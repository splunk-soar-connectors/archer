# File: archer_connector.py
#
# Copyright (c) 2016-2022 Splunk Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under
# the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
# either express or implied. See the License for the specific language governing permissions
# and limitations under the License.
"""Implements a Phantom.us app for RSA Archer GRC."""

import fcntl
import json
import os
import sys

import phantom.app as phantom
from bs4 import UnicodeDammit
from phantom.action_result import ActionResult
from phantom.base_connector import BaseConnector

# Imports local to this App
import archer_consts as consts
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
        self.file_ = consts.ARCHER_LAST_RECORD_FILE.format(self.get_asset_id())
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

        # Fetching the Python major version
        try:
            self._python_version = int(sys.version_info[0])
        except:
            return self.set_status(phantom.APP_ERROR, consts.ARCHER_ERR_PYTHON_MAJOR_VERSION)

        return phantom.APP_SUCCESS

    def finalize(self):
        self.save_state(self._state)
        return phantom.APP_SUCCESS

    def _handle_py_ver_compat_for_input_str(self, input_str):
        """
        This method returns the encoded|original string based on the Python version.
        :param input_str: Input string to be processed
        :return: input_str (Processed input string based on following logic 'input_str - Python 3; encoded input_str - Python 2')
        """

        try:
            if input_str and self._python_version == 2:
                input_str = UnicodeDammit(input_str).unicode_markup.encode('utf-8')
        except:
            self.debug_print("Error occurred while handling python 2to3 compatibility for the input string")

        return input_str

    def _get_error_message_from_exception(self, e):
        """ This method is used to get appropriate error message from the exception.
        :param e: Exception object
        :return: error message
        """

        try:
            if e.args:
                if len(e.args) > 1:
                    error_code = e.args[0]
                    error_msg = e.args[1]
                elif len(e.args) == 1:
                    error_code = consts.ARCHER_ERR_CODE_UNAVAILABLE
                    error_msg = e.args[0]
            else:
                error_code = consts.ARCHER_ERR_CODE_UNAVAILABLE
                error_msg = consts.ARCHER_ERR_CHECK_ASSET_CONFIG
        except:
            error_code = consts.ARCHER_ERR_CODE_UNAVAILABLE
            error_msg = consts.ARCHER_ERR_CHECK_ASSET_CONFIG

        try:
            error_msg = self._handle_py_ver_compat_for_input_str(error_msg)
        except TypeError:
            error_msg = consts.ARCHER_UNICODE_DAMMIT_TYPE_ERR_MESSAGE
        except:
            error_msg = consts.ARCHER_ERR_CHECK_ASSET_CONFIG

        if error_code in consts.ARCHER_ERR_CODE_UNAVAILABLE:
            error_text = consts.ARCHER_ERR_MESSAGE.format(error_msg)
        else:
            error_text = consts.ARCHER_ERR_CODE_MESSAGE.format(error_code, error_msg)

        return error_text

    def _handle_on_poll(self, action_result, param):
        """Handles 'on_poll' ingest actions"""

        self.save_progress('State location {} '.format(self. get_state_file_path()))

        config = self.get_config()

        if 'cef_mapping' not in config:
            action_result.set_status(phantom.APP_ERROR, consts.ARCHER_ERR_CEF_MAPPING_REQUIRED)
            return action_result.get_status()

        try:
            cef_mapping = json.loads(config.get('cef_mapping'))
        except Exception as e:
            err = self._get_error_message_from_exception(e)
            action_result.set_status(phantom.APP_ERROR, 'CEF Mapping JSON is not valid: {}'.format(err))
            return action_result.get_status()

        cef_mapping = dict([(k.lower(), v) for k, v in list(cef_mapping.items())])

        if not cef_mapping.get('application'):
            action_result.set_status(phantom.APP_ERROR, consts.ARCHER_ERR_APPLICATION_NOT_PROVIDED)
            return action_result.get_status()

        application = cef_mapping.pop('application')

        state = self._state.get(application, {})
        max_content_id = state.get('max_content_id', -1)
        last_page = state.get('last_page', 1)
        max_records = self.POLLING_PAGE_SIZE
        sort_type = consts.ARCHER_SORT_TYPE_ASCENDING

        if self.is_poll_now():
            max_content_id = 0
            last_page = 1
            max_records = param.get('container_count')
            sort_type = consts.ARCHER_SORT_TYPE_DESCENDING

        self.save_progress('Polling Archer for {} new records after {}...'.format(
               max_records, max_content_id))
        proxy = self._get_proxy()

        if not cef_mapping.get('tracking'):
            action_result.set_status(phantom.APP_ERROR, consts.ARCHER_ERR_TRACKING_ID_NOT_PROVIDED)
            return action_result.get_status()
        tracking_id_field = cef_mapping.pop('tracking')

        completed_records = 0
        max_ingested_id = max_content_id
        proxy.excluded_fields = [ x.lower().strip() for x in config.get('exclude_fields', '').split(',') ]
        while completed_records < max_records:
            records = proxy.find_records(application, tracking_id_field, None, self.POLLING_PAGE_SIZE, sort=sort_type, page=last_page)
            nrecs = len(records)
            if not records:
                break
            self.send_progress('Processing {} records, page {}...'.format(nrecs, last_page))
            for i, rec in enumerate(records):
                content_id = int(rec['@contentId'])
                if content_id <= max_content_id:
                    continue
                self.send_progress('On record {}/{}...'.format(i + 1, nrecs))
                record_name = consts.ARCHER_ERR_RECORD_NOT_FOUND

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

            if nrecs < self.POLLING_PAGE_SIZE:
                break
            else:
                last_page += 1

        self.save_progress('Ingested {} records'.format(completed_records))
        if not self.is_poll_now():
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
                self.get_config().get('instance_name'),
                self.get_config().get('domain'))

    def _get_proxy(self):
        """Returns an archer_utils.ArcherAPISession object."""
        if not self.proxy:
            ep, user, pwd, instance, users_domain = self._get_proxy_args()
            verify = self.get_config().get('verify_ssl')
            self.debug_print('New Archer API session at ep:{}, user:{}, '
                             'verify:{}'.format(ep, user, verify))
            self.proxy = archer_utils.ArcherAPISession(ep, user, pwd, instance, self._python_version, users_domain)
            self.proxy.verifySSL = verify
            archer_utils.W = self.debug_print
        return self.proxy

    def _handle_test_connectivity(self, action_result, param):
        """Tests Archer connectivity and App config by attempting to log in."""
        self.send_progress('Archer login test initiated...')

        try:
            term_msg = ''
            p = self._get_proxy()
            p.get_token()
            term_msg = p.terminate_session()
        except Exception as e:
            err = self._get_error_message_from_exception(e)
            self.debug_print('Exception during archer test: {}'.format(err))
            self.save_progress('Archer login test failed')
            self.save_progress('Please provide correct URL and credentials')
            if term_msg != '':
                self.save_progress(term_msg)
            self.save_progress(err)
            return action_result.set_status(phantom.APP_ERROR, 'Test Connectivity failed')
        self.send_progress('Archer login test... SUCCESS')
        msg = consts.ARCHER_SUCC_CONFIGURATION
        if term_msg != '':
            self.save_progress(term_msg)
        self.save_progress("Test connectivity passed")

        return action_result.set_status(phantom.APP_SUCCESS, msg)

    def _handle_create_ticket(self, action_result, param):
        """Handles 'create_ticket' actions.

            Takes one param.

            If it's an integer, then it's a container_id.  Use the Phantom
                REST API to get CEF fields from the container.  Each asset
                must have a config param mapping CEF<->Archer fields and the
                new record is created with the data from the CEF fields of the
                given container, populated into the appropriate Archer fields.
                This mapping may be a list of JSON dictionaries instead of a single
                dictionary, so that multiple 'module' keys may be specified and
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
        self.save_progress('Processing data parameter...')

        json_string = param.get('json_string', '')
        try:
            mapping = json.loads(json_string)
        except (ValueError, TypeError) as e:
            msg = consts.ARCHER_ERR_VALID_JSON
            self.debug_print(msg)
            err = self._get_error_message_from_exception(e)
            action_result.set_status(phantom.APP_ERROR, msg, err)
            return action_result.get_status()
        if not isinstance(mapping, dict):
            action_result.set_status(phantom.APP_ERROR, 'Invalid JSON string. Must be a dictionary containing key-value pairs')
            return action_result.get_status()

        self.debug_print('Parsed data: {}'.format(mapping))
        proxy = self._get_proxy()
        if not isinstance(mapping, dict):
            term_msg = proxy.terminate_session()
            msg = consts.ARCHER_ERR_NON_DICT.format(mapping)
            msg = '{}{}'.format(msg, term_msg)
            self.debug_print(msg)
            action_result.set_status(phantom.APP_ERROR, msg, err)
            return action_result.get_status()

        app = param.get('application')

        self.save_progress('Creating Archer record')
        try:
            cid = proxy.create_record(app, mapping)
        except Exception as e:
            err = self._get_error_message_from_exception(e)
            term_msg = proxy.terminate_session()
            return action_result.set_status(phantom.APP_ERROR, 'Failed to create Archer record {}{}'.format(err, term_msg))

        term_msg = proxy.terminate_session()
        if cid:
            self.save_progress('Created Archer record {}'.format(cid))
            d = {'content_id': cid}
            action_result.add_data(d)
            action_result.update_summary(d)
            action_result.set_status(phantom.APP_SUCCESS, 'Created ticket{}'.format(term_msg))
        else:
            action_result.set_status(phantom.APP_ERROR, 'Failed to create Archer record{}'.format(term_msg))
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
            term_msg = proxy.terminate_session()
            action_result.set_status(phantom.APP_ERROR,
                'Error: Could not find record "{}". "{}" may not be a tracking ID field in app "{}".{}'.format(nfv, nfid, app, term_msg))
            return action_result.get_status()

        if proxy.get_levelId_for_app(app) is None:
            term_msg = proxy.terminate_session()
            action_result.set_status(phantom.APP_ERROR, 'Error: Could not identify application \'{}\'{}'.format(app, term_msg))
        else:
            try:
                fid = int(fid)
            except (ValueError, TypeError):
                fid = proxy.get_fieldId_for_app_and_name(app, fid)

            if not fid or type(fid) != int:
                term_msg = proxy.terminate_session()
                action_result.set_status(phantom.APP_ERROR, 'Error: Could not identify field {}.{}'.format(orig_fid, term_msg))
            else:
                pur = proxy.update_record(app, cid, fid, value)
                term_msg = proxy.terminate_session()
                if pur:
                    action_result.set_status(phantom.APP_SUCCESS, 'Updated ticket{}'.format(term_msg))
                else:
                    action_result.set_status(phantom.APP_ERROR, 'Unable to update ticket{}'.format(term_msg))

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
                term_msg = proxy.terminate_session()
                action_result.set_status(phantom.APP_ERROR,
                    'Error: Could not find record "{}". "{}" may not be a tracking ID field in app "{}".{}'.format(nfv, nfid, app, term_msg))
                return action_result.get_status()

        action_result.update_summary({'content_id': cid})

        try:
            term_msg = ''
            record = proxy.get_record_by_id(app, cid)
            term_msg = proxy.terminate_session()
            if record:
                action_result.add_data(record)
                action_result.set_status(phantom.APP_SUCCESS, 'Ticket retrieved{}'.format(term_msg))
            else:
                action_result.set_status(phantom.APP_ERROR, 'Could not locate Ticket{}'.format(term_msg))
        except:
            action_result.set_status(phantom.APP_ERROR, 'Given content_id not found in \'{}\' application{}'.format(app, term_msg))

        return action_result.get_status()

    def _validate_integer(self, action_result, parameter, key, allow_zero=False):
        """Handles non integer values and set appropriate status"""
        if parameter is not None:
            try:
                if not float(parameter).is_integer() or isinstance(parameter, float):
                    return action_result.set_status(phantom.APP_ERROR, consts.ARCHER_ERR_VALID_INTEGER.format(key)), None
                parameter = int(parameter)
            except:
                return action_result.set_status(phantom.APP_ERROR, consts.ARCHER_ERR_VALID_INTEGER.format(key)), None
            if parameter < 0:
                return action_result.set_status(phantom.APP_ERROR, consts.ARCHER_ERR_NON_NEGATIVE.format(key)), None
            if not allow_zero and parameter == 0:
                return action_result.set_status(phantom.APP_ERROR, consts.ARCHER_ERR_VALID_INTEGER.format(key)), None
        return phantom.APP_SUCCESS, parameter

    def _handle_list_tickets(self, action_result, param):
        """Handles 'list_tickets' actions"""
        self.save_progress('Get Archer record...')
        app = param.get('application')
        max_count = param.get('max_results', 100)
        search_field_name = param.get('name_field')
        search_value = param.get('search_value')

        status, max_count = self._validate_integer(action_result, max_count, "max_result", False)
        if (phantom.is_fail(status)):
            return action_result.get_status()

        if (search_field_name or search_value) and not (search_field_name and search_value):
            action_result.set_status(phantom.APP_ERROR, 'Need both the field name and the search value to search')
            return action_result.get_status()

        proxy = self._get_proxy()

        proxy.excluded_fields = [ x.lower().strip() for x in self.get_config().get('exclude_fields', '').split(',') ]
        records = proxy.find_records(app, search_field_name, search_value, max_count)
        term_msg = proxy.terminate_session()

        if records:
            for r in records:
                action_result.add_data(r)
            action_result.set_status(phantom.APP_SUCCESS, 'Tickets retrieved{}'.format(term_msg))
            action_result.update_summary({'records_found': len(records)})
        else:
            if search_field_name and search_value:
                action_result.set_status(phantom.APP_SUCCESS,
                    'Found no tickets with field {} containing value {}{}'.format(search_field_name, search_value, term_msg))
            else:
                action_result.set_status(phantom.APP_SUCCESS, 'Found no tickets for {}{}'.format(app, term_msg))

        return action_result.get_status()

    def handle_action(self, param):
        """Dispatches actions."""
        action_id = self.get_action_identifier()
        self.debug_print('action_id', action_id)
        action_result = ActionResult(dict(param))
        self.add_action_result(action_result)
        try:
            if (action_id == consts.ARCHER_ACTION_CREATE_TICKET):
                return self._handle_create_ticket(action_result, param)
            elif (action_id == consts.ARCHER_ACTION_UPDATE_TICKET):
                return self._handle_update_ticket(action_result, param)
            elif (action_id == consts.ARCHER_ACTION_GET_TICKET):
                return self._handle_get_ticket(action_result, param)
            elif (action_id == consts.ARCHER_ACTION_LIST_TICKET):
                return self._handle_list_tickets(action_result, param)
            elif (action_id == phantom.ACTION_ID_TEST_ASSET_CONNECTIVITY):
                return self._handle_test_connectivity(action_result, param)
            elif (action_id == consts.ARCHER_ACTION_ON_POLL):
                return self._handle_on_poll(action_result, param)
            return phantom.APP_SUCCESS
        except Exception as e:
            err = self._get_error_message_from_exception(e)
            error_message = consts.ARCHER_ERR_ACTION_EXECUTION.format(action_id, err)
            self.debug_print(error_message)
            return action_result.set_status(phantom.APP_ERROR, error_message)


if __name__ == '__main__':
    from traceback import format_exc

    import pudb
    pudb.set_trace()
    if (len(sys.argv) < 2):
        print('No test json specified as input')
        sys.exit(0)
    with open(sys.argv[1]) as f:
        in_json = f.read()
        in_json = json.loads(in_json)
        print(json.dumps(in_json, indent=4))
        connector = ArcherConnector()
        connector.print_progress_message = True
        try:
            ret_val = connector._handle_action(json.dumps(in_json), None)
        except:
            print(format_exc())
        print(json.dumps(json.loads(ret_val), indent=4))
    sys.exit(0)
