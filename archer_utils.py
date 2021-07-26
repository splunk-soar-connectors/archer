# --
# File: archer_utils.py
#
# Copyright (c) 2016-2021 Splunk Inc.
#
# SPLUNK CONFIDENTIAL - Use or disclosure of this material in whole or in part
# without a valid written license from Splunk Inc. is PROHIBITED.
#
# --

"""Do things with the RSA Archer APIs.  There are two: a RESTful one and a SOAP
    one.  There are some things that can only be done in one or the other.  So
    we use them both as necessary.
"""

import sys
import json
import functools
import xmltodict
import requests
from lxml import etree
from bs4 import UnicodeDammit

from archer_soap import ArcherSOAP


last_message_length = 0


def W(msg):
    """Console-based status updater."""
    global last_message_length
    sys.stderr.write('\b' * last_message_length)
    sys.stderr.write(' ' * last_message_length)
    sys.stderr.write('\b' * last_message_length)
    msg = '--[ {}'.format(msg.strip())
    last_message_length = len(msg)
    sys.stderr.write(msg)


def memoize(f):
    """Naive memoizer, since Python2's functools doesn't have a memoizer.

        TODO: persistence would vastly improve performance, but we'll want a
            mechanism to clear the cache when the schema changes upstream.
    """
    cache = {}

    @functools.wraps(f)
    def cache_on_delivery(*args):
        if args not in cache:
            cache[args] = f(*args)
        return cache[args]
    return cache_on_delivery


def get_record_field(record, field):
    """Utility to return the field (as OrderedDict) with the given name in the
        given record.  Returns None if the field isn't found.
    """
    W('Getting field {} from record {}'.format(field, record))
    if 'Record' in record:
        record = record['Record']
    for f in record['Field']:
        if f.get('@name', None) == field:
            W('--- got {}'.format(f))
            return f
    W('--- got nothing!')
    return None


class ArcherAPISession(object):
    """Keeps state and simplifies Archer Web Service (SOAP) interactions."""

    sessionTimeout = 60  # Generate a new token after this much time unused
    BLACKLIST_TYPES = (24, 25)

    def __init__(self, base_url, userName, password, instanceName, pythonVerison, usersDomain):
        """Initializes an API session.

            base, a string: base endpoint for the Archer APIs.  E.g.,
                http://1.2.3.4
            user, a string: userName for authentication
            password, a string: password for authentication
            instance, a string: Archer instanceName (e.g., 'Default')
        """
        self.base_url = base_url
        self.userName = userName
        self.password = password
        self.instanceName = instanceName
        self.sessionToken = None
        self.sessionLastUse = 0
        self.verifySSL = True
        self.excluded_fields = []
        self.headers = {'Accept': 'application/json,text/html,'
                                  'application/xhtml+xml,application/xml;'
                                  'q=0.9,*/*;q=0.8',
                        'Content-Type': 'application/json'}
        self.asoap = None
        self.python_version = pythonVerison
        self.users_domain = usersDomain

    def _handle_py_ver_compat_for_input_str(self, input_str):
        """
        This method returns the encoded|original string based on the Python version.
        :param input_str: Input string to be processed
        :return: input_str (Processed input string based on following logic 'input_str - Python 3; encoded input_str - Python 2')
        """

        try:
            if input_str and self.python_version == 2:
                input_str = UnicodeDammit(input_str).unicode_markup.encode('utf-8')
        except:
            W("Error occurred while handling python 2to3 compatibility for the input string")

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
                    error_code = "Error code unavailable"
                    error_msg = e.args[0]
            else:
                error_code = "Error code unavailable"
                error_msg = "Error message unavailable. Please check the asset configuration and|or action parameters."
        except:
            error_code = "Error code unavailable"
            error_msg = "Error message unavailable. Please check the asset configuration and|or action parameters."

        try:
            error_msg = self._handle_py_ver_compat_for_input_str(error_msg)
        except TypeError:
            error_msg = "Error occurred while connecting to the Archer server. Please check the asset configuration and|or the action parameters."
        except:
            error_msg = "Error message unavailable. Please check the asset configuration and|or action parameters."

        if error_code in "Error code unavailable":
            error_text = "Error Message: {0}".format(error_msg)
        else:
            error_text = "Error Code: {0}. Error Message: {1}".format(error_code, error_msg)

        return error_text

    def get_token(self):
        if not self.asoap:
            self.asoap = ArcherSOAP(self.base_url, self.userName, self.password, self.instanceName, verify_cert=self.verifySSL,
                         usersDomain=self.users_domain, pythonVersion=self.python_version)
        return self.asoap.session

    def _rest_call(self, ep, meth='GET', data={}):
        """Utility to make a REST API call."""
        hdrs = self.headers.copy()
        hdrs.update({'X-Http-Method-Override': meth})
        hdrs.update({'Authorization': 'Archer session-id="{}"'.format(
                self.get_token())})
        url = '{}{}'.format(self.base_url, ep)
        r = requests.post(url, headers=hdrs, json=data, verify=self.verifySSL)
        r.raise_for_status
        try:
            r = r.content.decode()
        except (UnicodeDecodeError, AttributeError):
            return r.text
        return r

    @memoize
    def get_fieldId_for_content_and_name(self, cid, fname):
        """Returns ID of the field with the given name in the given record.
            Return None if not found.
        """
        W('Getting fieldId for {} in record {}'.format(fname, cid))
        j = json.loads(self._rest_call('/api/core/content/{}'.format(cid)))
        if not('RequestedObject' in j and 'FieldContents' in j['RequestedObject']):
            return None
        for fid in j['RequestedObject']['FieldContents']:
            j2 = json.loads(self._rest_call(
                    '/api/core/system/fielddefinition/{}'.format(fid)))
            n = j2['RequestedObject']['Name']
            W('...matching "{}" == "{}"'.format(fname, n))
            if n == fname:
                id_ = j2['RequestedObject']['Id']
                W('...Matched!  Returning ID {}'.format(id_))
                return id_
        W('...NO MATCH!  Returning None')
        return None

    @memoize
    def get_fieldId_for_app_and_name(self, mid, fname):
        """Returns ID of the field with the given name in the given module.
            `mid` will be interpreted as app_name, level_id, then app_id.
            Return None if not found.
        """
        W('Getting fieldId for {} in module {}'.format(mid, fname))
        try:
            mid = int(mid)
        except (ValueError, TypeError):
            mid = self.get_levelId_for_app(mid)
            W('Got level id: {}'.format(mid))
            flds = self.get_fields_for_level(mid)
        else:
            flds = self.get_fields_for_level(mid)
            if not flds[0]['IsSuccessful']:
                W('No fields for level {}'.format(mid))
                mid = self.get_levelId_for_app(mid)
                W('Got level id: {}'.format(mid))
                flds = self.get_fields_for_level(mid)
        if type(flds) != list:
            return None
        if not flds[0]['IsSuccessful']:
            W('No fields for level {}, returning None'.format(mid))
            return None
        for fld in flds:
            if fld['RequestedObject']['Name'] == fname:
                W('Found a match!')
                return fld['RequestedObject']['Id']
        W('Found no match')
        return None

    def get_module_name(self, mid):
        """Returns the name of the given module."""
        try:
            int(mid)
        except (ValueError, TypeError):
            if self.get_moduleid(mid):
                return mid
            else:
                return None
        mid = str(mid)
        for a in self.get_applications():
            if mid == a['RequestedObject']['Id']:
                return a['RequestedObject']['Name']
        return None

    @memoize
    def get_applications(self):
        """Return an array of all modules/apps"""
        return json.loads(self._rest_call('/api/core/system/application'))

    def get_moduleid(self, name):
        """Return the ID of the Archer module/app with the given name.  Returns
            None if the module name isn't found.
        """
        for j in self.get_applications():
            if name in (j['RequestedObject'][x] for x in ('Name', 'Alias')):
                return j['RequestedObject']['Id']
        return None

    @memoize
    def get_fields_for_level(self, levelId):
        """Return array of fields for the given level"""
        return json.loads(self._rest_call(
                '/api/core/system/fielddefinition/level/{}'.format(levelId)))

    @memoize
    def get_levelId_for_app(self, name):
        """Return the ID of the base level for the named module/app.  Returns
            None if the module's name or level isn't found.

            name, a string-or-number: Module ID or name
        """
        try:
            mid = int(name)
        except (ValueError, TypeError):
            mid = self.get_moduleid(name)
        if mid is None:
            return None
        j = self._rest_call('/api/core/system/level/module/{}'.format(mid))
        j = json.loads(j)[0]
        if not j['IsSuccessful']:
            return None
        return j['RequestedObject']['Id']

    def concatenate_list_data(self, fv_list):
        """Concatenates list values and create string"""
        result = ''
        for element in fv_list:
            result += str(element)
        return result

    @memoize
    def get_field_details(self, fieldId):
        """Returns details about the field with the given ID."""
        r = self._rest_call('/api/core/system/fielddefinition/{}'.format(
                fieldId))
        return json.loads(r)['RequestedObject']

    def get_content_id(self, app, field_name, field_value):
        try:
            fid = int(field_name)
        except (ValueError, TypeError):
            try:
                fid = self.get_fieldId_for_app_and_name(app, field_name)
            except Exception as e:
                err = self._get_error_message_from_exception(e)
                raise Exception('Failed to find field "{}" in "{}": {}'.format(field_name, app, err))
        modid = self.get_moduleid(app)

        if not field_value:
            raise TypeError('Either content id or Tracking ID field and record name are required')
        fv = filter(lambda x: x.isdigit(), field_value)
        if self.python_version == 3:
            fv = self.concatenate_list_data(list(fv))
        if not fv:
            return None
        fv = int(fv)

        if not self.asoap:
            self.asoap = ArcherSOAP(self.base_url, self.userName, self.password, self.instanceName, self.sessionToken,
                     verify_cert=self.verifySSL, usersDomain=self.users_domain, pythonVersion=self.python_version)
        records = self.asoap.find_records(modid, app, fid, field_name, fv, filter_type='numeric')
        # should only get one
        if records:
            return records[0].get('contentId')
        return None

    def get_name_of_field(self, fieldId):
        """Returns the name of the field with the given ID."""
        return self.get_field_details(fieldId)['Name']

    def get_level_of_field(self, fieldId):
        """Returns the level of the field with the given ID."""
        return self.get_field_details(fieldId)['LevelId']

    def get_type_of_field(self, fieldId):
        """Returns the type of the field with the given ID."""
        return self.get_field_details(fieldId)['Type']

    def get_valuesetvalue_of_field(self, fieldId, value):
        """Returns the value set appropriately to update the given filedId

            TODO: support subforms
        """
        fld = self.get_field_details(fieldId)
        if fld['Type'] not in (4, 23, 8, 6):
            return value
        if fld['Type'] in (4, 6):
            W('Valufying "{}" as values-list field {}'.format(value, fld))
            vlid = fld['RelatedValuesListId']
            vlval, othertext = self.get_valueslistvalue_id(vlid, value)
            if not vlval:
                raise Exception('Failed to set valueslist field '
                                'vlid:{}/val:{}'.format(vlid, value))
            return {'value_id': vlval, 'other_text': othertext}
        if fld['Type'] == 8:
            if not self.asoap:
                self.asoap = ArcherSOAP(self.base_url, self.userName, self.password, self.instanceName, self.sessionToken,
                         verify_cert=self.verifySSL, usersDomain=self.users_domain, pythonVersion=self.python_version)
            uid = self.asoap.find_user(value)
            if not uid:
                W("User not found in local user search")
                duid = self.asoap.find_domain_user(value)
                if not duid:
                    W("User not found in domain user search")
                    raise Exception('Failed to find user "{}"'.format(value))
                W("Domain User ID: {}".format(duid))
                return duid
            W("User ID: {}".format(uid))
            return uid
        W('Valufying "{}" as cross-reference field {}'.format(value, fld))
        try:
            value = int(value)
        except (ValueError, TypeError):
            W('Cross-reference values must be integers: {}'.format(value))
            return None
        # refrecs = self.get_referenced_records(fld.get('ReferencedFieldId'))
        refrecs = self.get_referenced_records(fld.get('Id'))
        if refrecs:
            rec = [x['Id'] for x in refrecs if x['SequentialId'] == value]
            if len(rec) != 1:
                W('Zero or multiple referenced records found by SeqId: '
                  '{} in reference records: {}'.format(rec, refrecs))
                with open('/tmp/this.json', 'w') as of:
                    json.dump(refrecs, of)
            else:
                W('Cross-reference is a Sequential ID: {}'.format(value))
                return rec[0]
        content = self._rest_call('/api/core/content/{}'.format(value), 'GET')
        if json.loads(content)['IsSuccessful']:
            W('Cross-reference is a content ID: {}'.format(value))
            return value
        raise Exception('Failed to set Cross-Reference field '
                        'vlid:{}/val:{}'.format(vlid, value))

    def get_referenced_records(self, rfid):
        """Returns records that could be linked by the given reference field"""
        j = json.loads(self._rest_call(
                '/api/core/content/referencefield/{}'.format(rfid), 'GET'))
        if 'Message' in j or not j[0]['IsSuccessful']:
            W('Failed to get referenced records for rfid {}'.format(rfid))
            return None
        return [x['RequestedObject'] for x in j]

    @memoize
    def get_valueslist(self, vlid):
        """Returns the ValuesList with the give Id"""
        j = json.loads(self._rest_call(
            '/api/core/system/valueslistvalue/flat/valueslist/{}'.format(vlid),
            'GET'))
        if 'Message' in j:
            W('Error getting valueslist {}: {}'.format(vlid, j['Message']))
            return None
        return [x['RequestedObject'] for x in j]

    def get_value(self, value):
        """
        Returns value as per the returned datatype
        """
        if not isinstance(value, str):
            return value
        return UnicodeDammit(value).unicode_markup.lower()

    def get_valueslistvalue_id(self, vlid, value):
        """Returns (ValueId,OtherText) for the given value in the given
            valuelist, matched by Name/Alias/NumericValue/Description/ID.  If
            the value doesn't match a valueid in the valueslist, we'll look
            for an "other" field who's name/alias/etc is matched as the part of
            value before the first ':' - in which case that's the valueid
            returned, and OtherText is set to the value with prefix removed.

            Case-insensitive match.
        """
        values = self.get_valueslist(vlid)
        match_flds = ('Name', 'Alias', 'NumericValue', 'Description', 'Id')
        lval = str(value).lower()
        for v in values:
            W('Comparing {} and {}'.format(lval, v))
            if lval in (self.get_value(v[x]) for x in match_flds if v[x]):
                return v['Id'], None
        if ':' in value:
            vname, vval = value.split(':', 1)
            vname = vname.lower()
            for other in (x for x in values if x['EnableOtherText']):
                if vname in (self.get_value(other[x]) for x in match_flds
                             if other[x]):
                    return other['Id'], vval
        W('No valueslistvalue found for vlid:{} and value:{}'.format(
                vlid, value))
        return None, None

    def get_content_by_id(self, cid):
        """Returns the full record with the given id."""
        j = json.loads(self._rest_call('/api/core/content/{}'.format(cid),
                                       'GET'))
        if not j['IsSuccessful']:
            W('Failed to fetch record with cid {}: {}'.format(
                    cid, j['ValidationMessages'][0]['ResourcedMessage']))
            return None
        return j['RequestedObject']

    def _get_field_id_map(self, app):
        mid = self.get_moduleid(app)

        levelid = self.get_levelId_for_app(mid)
        q_fields = self.get_fields_for_level(levelid)
        if not q_fields or type(q_fields) != list or type(q_fields[0]) != dict or 'RequestedObject' not in q_fields[0]:
            raise Exception('Could not find any fields for application "{}". Please verify the application is correct.'.format(app))
        fields = {}
        for f in q_fields:
            try:
                ftype = int(f['RequestedObject']['Type'])
                if ftype not in (1, 2, 3, 4, 6, 8, 9, 11, 19, 20, 21, 22, 23, 26, 27, 29, 1001):
                    W('Unexpected field type {} trying anyway: {}'.format(ftype, json.dumps(f)))
                if f['RequestedObject']['Name'].lower() in self.excluded_fields:
                    W('Skipping {}'.format(f['RequestedObject']['Name']))
                    continue
                elif ftype not in self.BLACKLIST_TYPES:
                    fields[int(f['RequestedObject']['Id'])] = f['RequestedObject']['Name']
                else:
                    W('unable to parse field {}, type {}: {}'.format(f['RequestedObject']['Name'], f['RequestedObject']['Type'], json.dumps(f)))
            except Exception as e:
                err = self._get_error_message_from_exception(e)
                W('Failed to parse: {}: {}'.format(f, err))
        return fields

    def get_records(self, app, field_name, value, max_count, mid, fid, fields, comparison=None, sort=None, page=1):
        records = []

        num_iterations = max_count // 1000
        rem_count = max_count % 1000
        if rem_count != 0:
            num_iterations = num_iterations + 1

        for iter_count in range(num_iterations):
            records_req = 1000
            if rem_count != 0 and iter_count == num_iterations - 1:
                records_req = rem_count

            if comparison is None:
                lst_records = self.asoap.find_records(mid, app, fid, field_name, value, filter_type='text',
                            max_count=records_req, fields=fields, comparison=comparison, sort=sort, page=page)
                if lst_records:
                    records.extend(lst_records)
            if not lst_records:
                try:
                    lst_inter_records = self.asoap.find_records(mid, app, fid, field_name, int(value), filter_type='numeric',
                            max_count=records_req, fields=fields, comparison=comparison, sort=sort, page=page)
                    if lst_inter_records:
                        records.extend(lst_inter_records)
                    else:
                        break
                except (TypeError, ValueError):
                    pass  # Not looking up numerically

        return records

    def find_records(self, app, field_name, value, max_count, comparison=None, sort=None, page=1):
        fid = None
        err = ""

        try:
            fid = int(field_name)
        except (ValueError, TypeError):
            try:
                fid = self.get_fieldId_for_app_and_name(app, field_name)
            except Exception as e:
                err = self._get_error_message_from_exception(e)
                pass
        if field_name and value and not fid:
            raise Exception('Failed to find field "{}" in "{}": {}'.format(field_name, app, err))
        mid = self.get_moduleid(app)
        fields = self._get_field_id_map(app)

        if not self.asoap:
            self.asoap = ArcherSOAP(self.base_url, self.userName, self.password, self.instanceName, self.get_token(),
                     verify_cert=self.verifySSL, usersDomain=self.users_domain, pythonVersion=self.python_version)

        records = self.get_records(app, field_name, value, max_count, mid, fid, fields, comparison, sort, page)
        if not records:
            return records

        recs = etree.Element('Records')
        document = etree.ElementTree(recs)
        for r in records:
            recs.append(r)
        rec_xml = etree.tostring(document, pretty_print=True)

        rec_dict = records and xmltodict.parse(rec_xml) or {}
        records = rec_dict.get('Records', {}).get('Record')
        # remove blanks and add readable name
        if not records:
            return []

        if not isinstance(records, list):
            records = [records]

        for r in records:
            cur_fields = r.get('Field', [])
            new_fields = []
            for f in cur_fields:
                try:
                    t = f.get('#text')
                    if t:
                        f['@name'] = fields.get(int(f['@id']), f['@id'])
                        new_fields.append(f)
                    elif f.get('@type') == '4':
                        f['@name'] = fields.get(int(f['@id']), f['@id'])
                        value_list = f.get('ListValues', {}).get('ListValue', {})
                        if value_list:
                            if isinstance(value_list, dict):
                                value_list = [value_list]
                            value_list = set([ x.get('#text', '') for x in value_list])
                            v = f.get('@value')
                            if v:
                                value_list.add(v)
                            f['multi_value'] = list(value_list)
                            f['#text'] = ', '.join(f['multi_value'])
                        else:
                            f['#text'] = None
                        new_fields.append(f)
                except Exception as e:
                    err = self._get_error_message_from_exception(e)
                    W('Failed to parse {}: {}'.format(f, err))
            r['Field'] = new_fields

        return records

    def get_record_by_id(self, app, contentId, cl=None):
        """Returns the full record with the given id."""
        fields = self._get_field_id_map(app)
        moduleId = self.get_moduleid(app)

        if not self.asoap:
            self.asoap = ArcherSOAP(self.base_url, self.userName, self.password, self.instanceName,
                     verify_cert=self.verifySSL, usersDomain=self.users_domain, pythonVersion=self.python_version)
        data = self.asoap.get_record(contentId, moduleId)

        rec_dict = xmltodict.parse(data) or {}

        rec_dict['@moduleId'] = moduleId
        rec_dict['@contentId'] = contentId
        empty_name_count = 0
        for i, field in enumerate(rec_dict['Record']['Field']):
            try:
                field_type = int(field.get('@type'))
                field['@name'] = fields.get(int(field.get('@id')))
                if field['@name'] is None:
                    empty_name_count += 1
                if field.get('@value', '').startswith('<p>'):
                    field['@value'] = field['@value'][3:-4]
                if field_type in self.BLACKLIST_TYPES:
                    W('Skpping field (unsupported type): {}'.format(field))
                    continue
                if field_type == 4:
                    value_list = field.get('MultiValue', [])
                    if value_list:
                        value_list = set([ x.get('@value', '') for x in value_list ])
                        value_list.add(field.get('@value'))
                        field['multi_value'] = list(value_list)
            except Exception as e:
                err = self._get_error_message_from_exception(e)
                W('Failed to parse {}: {}'.format(field, err))
        # All name fields should not be None for valid record
        if empty_name_count == len(rec_dict['Record']['Field']):
            W('Failed to get name field. Check input parameters')
            raise Exception('Failed to get name field. Check input parameters')
        return rec_dict

    def create_record(self, app, data={}):
        """Create a new record at the given level with the given data.

            data has fieldId/value pairs with which to call `update_record`.
        """
        W('In create_record({},{})'.format(app, data))

        W('Crafting data for new record...')
        moduleId = self.get_moduleid(app)
        fields = []

        levelid = self.get_levelId_for_app(moduleId)
        q_fields = self.get_fields_for_level(levelid)
        if not q_fields or type(q_fields) != list or type(q_fields[0]) != dict or 'RequestedObject' not in q_fields[0]:
            raise Exception('Could not find any fields for application "{}". Please verify the application is correct.'.format(app))
        field_data = {}
        for f in q_fields:
            try:
                ftype = int(f['RequestedObject']['Type'])
                field_data[f['RequestedObject']['Name']] = {'id': int(f['RequestedObject']['Id']), 'type': ftype}
            except Exception as e:
                err = self._get_error_message_from_exception(e)
                W('Failed to parse: {}: {}'.format(f, err))
        for field, value in list(data.items()):
            fd = field_data.get(field)
            if not fd:
                raise Exception('Could not identify field {}'.format(field))
            value = self.get_valuesetvalue_of_field(fd['id'], value)

            field = {'value': value}
            field.update(fd)
            fields.append(field)

        if not self.asoap:
            self.asoap = ArcherSOAP(self.base_url, self.userName, self.password, self.instanceName,
                     verify_cert=self.verifySSL, usersDomain=self.users_domain, pythonVersion=self.python_version)
        cid = self.asoap.create_record(moduleId, fields)
        return cid

    def update_record(self, app, contentId, fieldId, value, doit=True):
        """Set the value of the given field in the given content record.

            contentId, a number-or-string: ID of the Archer record to update,
                or the ID/name of the App in which to find the fieldId.  Note
                that the latter case can only work with doit=False

            fieldId, a string-or-number: ID or name of the field to update
                within the given Archer record

            value, a string-or-number: value to which the given field in the
                given Archer record will be set

            doit, a boolean: whether to actually issue the update command.  If
                False, return the data that would have been sent.

            TODO: accept multiple field/value pairs for efficiency
        """
        W('In update_record({}, {}, {})'.format(contentId, fieldId, value))
        try:
            fieldId = int(fieldId)
            W('fieldId is integer, using as-is: {}'.format(fieldId))
        except (ValueError, TypeError):
            newId = self.get_fieldId_for_app_and_name(app, fieldId)
            W('Got fieldId from app_and_name: {}'.format(newId))
            if newId is None:
                raise Exception("Can't resolve field: {}".format(fieldId))
            elif doit:
                raise Exception("Can't update without content_id")
            fieldId = newId

        fieldType = int(self.get_type_of_field(fieldId))
        W('Got fieldType: {}'.format(fieldType))
        levelId = self.get_level_of_field(fieldId)
        W('Got levelId: {}'.format(levelId))
        value = self.get_valuesetvalue_of_field(fieldId, value)
        moduleId = self.get_moduleid(app)

        if not self.asoap:
            self.asoap = ArcherSOAP(self.base_url, self.userName, self.password, self.instanceName, verify_cert=self.verifySSL,
                     pythonVersion=self.python_version)
        field = {
           'id': fieldId,
           'type': fieldType,
           'value': value
        }
        W('Updating to value: {}'.format(value))
        W('Updating to id: {}'.format(fieldId))
        W('Updating to type: {}'.format(fieldType))
        data = self.asoap.update_record(contentId, moduleId, [field])
        W(data)
        return bool(data)
