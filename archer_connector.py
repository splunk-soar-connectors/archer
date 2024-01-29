# File: archer_connector.py
#
# Copyright (c) 2016-2024 Splunk Inc.
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

import base64
import fcntl
import json
import os
import sys

import encryption_helper
import phantom.app as phantom
from phantom import vault
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
        self.sessionToken = None
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
        self.sessionToken = self._state.get(consts.ARCHER_SESSION_TOKEN)
        if self.sessionToken:
            self.sessionToken = self.decrypt_state(self.sessionToken, consts.ARCHER_SESSION_TOKEN)
        self.proxy = self._get_proxy()
        return phantom.APP_SUCCESS

    def finalize(self):
        self._state[consts.ARCHER_SESSION_TOKEN] = self.sessionToken
        if self.sessionToken:
            self._state[consts.ARCHER_SESSION_TOKEN] = self.encrypt_state(self.sessionToken, consts.ARCHER_SESSION_TOKEN)
        self.save_state(self._state)
        return phantom.APP_SUCCESS

    def encrypt_state(self, encrypt_var, token_name):
        """ Handle encryption of token.
        :param encrypt_var: Variable needs to be encrypted
        :return: encrypted variable
        """
        self.debug_print(consts.ARCHER_ENCRYPT_TOKEN.format(token_name))   # nosemgrep
        return encryption_helper.encrypt(encrypt_var, self.get_asset_id())

    def decrypt_state(self, decrypt_var, token_name):
        """ Handle decryption of token.
        :param decrypt_var: Variable needs to be decrypted
        :return: decrypted variable
        """
        self.debug_print(consts.ARCHER_DECRYPT_TOKEN.format(token_name))    # nosemgrep
        return encryption_helper.decrypt(decrypt_var, self.get_asset_id())

    def _get_error_message_from_exception(self, e):
        """
        Get appropriate error message from the exception.
        :param e: Exception object
        :return: error message
        """

        error_code = None
        error_msg = consts.ERR_MSG_UNAVAILABLE

        self.error_print('Error occurred.', e)

        try:
            if hasattr(e, 'args'):
                if len(e.args) > 1:
                    error_code = e.args[0]
                    error_msg = e.args[1]
                elif len(e.args) == 1:
                    error_msg = e.args[0]
        except Exception as e:
            self.error_print('Error occurred while fetching exception information. Details: {}'.format(str(e)))

        if not error_code:
            error_text = 'Error Message: {}'.format(error_msg)
        else:
            error_text = 'Error Code: {}. Error Message: {}'.format(error_code, error_msg)

        return error_text

    def _handle_on_poll(self, action_result, param):
        """Handles 'on_poll' ingest actions"""

        self.save_progress('State location {} '.format(self. get_state_file_path()))

        config = self.get_config()

        if 'cef_mapping' not in config:
            return action_result.set_status(phantom.APP_ERROR, consts.ARCHER_ERR_CEF_MAPPING_REQUIRED)

        try:
            cef_mapping = json.loads(config.get('cef_mapping'))
        except Exception as e:
            err = self._get_error_message_from_exception(e)
            return action_result.set_status(phantom.APP_ERROR, 'CEF Mapping JSON is not valid: {}'.format(err))

        cef_mapping = dict([(k.lower(), v) for k, v in list(cef_mapping.items())])

        if not cef_mapping.get('application'):
            return action_result.set_status(phantom.APP_ERROR, consts.ARCHER_ERR_APPLICATION_NOT_PROVIDED)

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

        if not cef_mapping.get('tracking'):
            return action_result.set_status(phantom.APP_ERROR, consts.ARCHER_ERR_TRACKING_ID_NOT_PROVIDED)
        tracking_id_field = cef_mapping.pop('tracking')

        completed_records = 0
        max_ingested_id = max_content_id
        self.proxy.excluded_fields = [x.lower().strip() for x in config.get('exclude_fields', '').split(',')]
        while completed_records < max_records:
            records = self.proxy.find_records(application, tracking_id_field, None, self.POLLING_PAGE_SIZE, sort=sort_type, page=last_page)
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
                    'name': record_name
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
        return action_result.set_status(phantom.APP_SUCCESS, 'Import complete')

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
            verify = self.get_config().get('verify_ssl', False)
            self.debug_print('New Archer API session at ep:{}, user:{}, '
                             'verify:{}'.format(ep, user, verify))
            self.proxy = archer_utils.ArcherAPISession(ep, user, pwd, instance, users_domain, self)
            self.proxy.verifySSL = verify
            archer_utils.W = self.debug_print
        return self.proxy

    def _handle_test_connectivity(self, action_result, param):
        """Tests Archer connectivity and App config by attempting to log in."""
        self.send_progress('Archer login test initiated...')

        try:
            self.proxy.get_token()
        except Exception as e:
            err = self._get_error_message_from_exception(e)
            self.debug_print('Exception during archer test: {}'.format(err))
            self.save_progress('Archer login test failed')
            self.save_progress(err)
            self.save_progress('Please provide correct URL and credentials')
            return action_result.set_status(phantom.APP_ERROR, 'Test Connectivity failed')
        self.send_progress('Archer login test... SUCCESS')
        msg = consts.ARCHER_SUCC_CONFIGURATION
        self.save_progress('Test connectivity passed')

        return action_result.set_status(phantom.APP_SUCCESS, msg)

    def _handle_create_ticket(self, action_result, param):
        """Handles 'create_ticket' actions.

            Takes one param.

            If it's an integer, then it's a container_id.  Use the Splunk SOAR
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
            return action_result.set_status(phantom.APP_ERROR, msg, err)
        if not isinstance(mapping, dict):
            return action_result.set_status(phantom.APP_ERROR, consts.ARCHER_INVALID_JSON)

        self.debug_print('Parsed data: {}'.format(mapping))
        if not isinstance(mapping, dict):
            msg = consts.ARCHER_ERR_NON_DICT.format(mapping)
            self.debug_print(msg)
            return action_result.set_status(phantom.APP_ERROR, msg)

        app = param['application']

        self.save_progress('Creating Archer record')
        try:
            cid = self.proxy.create_record(app, mapping)
        except Exception as e:
            err = self._get_error_message_from_exception(e)
            return action_result.set_status(phantom.APP_ERROR, 'Failed to create Archer record {}'.format(err))

        if cid:
            self.save_progress('Created Archer record {}'.format(cid))
            d = {'content_id': cid}
            action_result.add_data(d)
            action_result.update_summary(d)
            action_result.set_status(phantom.APP_SUCCESS, 'Created ticket')
        else:
            action_result.set_status(phantom.APP_ERROR, 'Failed to create Archer record')
        return action_result.get_status()

    def _handle_update_ticket(self, action_result, param):
        """Handles 'update_ticket' actions"""
        self.save_progress('Updating Archer record...')
        app = param['application']
        cid = param.get('content_id')
        nfid = param.get('name_field')
        nfv = param.get('name_value')
        fid = param.get('field_id')
        value = param.get('value')
        json_string = param.get('json_string')

        mapping = ''
        if json_string:
            try:
                mapping = json.loads(json_string)
            except (ValueError, TypeError) as e:
                msg = consts.ARCHER_ERR_VALID_JSON
                self.debug_print(msg)
                err = self._get_error_message_from_exception(e)
                return action_result.set_status(phantom.APP_ERROR, msg, err)
            if not isinstance(mapping, dict):
                return action_result.set_status(phantom.APP_ERROR, consts.ARCHER_INVALID_JSON)

            self.debug_print('Parsed data: {}'.format(mapping))

        # Raise an exception if invalid numeric value is provided in content ID parameter
        try:
            if str(cid) and not str(cid) == 'None' and (not str(cid).isdigit() or str(cid) == '0'):
                raise ValueError
        except:
            return action_result.set_status(phantom.APP_ERROR, 'Please provide a valid content ID')
        if fid and not value:
            return action_result.set_status(phantom.APP_ERROR, 'Value paramter is mandatory if field id is mentioned')
        if not cid:
            if nfid and nfv:
                cid = self.proxy.get_content_id(app, nfid, nfv)
            else:
                return action_result.set_status(phantom.APP_ERROR, 'Either content ID or both name field and name value are mandatory')
            if not cid:
                return action_result.set_status(phantom.APP_ERROR,
                                    'Error: Could not find record "{}". "{}" may not be a tracking ID field in app "{}"'.format(nfv, nfid, app))

        action_result.update_summary({'content_id': cid})

        if self.proxy.get_levelId_for_app(app) is None:
            action_result.set_status(phantom.APP_ERROR, "Error: Could not identify application {}".format(app))
        else:
            pur = False
            if json_string:
                pur = self.proxy.update_record_by_json(app, cid, mapping)
            else:
                pur = self.proxy.update_record(app, cid, fid, value)
            if pur:
                action_result.set_status(phantom.APP_SUCCESS, 'Updated ticket')
            else:
                action_result.set_status(phantom.APP_ERROR, 'Unable to update ticket')

        return action_result.get_status()

    def _handle_get_ticket(self, action_result, param):
        """Handles 'get_ticket' actions"""
        self.save_progress('Get Archer record...')
        app = param['application']
        cid = param.get('content_id')
        nfid = param.get('name_field')
        nfv = param.get('name_value')

        # Raise an exception if invalid numeric value is provided in content ID parameter
        try:
            if str(cid) and not str(cid) == 'None' and (not str(cid).isdigit() or str(cid) == '0'):
                raise ValueError
        except:
            return action_result.set_status(phantom.APP_ERROR, 'Please provide a valid content ID')

        if not cid:
            if nfid and nfv:
                self.save_progress("Get Content ID...")
                cid = self.proxy.get_content_id(app, nfid, nfv)
            else:
                return action_result.set_status(phantom.APP_ERROR, 'Either content ID or both name field and name value are mandatory')
            if not cid:
                return action_result.set_status(phantom.APP_ERROR,
                                    'Error: Could not find record "{}". "{}" may not be a tracking ID field in app "{}"'.format(nfv, nfid, app))

        action_result.update_summary({'content_id': cid})

        try:
            record = self.proxy.get_record_by_id(app, cid)
            if record:
                action_result.add_data(record)
                action_result.set_status(phantom.APP_SUCCESS, 'Ticket retrieved')
            else:
                action_result.set_status(phantom.APP_ERROR, 'Could not locate Ticket')
        except:
            action_result.set_status(phantom.APP_ERROR, "Given content_id not found in \'{}\' application".format(app))

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
        app = param['application']
        max_count = param.get('max_results', 100)
        search_field_name = param.get('name_field')
        search_value = param.get('search_value')
        results_filter_json = param.get('results_filter_json')
        try:
            if results_filter_json:
                results_filter_dict = json.loads(results_filter_json)
            else:
                results_filter_dict = None
        except Exception as e:
            msg = consts.ARCHER_ERR_VALID_JSON
            self.debug_print(msg)
            err = self._get_error_message_from_exception(e)
            return action_result.set_status(phantom.APP_ERROR, msg, err)
        if results_filter_dict and not isinstance(results_filter_dict, dict):
            return action_result.set_status(phantom.APP_ERROR, consts.ARCHER_INVALID_JSON)

        results_filter_operator = param.get('results_filter_operator')
        results_filter_equality = param.get('results_filter_equality')
        if results_filter_operator:
            if results_filter_operator.lower() not in consts.ARCHER_OPERATOR_VALUELIST:
                return action_result.set_status(phantom.APP_ERROR,
                    f'Please enter a valid value for results_filter_operator from {consts.ARCHER_OPERATOR_VALUELIST}')
            else:
                results_filter_operator = results_filter_operator.lower()
        else:
            if results_filter_dict:
                if len(results_filter_dict) == 1 and not results_filter_operator:
                    results_filter_operator = "and"
        if results_filter_equality:
            if results_filter_equality.lower() not in consts.ARCHER_EQUALITY_VALUELIST:
                return action_result.set_status(phantom.APP_ERROR,
                    f'Please enter a valid value for results_filter_equality from {consts.ARCHER_EQUALITY_VALUELIST}')
            else:
                results_filter_equality = results_filter_equality.lower()

        status, max_count = self._validate_integer(action_result, max_count, 'max_result', False)
        if (phantom.is_fail(status)):
            return action_result.get_status()

        if (search_field_name or search_value) and not (search_field_name and search_value):
            return action_result.set_status(phantom.APP_ERROR, 'Need both the field name and the search value to search')

        if (results_filter_dict or results_filter_operator or results_filter_equality) \
                and not (results_filter_dict and results_filter_operator and results_filter_equality):
            return action_result.set_status(phantom.APP_ERROR,
                                     'Need results filter json, results filter operator and results filter equality to filter the results')

        self.proxy.excluded_fields = [x.lower().strip() for x in self.get_config().get('exclude_fields', '').split(',')]
        records = self.proxy.find_records(app, search_field_name, search_value, max_count)

        self.save_progress("Filtering records...")
        if results_filter_dict:
            filtered_records = self.filter_records(results_filter_dict, results_filter_operator, results_filter_equality, records)
        else:
            filtered_records = records

        if filtered_records:
            for r in filtered_records:
                action_result.add_data(r)
            action_result.set_status(phantom.APP_SUCCESS, 'Tickets retrieved')
            action_result.update_summary({'records_found': len(filtered_records)})
        else:
            filter_msg = ''
            if search_field_name and search_value:
                filter_msg = ' with field {} containing value {}'.format(search_field_name, search_value)
            if results_filter_dict:
                if filter_msg != '':
                    filter_msg = '{} and results filter json'.format(filter_msg)
                else:
                    filter_msg = ' with results filter json'

            action_result.set_status(phantom.APP_SUCCESS, 'Found no tickets for {}{}'.format(app, filter_msg))
            action_result.update_summary({'records_found': 0})

        return action_result.get_status()

    def _handle_create_attachment(self, action_result, param):
        self.debug_print("In action create attachment...")
        vault_id = param['vault_id']
        name_of_file = param.get('file_name')
        endpoint = consts.ARCHER_CREATE_ATTACHMENT_ENDPOINT
        container = self.get_container_id()

        try:
            success, message, info = vault.vault_info(
                vault_id=vault_id, container_id=container)
            if success:
                file_path = info[0]['path']
                file_name = name_of_file if name_of_file else info[0]['name']
                with open(file_path, 'rb') as file_object:
                    attachment_data = file_object.read()
                    attachment_bytes = base64.encodebytes(attachment_data)
            else:
                return action_result.set_status(phantom.APP_ERROR, message)

            data = {
                'AttachmentName': file_name,
                'AttachmentBytes': attachment_bytes
            }
            try:
                response = archer_utils.ArcherAPISession._rest_call(self.proxy, endpoint, 'post', data)
                response = json.loads(response)
            except Exception:
                return action_result.set_status(phantom.APP_ERROR,
                                                consts.ARCHER_ERR_ACTION_EXECUTION.format(self.get_action_identifier(), response))
            if response['IsSuccessful']:
                action_result.add_data({'Attachment_ID': response['RequestedObject']['Id']})
                action_result.set_status(phantom.APP_SUCCESS, 'Attachment created successfully')
            else:
                action_result.set_status(phantom.APP_ERROR, response['ValidationMessages'][0]['ResourcedMessage'])
        except Exception as e:
            err = self._get_error_message_from_exception(e)
            action_result.set_status(phantom.APP_ERROR, 'Error: {}'.format(err))

        return action_result.get_status()

    def filter_records(self, results_filter_dict, results_filter_operator, results_filter_equality, records):
        filtered_records = []

        if results_filter_operator == 'and':
            and_dict_len = len(results_filter_dict)
            for record in records:
                and_dict_count = 0
                for field in record['Field']:
                    for k, v in results_filter_dict.items():
                        try:
                            if results_filter_equality == 'equals':
                                if field['@name'] == k and v.lower() == field['#text'].lower():
                                    and_dict_count = and_dict_count + 1
                            else:
                                if field['@name'] == k and v.lower() in field['#text'].lower():
                                    and_dict_count = and_dict_count + 1
                        except Exception:
                            continue
                if and_dict_count >= and_dict_len:
                    filtered_records.append(record)

        elif results_filter_operator == 'or':
            for record in records:
                next_record = False
                for field in record['Field']:
                    for k, v in results_filter_dict.items():
                        try:
                            if results_filter_equality == 'equals':
                                if field['#text'] and field['@name'] == k and v.lower() == field['#text'].lower():
                                    filtered_records.append(record)
                                    next_record = True
                                    break
                            else:
                                if field['#text'] and field['@name'] == k and v.lower() in field['#text'].lower():
                                    filtered_records.append(record)
                                    next_record = True
                                    break
                        except Exception:
                            continue
                    if next_record:
                        break

        return filtered_records

    def _handle_get_report(self, action_result, param):
        """Handles 'get_report' actions"""
        self.save_progress('Get Archer report...')
        guid = param['guid']
        max_count = param.get('max_results', 100)
        max_pages = param.get('max_pages', 10)
        results_filter_json = param.get('results_filter_json')
        try:
            if results_filter_json:
                results_filter_dict = json.loads(results_filter_json)
            else:
                results_filter_dict = None
        except Exception as e:
            msg = consts.ARCHER_ERR_VALID_JSON
            self.debug_print(msg)
            err = self._get_error_message_from_exception(e)
            return action_result.set_status(phantom.APP_ERROR, msg, err)

        if results_filter_dict and not isinstance(results_filter_dict, dict):
            return action_result.set_status(phantom.APP_ERROR, consts.ARCHER_INVALID_JSON)

        results_filter_operator = param.get('results_filter_operator')
        results_filter_equality = param.get('results_filter_equality')
        if results_filter_operator:
            results_filter_operator = results_filter_operator.lower()
        if results_filter_equality:
            results_filter_equality = results_filter_equality.lower()

        if results_filter_operator:
            if results_filter_operator.lower() not in consts.ARCHER_OPERATOR_VALUELIST:
                return action_result.set_status(phantom.APP_ERROR,
                    f'Please enter a valid value for results_filter_operator from {consts.ARCHER_OPERATOR_VALUELIST}')
            else:
                results_filter_operator = results_filter_operator.lower()
        else:
            if results_filter_dict:
                if len(results_filter_dict) == 1 and not results_filter_operator:
                    results_filter_operator = "and"
        if results_filter_equality:
            if results_filter_equality.lower() not in consts.ARCHER_EQUALITY_VALUELIST:
                return action_result.set_status(phantom.APP_ERROR,
                    f'Please enter a valid value for results_filter_equality from {consts.ARCHER_EQUALITY_VALUELIST}')
            else:
                results_filter_equality = results_filter_equality.lower()

        status, max_count = self._validate_integer(action_result, max_count, 'max_result', False)
        if (phantom.is_fail(status)):
            return action_result.get_status()

        status, max_pages = self._validate_integer(action_result, max_pages, 'max_pages', False)
        if (phantom.is_fail(status)):
            return action_result.get_status()

        if (results_filter_dict or results_filter_operator or results_filter_equality) \
                and not (results_filter_dict and results_filter_operator and results_filter_equality):
            return action_result.set_status(phantom.APP_ERROR,
                                     'Need results filter json, results filter operator and results filter equality to filter the results')

        try:
            result_dict = self.proxy.get_report_by_id(guid, max_count, max_pages)
            if result_dict['status'] != 'success':
                return action_result.set_status(phantom.APP_ERROR, result_dict['message'])

            records = result_dict['records']

            self.save_progress("Filtering records...")
            if results_filter_dict:
                filtered_records = self.filter_records(results_filter_dict, results_filter_operator, results_filter_equality, records)
            else:
                filtered_records = records

            if filtered_records:
                for r in filtered_records:
                    action_result.add_data(r)
                action_result.set_status(phantom.APP_SUCCESS, 'Tickets retrieved')
                action_result.update_summary({'records_found': len(filtered_records)})
                action_result.update_summary({'pages_found': result_dict['page_count']})
            else:
                if results_filter_dict:
                    filter_msg = ' with results filter json'
                else:
                    filter_msg = ''

                action_result.set_status(phantom.APP_SUCCESS, 'Found no tickets{}'.format(filter_msg))
                action_result.update_summary({'records_found': 0})
                action_result.update_summary({'pages_found': result_dict['page_count']})

        except Exception as e:
            action_result.set_status(phantom.APP_ERROR,
                                     'Error handling get report action - e = {}'.format(e))

        return action_result.get_status()

    def _handle_assign_ticket(self, action_result, param):
        self.debug_print("In action handler for assign ticket...")

        # Required values can be accessed directly
        application = param['application']

        # Optional values should use the .get() function
        name_field = param.get('name_field')
        users = param.get('users')
        field_id = param.get('field_id')
        name_value = param.get('name_value')
        groups = param.get('groups')
        content_id = param.get('content_id')
        lid = self.proxy.get_levelId_for_app(application)
        if lid is None:
            return action_result.set_status(phantom.APP_ERROR, "Error: Could not identify application {}".format(application))

        if not content_id:
            if name_field and name_value:
                content_id = self.proxy.get_content_id(application, name_field, name_value)
            else:
                return action_result.set_status(phantom.APP_ERROR, 'Either content ID or both name field and name value are mandatory')
            if not content_id:
                return action_result.set_status(phantom.APP_ERROR,
                                    'Error: Could not find record "{}". "{}" may not be a tracking ID field in app "{}"'
                                    .format(name_value, name_field, application))

        if not users and not groups:
            return action_result.set_status(phantom.APP_ERROR, "Please provide either a users or groups.")

        action_result.update_summary({'content_id': content_id})

        try:
            field_id = int(field_id)
        except (ValueError, TypeError):
            field_id = self.proxy.get_fieldId_for_content_and_name(content_id, field_id)
            if field_id is None:
                return action_result.set_status(phantom.APP_ERROR, "Can't resolve field for application {}".format(application))

        group_list_data = []
        user_list_data = []
        field_def = {}
        field_def['Value'] = {}
        field_def['FieldId'] = field_id
        field_def['Type'] = 8

        fields = {}
        fields[str(field_id)] = field_def
        contentDetails = {}
        contentDetails["LevelId"] = lid
        contentDetails["Id"] = content_id
        contentDetails["FieldContents"] = fields

        assign_ticket_request = {}
        assign_ticket_request['Content'] = contentDetails
        try:
            if groups:
                temp_groups_list = groups.split(",")
                for value in temp_groups_list:
                    strip_group_value = value.strip()
                    if "" == strip_group_value:
                        return action_result.set_status(phantom.APP_ERROR, "Please provide valid value of groups.")
                    group_list_data.append({"Id": strip_group_value})
                field_def['Value']['GroupList'] = group_list_data

            if users:
                temp_users_list = users.split(",")
                for value in temp_users_list:
                    strip_user_value = value.strip()
                    if "" == strip_user_value:
                        return action_result.set_status(phantom.APP_ERROR, "Please provide valid value of users.")
                    user_list_data.append({"Id": strip_user_value})
                field_def['Value']['UserList'] = user_list_data
        except Exception as e:
            error_message = self._get_error_message_from_exception(e)
            return action_result.set_status(phantom.APP_ERROR, "Error while parsing users/groups. {}".format(error_message))

        self.debug_print("assign_ticket_request: {}".format(assign_ticket_request))

        # make REST call
        try:
            r = archer_utils.ArcherAPISession._rest_call(self.proxy, consts.ARCHER_UPDATE_CONTENT_ENDPOINT, 'put', assign_ticket_request)
            r = json.loads(r)
        except Exception:
            return action_result.set_status(phantom.APP_ERROR, consts.ARCHER_ERR_ACTION_EXECUTION.format(self.get_action_identifier(), r))

        # Add response to action_result for troubleshooting purposes
        action_result.add_data(r)

        try:
            if r["IsSuccessful"]:
                action_result.set_status(phantom.APP_SUCCESS, 'Groups/Users successfully assigned')
            else:
                action_result.set_status(phantom.APP_ERROR, 'Action failed. Groups/Users not assigned.')
        except Exception as e:
            error_message = self._get_error_message_from_exception(e)
            action_result.set_status(phantom.APP_ERROR, 'Action failed. {}'.format(error_message))

        return action_result.get_status()

    def _handle_attach_alert(self, action_result, param):
        self.debug_print("In attach alert action...")

        # Required values can be accessed directly
        application = param['application']
        security_alert_id = param['security_alert_id']

        # Optional values should use the .get() function
        name_field = param.get('name_field')
        field_id = param.get('field_id')
        name_value = param.get('name_value')
        content_id = param.get('content_id')
        lid = self.proxy.get_levelId_for_app(application)

        if lid is None:
            return action_result.set_status(phantom.APP_ERROR, "Error: Could not identify application {}".format(application))

        if not content_id:
            if name_field and name_value:
                content_id = self.proxy.get_content_id(application, name_field, name_value)
            else:
                return action_result.set_status(phantom.APP_ERROR, 'Either content ID or both name field and name value are mandatory')
            if not content_id:
                return action_result.set_status(phantom.APP_ERROR,
                                    'Error: Could not find record "{}". "{}" may not be a tracking ID field in app "{}"'
                                    .format(name_value, name_field, application))

        action_result.update_summary({'content_id': content_id})

        try:
            field_id = int(field_id)
        except (ValueError, TypeError):
            field_id = self.proxy.get_fieldId_for_content_and_name(content_id, "Security Alerts")
            if field_id is None:
                return action_result.set_status(phantom.APP_ERROR, "Can't resolve field for application {}".format(application))

        fields = {}
        field_def = {}
        field_def['FieldId'] = field_id
        field_def['Type'] = 23

        security_alert_id = [x.strip() for x in security_alert_id.split(",")]

        record = self.proxy.get_record_by_id(application, content_id)

        # Gathers any existing security alerts in the incident. Blank if not popualted yet. Used for duplicate incidents
        security_alerts = archer_utils.get_record_field(record, "Security Alerts")

        record = None
        try:
            # Gets any existing security alerts in security incident
            record = security_alerts['Record']
        except Exception as e:
            error_message = self._get_error_message_from_exception(e)
            self.debug_print("Error while getting any existing security alerts in security incident. {}".format(error_message))

        # If there are any existing security alerts in the incident, add them to the beginning of the list of alerts to add. If not, skip.
        if record:
            if isinstance(record, dict):
                record = [record]
            for i in range(len(record)):
                for k, v in record[i].items():
                    if k == "@id" and str(v) not in security_alert_id:
                        security_alert_id.insert(0, str(v))

        # Must be in list form
        field_def['Value'] = security_alert_id

        fields[str(field_id)] = field_def
        contentDetails = {}
        contentDetails["LevelId"] = lid
        contentDetails["Id"] = str(content_id)
        contentDetails["FieldContents"] = fields

        sec_alert_request = {}
        sec_alert_request['Content'] = contentDetails

        # make REST call
        try:
            r = archer_utils.ArcherAPISession._rest_call(self.proxy, consts.ARCHER_UPDATE_CONTENT_ENDPOINT, 'put', sec_alert_request)
            r = json.loads(r)
        except Exception:
            return action_result.set_status(phantom.APP_ERROR, consts.ARCHER_ERR_ACTION_EXECUTION.format(self.get_action_identifier(), r))

        # Add response data to action result for troubleshooting purposes
        action_result.add_data(r)

        try:
            if r["IsSuccessful"]:
                action_result.set_status(phantom.APP_SUCCESS, 'Alert successfully attached to Incident')
            else:
                action_result.set_status(phantom.APP_ERROR, 'Action failed. Alert not attached to Incident.')
        except Exception as e:
            error = self._get_error_message_from_exception(e)
            action_result.set_status(phantom.APP_ERROR, error)

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
            elif (action_id == consts.ARCHER_ACTION_LIST_TICKETS):
                return self._handle_list_tickets(action_result, param)
            elif (action_id == phantom.ACTION_ID_TEST_ASSET_CONNECTIVITY):
                return self._handle_test_connectivity(action_result, param)
            elif (action_id == consts.ARCHER_ACTION_ON_POLL):
                return self._handle_on_poll(action_result, param)
            elif (action_id == consts.ARCHER_ACTION_CREATE_ATTACHMENT):
                return self._handle_create_attachment(action_result, param)
            elif (action_id == consts.ARCHER_ACTION_GET_REPORT):
                return self._handle_get_report(action_result, param)
            elif (action_id == consts.ARCHER_ACTION_ASSIGN_TICKET):
                return self._handle_assign_ticket(action_result, param)
            elif (action_id == consts.ARCHER_ACTION_ATTACH_ALERT):
                return self._handle_attach_alert(action_result, param)
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
