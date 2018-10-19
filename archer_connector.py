# File: archer_connector.py
# Copyright (c) 2016-2018 Splunk Inc.
#
# SPLUNK CONFIDENTIAL - Use or disclosure of this material in whole or in part
# without a valid written license from Splunk Inc. is PROHIBITED.
#
# --

"""Implements a Phantom.us app for RSA Archer GRC."""

import phantom.app as phantom
from phantom.base_connector import BaseConnector
from phantom.action_result import ActionResult

import os
import json
import fcntl
import requests
import archer_utils


class ArcherConnector(BaseConnector):
    """A subclass of `phantom.base_connector.BaseConnector`, which implements
        on_poll and *_ticket to manipulate records/events in RSA Archer GRC.
    """

    POLLING_PAGE_SIZE = 100

    def __init__(self):
        """Initialize persistent state (used only to store latest record
            time.)
        """
        super(ArcherConnector, self).__init__()
        self.file_ = 'last_record_{}.txt'.format(self.get_asset_id())
        self.latest_time = 0
        self.proxy = None
        if isinstance(self.get_app_config(), dict):
            self.latest_time = self.get_app_config().get('past_days', 0)
        if os.path.isfile(self.file_):
            with open(self.file_) as fi:
                fcntl.flock(fi, fcntl.LOCK_SH)
                self.latest_time = fi.read()
                fcntl.flock(fi, fcntl.LOCK_UN)
            try:
                self.latest_time = float(self.latest_time)
            except (ValueError, TypeError):
                pass
        self._state = {}

    def initialize(self):
        self._state = self.load_state()
        return phantom.APP_SUCCESS

    def finalize(self):
        self.save_state(self._state)
        return phantom.APP_SUCCESS

    def _handle_on_poll(self, action_result, param):
        """Handles 'on_poll' ingest actions"""

        self.save_progress('State location {} '.format(self. get_state_file_path()))

        config = self.get_config()

        if 'cef_mapping' not in config:
            action_result.set_status(phantom.APP_ERROR, 'CEF Mapping is required for ingestion. Please add CEF mapping to the asset config.')
            return action_result.get_status()

        try:
            cef_mapping = json.loads(config.get('cef_mapping'))
        except Exception as e:
            action_result.set_status(phantom.APP_ERROR, 'CEF Mapping JSON is not valid: {}'.format(str(e)))
            return action_result.get_status()

        cef_mapping = dict( [ (k.lower(), v) for k, v in cef_mapping.iteritems() ])

        if not cef_mapping.get('application'):
            action_result.set_status(phantom.APP_ERROR, 'Application not provided in CEF Mapping (use key: "application")')
            return action_result.get_status()

        application = cef_mapping.pop('application')

        state = self._state.get(application, {})
        max_content_id = state.get('max_content_id', -1)
        last_page = state.get('last_page', 1)
        max_records = min(self.POLLING_PAGE_SIZE, param['container_count'])
        self.save_progress('Polling Archer for {} new records after {}...'.format(
               max_records, max_content_id))
        proxy = self._get_proxy()

        if not cef_mapping.get('tracking'):
            action_result.set_status(phantom.APP_ERROR, 'Tracking ID Field name not provided in CEF Mapping (use key: "tracking")')
            return action_result.get_status()
        tracking_id_field = cef_mapping.pop('tracking')

        completed_records = 0
        max_ingested_id = max_content_id
        proxy.excluded_fields = [ x.lower().strip() for x in config.get('exclude_fields', '').split(',') ]
        while completed_records < max_records:
            records = proxy.find_records(application, tracking_id_field, None, self.POLLING_PAGE_SIZE, sort='Ascending', page=last_page)
            nrecs = len(records)
            if not records:
                break
            self.send_progress('Processing {} records, page {}...'.format(nrecs, last_page))
            for i, rec in enumerate(records):
                content_id = int(rec['@contentId'])
                if content_id <= max_content_id:
                    continue
                self.send_progress('On record {}/{}...'.format(i + 1, nrecs))
                record_name = 'Record Name not found'

                cef = {}
                for field in rec.get('Field', []):
                    name = field.get('@name')
                    ftype = field.get('@type')
                    content = None
                    if ftype in []:
                        pass
                    else:
                        content = field.get('#text')
                    if name.lower() in cef_mapping:
                        cef[cef_mapping.get(name.lower(), name)] = content
                    if name == tracking_id_field:
                        record_num = str(field.get('#text'))
                        record_name = '{} - {}'.format(application, record_num)

                c = {
                    'data': {},
                    'description': 'Ingested from Archer',
                }
                c['name'] = record_name
                c['data']['archer_record'] = rec
                c['data']['archer_url'] = self._get_proxy_args()
                c['data']['archer_instance'] = c['data']['archer_url'][0]
                c['data']['archer_url'] = c['data']['archer_url'][3]
                c['data']['archer_content_id'] = int(rec['@contentId'])
                c['source_data_identifier'] = '{}@"{}"/{}'.format(
                        c['data']['archer_content_id'],
                        c['data']['archer_instance'],
                        c['data']['archer_url'])
                c['data']['raw'] = dict(rec)

                self.send_progress('Saving container {}...'.format(c['data']['archer_content_id']))
                status, msg, id_ = self.save_container(c)
                if status == phantom.APP_ERROR:
                    self.debug_print('Failed to store: {}'.format(c))
                    self.debug_print('stat/msg {}/{}'.format(status, msg))
                    action_result.set_status(
                            phantom.APP_ERROR,
                            'Container creation failed: {}'.format(msg))
                    return status
                art = {
                    'container_id': id_,
                    'label': 'event',
                    'source_data_identifier': c['source_data_identifier'],
                    'cef': cef,
                    'run_automation': True,
                }
                self.send_progress('Saving artifact...')
                status, msg, id_ = self.save_artifact(art)
                if status == phantom.APP_ERROR:
                    self.debug_print('Failed to store: {}'.format(c))
                    self.debug_print('stat/msg {}/{}'.format(status, msg))
                    action_result.set_status(
                            phantom.APP_ERROR,
                            'Artifact creation failed: {}'.format(msg))
                    return status
                max_ingested_id = max(max_ingested_id, c['data']['archer_content_id'])
                completed_records += 1
                if completed_records >= max_records:
                    break
            if completed_records < max_records:
                last_page += 1

        self.save_progress('Ingested {} records'.format(completed_records))
        self._state[application] = {'max_content_id': max_ingested_id, 'last_page': last_page}
        self.save_progress('Import complete.')
        action_result.set_status(phantom.APP_SUCCESS, 'Import complete')
        return action_result.get_status()

    def _save_latest_time(self, latest_time=None):
        """Sets the time of the last record successfully fetched, in epoch
            time.
        """
        if latest_time is None:
            latest_time = self.latest_time
        with open(self.file_, 'w') as f1:
            fcntl.flock(f1, fcntl.LOCK_EX)
            with open(self.file_, 'w') as f2:
                f2.write(str(latest_time))
            fcntl.flock(f1, fcntl.LOCK_UN)

    def _get_proxy_args(self):
        """Returns the args to instantiate archer_utils.ArcherAPISession"""
        return (self.get_config().get('endpoint_url'),
                self.get_config().get('username'),
                self.get_config().get('password'),
                self.get_config().get('instance_name'))

    def _get_proxy(self):
        """Returns an archer_utils.ArcherAPISession object."""
        if not self.proxy:
            ep, user, pwd, instance = self._get_proxy_args()
            verify = self.get_config().get('verify_ssl')
            self.debug_print('New Archer API session at ep:{}, user:{}, '
                             'verify:{}'.format(ep, user, verify))
            self.proxy = archer_utils.ArcherAPISession(ep, user, pwd, instance)
            self.proxy.verifySSL = verify
            archer_utils.W = self.debug_print
        return self.proxy

    def _handle_test_connectivity(self, action_result, param):
        """Tests Archer connectivity and App config by attempting to log in."""
        self.send_progress('Archer login test initiated...')

        try:
            p = self._get_proxy()
            p.get_token()
        except Exception as e:
            self.debug_print('Exception during archer test: {}'.format(e))
            self.save_progress('Archer login test failed')
            self.save_progress('Please provide correct URL and credentials')
            return action_result.set_status(phantom.APP_ERROR, 'Test Connectivity failed.')
        self.send_progress('Archer login test... SUCCESS')
        msg = 'Archer configuration test SUCCESS'
        return self.set_status_save_progress(phantom.APP_SUCCESS, msg)

    def _container_to_archer(self, cid):
        """Reads CEF fields from a container, returns a list of dicts with
            key/value pairs to populate a new Archer record, where the
            'module' key of each dict names the module/app within which to
            create a new record.
        """
        self.save_progress('Fetching data for container {}'.format(cid))
        c2as = json.loads(self.get_config().get('cef_mapping'))
        if isinstance(c2as, dict):
            c2as = (c2as,)
        maps = [{'module': (c2a['module'],)} for c2a in c2as]
        url = 'http://127.0.0.1/rest/container/{}'.format(cid)
        c = requests.get(url, verify=False).json()
        if 'failed' in c and c['failed']:
            raise Exception('Failed to get container: {}'.format(
                    'message' in c and c['message'] or 'unknown reason'))
        self.debug_print('Mapping Container {}'.format(c))
        for m, c2a, cfld in ((maps[i], c2a, x) for i, c2a in enumerate(c2as)
                             for x in c if x in c2a):
            self.debug_print('Container[{}] <-> Archer/{}[{}]'.format(
                    cfld, m['module'], c2a[cfld]))
            self.debug_print('m[{}] = {} + [{}]'.format(
                    c2a[cfld], m.get(c2a[cfld], []), c[cfld]))
            m[c2a[cfld]] = m.get(c2a[cfld], []) + [c[cfld]]
        self.save_progress('Fetching artifacts for container')
        url = 'http://127.0.0.1/rest/container/{}/artifacts{}'
        page = 1
        while True:
            get_page = page > 1 and '?page={}'.format(page) or ''
            self.debug_print('URL {}'.format(url.format(cid, get_page)))
            resp = requests.get(url.format(cid, get_page), verify=False).json()
            for r in resp['data']:
                url2 = 'http://127.0.0.1/rest/artifact/{}'.format(r['id'])
                self.debug_print('URL {}'.format(url.format(cid, get_page)))
                c = requests.get(url2, verify=False).json()
                self.debug_print('Mapping Artifact {}'.format(c))
                for m, c2a, cfld in ((maps[i], c2a, x)
                                     for i, c2a in enumerate(c2as)
                                     for x in c['cef'] if x in c2a):
                    self.debug_print(
                            'Container["cef"][{}] <-> Archer/{}[{}]'.format(
                                    cfld, m['module'], c2a[cfld]))
                    self.debug_print('m[{}] = {} + [{}]'.format(
                            c2a[cfld], m.get(c2a[cfld], []), c['cef'][cfld]))
                    m[c2a[cfld]] = m.get(c2a[cfld], []) + [c['cef'][cfld]]
            if resp['num_pages'] <= page:
                break
            page += 1
        return [{x: ', '.join(m[x]) for x in m} for m in maps]

    def _handle_create_ticket(self, action_result, param):
        """Handles 'create_ticket' actions.

            Takes one param.

            If it's an integer, then it's a container_id.  Use the Phantom
                REST API to get CEF fields from the container.  Each asset
                must have a config param mapping CEF<->Archer fields, and the
                new record is created with the data from the CEF fields of the
                given container, populated into the appropriate Archer fields.
                This mapping may be a list of JSON dicts instead of a single
                dict, so that multiple 'module' keys may be specified and
                mapped to.

            Otherwise, if it's a native or JSON list, each item in the list is
                processed as a dict.

            If it's a native or JSON dict, then use it as key/value pairs to
                populate the new record, where the 'module' key sets the name
                or ID of the module within which to create the new record.

            In either case, the data must have a 'module' key set to the name
                or ID of the module within which to create the new record.  And
                if there's an 'allow_partial' key set to True, the record-
                creation process will proceed even if some fields could not be
                updated appropriately.
        """
        self.save_progress(u'Processing data parameter...')

        json_string = param.get(u'json_string', '')
        try:
            mapping = json.loads(json_string)
        except (ValueError, TypeError) as e:
            msg = u'JSON field does not contain a valid JSON value'
            self.debug_print(msg)
            action_result.set_status(phantom.APP_ERROR, msg, e)
            return action_result.get_status()
        if not isinstance(mapping, dict):
            action_result.set_status(phantom.APP_ERROR, u'Invalid JSON string. Must be a dictionary containing key value pairs')
            return action_result.get_status()

        self.debug_print(u'Parsed data: {}'.format(mapping))
        proxy = self._get_proxy()
        if not isinstance(mapping, dict):
            msg = u'Non-dict map: {}'.format(mapping)
            self.debug_print(msg)
            action_result.set_status(phantom.APP_ERROR, msg, e)
            return action_result.get_status()

        app = param.get('application')

        self.save_progress(u'Creating Archer record')
        try:
            cid = proxy.create_record(app, mapping)
        except Exception as e:
            return action_result.set_status(phantom.APP_ERROR, u'Failed to create Archer record. Error: {0}'.format(str(e)))

        if cid:
            self.save_progress(u'Created Archer record {}'.format(cid))
            d = {'content_id': cid}
            action_result.add_data(d)
            action_result.update_summary(d)
            action_result.set_status(phantom.APP_SUCCESS, 'Created ticket')
        else:
            action_result.set_status(phantom.APP_ERROR, u'Failed to create Archer record')
            return action_result.get_status()
        return action_result.get_status()

    def _handle_update_ticket(self, action_result, param):
        """Handles 'update_ticket' actions"""
        self.save_progress('Updating Archer record...')
        app = param.get('application')
        cid = param.get('content_id')
        nfid = param.get('name_field')
        nfv = param.get('name_value')
        fid = orig_fid = param.get('field_id')
        value = param.get('value')
        proxy = self._get_proxy()

        # Raise an exception if invalid numeric value is provided in content ID parameter
        try:
            if str(cid) and not str(cid) == 'None' and (not str(cid).isdigit() or str(cid) == '0'):
                raise ValueError
        except:
            action_result.set_status(phantom.APP_ERROR, 'Please provide a valid content ID')
            return action_result.get_status()

        if not cid:
            if nfid and nfv:
                cid = proxy.get_content_id(app, nfid, nfv)
            else:
                action_result.set_status(phantom.APP_ERROR, 'Either content ID or both name field and name value are mandatory')
                return action_result.get_status()
        action_result.update_summary({'content_id': cid})

        if not cid and nfv:
            action_result.set_status(phantom.APP_ERROR, 'Error: Could not find record "{}". "{}" may not be a tracking ID field in app "{}".'.format(nfv, nfid, app))
            return action_result.get_status()

        try:
            fid = int(fid)
        except (ValueError, TypeError):
            fid = proxy.get_fieldId_for_app_and_name(app, fid)

        if not fid or type(fid) != int:
            action_result.set_status(phantom.APP_ERROR, 'Error: Could not identify field {}.'.format(orig_fid))
        else:
            if proxy.update_record(app, cid, fid, value):
                action_result.set_status(phantom.APP_SUCCESS, 'Updated ticket')
            else:
                action_result.set_status(phantom.APP_ERROR, 'Unable to update ticket')

        return action_result.get_status()

    def _handle_get_ticket(self, action_result, param):
        """Handles 'get_ticket' actions"""
        self.save_progress('Get Archer record...')
        app = param.get('application')
        cid = param.get('content_id')
        nfid = param.get('name_field')
        nfv = param.get('name_value')
        proxy = self._get_proxy()

        # Raise an exception if invalid numeric value is provided in content ID parameter
        try:
            if str(cid) and not str(cid) == 'None' and (not str(cid).isdigit() or str(cid) == '0'):
                raise ValueError
        except:
            action_result.set_status(phantom.APP_ERROR, 'Please provide a valid content ID')
            return action_result.get_status()

        if not cid:
            if nfid and nfv:
                cid = proxy.get_content_id(app, nfid, nfv)
            else:
                action_result.set_status(phantom.APP_ERROR, 'Either content ID or both name field and name value are mandatory')
                return action_result.get_status()
            if not cid:
                action_result.set_status(phantom.APP_ERROR, 'Error: Could not find record "{}". "{}" may not be a tracking ID field in app "{}".'.format(nfv, nfid, app))
                return action_result.get_status()

        action_result.update_summary({'content_id': cid})
        record = proxy.get_record_by_id(app, cid)

        if record:
            action_result.add_data(record)
            action_result.set_status(phantom.APP_SUCCESS, 'Ticket retrieved')
        else:
            action_result.set_status(phantom.APP_ERROR, 'Could not locate Ticket')

        return action_result.get_status()

    def _handle_list_tickets(self, action_result, param):
        """Handles 'list_tickets' actions"""
        self.save_progress('Get Archer record...')
        app = param.get('application')
        max_count = param.get('max_results', 100)
        search_field_name = param.get('name_field')
        search_value = param.get('search_value')

        try:
            max_count = int(max_count)
        except:
            return action_result.set_status(phantom.APP_ERROR, 'Please provide a valid integer max_results value')

        if (search_field_name or search_value) and not (search_field_name and search_value):
            action_result.set_status(phantom.APP_ERROR, 'Need both the field name and the search value to search')
            return action_result.get_status()

        proxy = self._get_proxy()

        proxy.excluded_fields = [ x.lower().strip() for x in self.get_config().get('exclude_fields', '').split(',') ]
        records = proxy.find_records(app, search_field_name, search_value, max_count)

        if records:
            for r in records:
                action_result.add_data(r)
            action_result.set_status(phantom.APP_SUCCESS, 'Tickets retrieved')
            action_result.update_summary({'records_found': len(records)})
        else:
            if search_field_name and search_value:
                action_result.set_status(phantom.APP_ERROR, 'Found no tickets with field {} containing value {}'.format(search_field_name, search_value))
            else:
                action_result.set_status(phantom.APP_ERROR, 'Found no tickets for {}'.format(app))

        return action_result.get_status()

    def handle_action(self, param):
        """Dispatches actions."""
        action_id = self.get_action_identifier()
        self.debug_print('action_id', action_id)
        action_result = ActionResult(dict(param))
        self.add_action_result(action_result)
        try:
            if (action_id == 'create_ticket'):
                return self._handle_create_ticket(action_result, param)
            elif (action_id == 'update_ticket'):
                return self._handle_update_ticket(action_result, param)
            elif (action_id == 'get_ticket'):
                return self._handle_get_ticket(action_result, param)
            elif (action_id == 'list_tickets'):
                return self._handle_list_tickets(action_result, param)
            elif (action_id == phantom.ACTION_ID_TEST_ASSET_CONNECTIVITY):
                return self._handle_test_connectivity(action_result, param)
            elif (action_id == 'on_poll'):
                return self._handle_on_poll(action_result, param)
            return phantom.APP_SUCCESS
        except Exception as e:
            error_message = 'Exception during execution of archer action: {} and the error is: {}'.format(action_id, e)
            self.debug_print(error_message)
            return action_result.set_status(phantom.APP_ERROR, error_message)


if __name__ == '__main__':
    import sys
    import pudb
    from traceback import format_exc
    pudb.set_trace()
    if (len(sys.argv) < 2):
        print 'No test json specified as input'
        exit(0)
    with open(sys.argv[1]) as f:
        in_json = f.read()
        in_json = json.loads(in_json)
        print(json.dumps(in_json, indent=4))
        connector = ArcherConnector()
        connector.print_progress_message = True
        try:
            ret_val = connector._handle_action(json.dumps(in_json), None)
        except:
            print format_exc()
        print (json.dumps(json.loads(ret_val), indent=4))
    exit(0)
