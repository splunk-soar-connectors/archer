# File: archer_utils.py
#
# Copyright (c) 2016-2025 Splunk Inc.
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
"""Do things with the RSA Archer APIs.  There are two: a RESTful one and a SOAP
one.  There are some things that can only be done in one or the other.  So
we use them both as necessary.
"""

import functools
import json
import sys

import requests
import xmltodict
from bs4 import UnicodeDammit
from lxml import etree

import archer_consts as consts
from archer_soap import ArcherSOAP


last_message_length = 0


def W(msg):
    """Console-based status updater."""
    global last_message_length
    sys.stderr.write("\b" * last_message_length)
    sys.stderr.write(" " * last_message_length)
    sys.stderr.write("\b" * last_message_length)
    msg = f"--[ {msg.strip()}"
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
    W(f"Getting field {field} from record {record}")
    if "Record" in record:
        record = record["Record"]
    for f in record["Field"]:
        if f.get("@name", None) == field:
            W(f"--- got {f}")
            return f
    W("--- got nothing!")
    return None


class ArcherAPISession:
    """Keeps state and simplifies Archer Web Service (SOAP) interactions."""

    BLACKLIST_TYPES = (24, 25)

    def __init__(self, base_url, userName, password, instanceName, usersDomain, verify_ssl, obj):
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
        self.conn_obj = obj
        self.verifySSL = verify_ssl
        self.excluded_fields = []
        self.headers = {
            "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Content-Type": "application/json",
        }
        self.users_domain = usersDomain
        self.asoap = ArcherSOAP(
            self.base_url,
            self.userName,
            self.password,
            self.instanceName,
            verify_cert=self.verifySSL,
            usersDomain=self.users_domain,
            conn_obj=obj,
        )

    def _get_error_message_from_exception(self, e):
        """
        Get appropriate error message from the exception.
        :param e: Exception object
        :return: error message
        """

        error_code = None
        error_msg = consts.ERR_MSG_UNAVAILABLE

        self.conn_obj.error_print("Error occurred.", e)

        try:
            if hasattr(e, "args"):
                if len(e.args) > 1:
                    error_code = e.args[0]
                    error_msg = e.args[1]
                elif len(e.args) == 1:
                    error_msg = e.args[0]
        except Exception as e:
            self.error_print(f"Error occurred while fetching exception information. Details: {e!s}")

        if not error_code:
            error_text = f"Error Message: {error_msg}"
        else:
            error_text = f"Error Code: {error_code}. Error Message: {error_msg}"

        return error_text

    def get_token(self):
        self.asoap._authenticate()

    def _rest_call(self, ep, meth="get", data={}):
        hdrs = self.headers.copy()
        hdrs.update({"X-Http-Method-Override": meth})
        hdrs.update({"Authorization": f'Archer session-id="{self.conn_obj.sessionToken}"'})
        url = f"{self.base_url}{ep}"

        request_func = getattr(requests, meth)
        if data:
            r = request_func(
                url,
                headers=hdrs,
                json=data,
                verify=self.verifySSL,  # nosemgrep: python.requests.best-practice.use-timeout.use-timeout
            )
        else:
            r = request_func(url, headers=hdrs, verify=self.verifySSL)  # nosemgrep: python.requests.best-practice.use-timeout.use-timeout
        if r.status_code == consts.ARCHER_UNAUTHORIZED_USER:
            self.get_token()
            return self._rest_call(ep, meth, data)
        r.raise_for_status
        try:
            r = r.content.decode() or r.reason
        except (UnicodeDecodeError, AttributeError):
            return r.text or r.reason
        return r

    @memoize
    def get_fieldId_for_content_and_name(self, cid, fname):
        """Returns ID of the field with the given name in the given record.
        Return None if not found.
        """
        W(f"Getting fieldId for {fname} in record {cid}")
        j = json.loads(self._rest_call(f"/api/core/content/{cid}"))
        if not ("RequestedObject" in j and "FieldContents" in j["RequestedObject"]):
            return None
        for fid in j["RequestedObject"]["FieldContents"]:
            j2 = json.loads(self._rest_call(f"/api/core/system/fielddefinition/{fid}"))
            n = j2["RequestedObject"]["Name"]
            W(f'...matching "{fname}" == "{n}"')
            if n == fname:
                id_ = j2["RequestedObject"]["Id"]
                W(f"...Matched!  Returning ID {id_}")
                return id_
        W("...NO MATCH!  Returning None")
        return None

    @memoize
    def get_fieldId_for_app_and_name(self, mid, fname):
        """Returns ID of the field with the given name in the given module.
        `mid` will be interpreted as app_name, level_id, then app_id.
        Return None if not found.
        """
        W(f"Getting fieldId for {mid} in module {fname}")
        try:
            mid = int(mid)
        except (ValueError, TypeError):
            mid = self.get_levelId_for_app(mid)
            W(f"Got level id: {mid}")
            flds = self.get_fields_for_level(mid)
        else:
            flds = self.get_fields_for_level(mid)
            if not flds[0]["IsSuccessful"]:
                W(f"No fields for level {mid}")
                mid = self.get_levelId_for_app(mid)
                W(f"Got level id: {mid}")
                flds = self.get_fields_for_level(mid)
        if type(flds) is not list:
            return None
        if not flds[0]["IsSuccessful"]:
            W(f"No fields for level {mid}, returning None")
            return None
        for fld in flds:
            if fld["RequestedObject"]["Name"] == fname:
                W("Found a match!")
                return fld["RequestedObject"]["Id"]
        W("Found no match")
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
            if mid == a["RequestedObject"]["Id"]:
                return a["RequestedObject"]["Name"]
        return None

    @memoize
    def get_applications(self):
        """Return an array of all modules/apps"""
        return json.loads(self._rest_call("/api/core/system/application"))

    def get_moduleid(self, name):
        """Return the ID of the Archer module/app with the given name.  Returns
        None if the module name isn't found.
        """
        for j in self.get_applications():
            if name in (j["RequestedObject"][x] for x in ("Name", "Alias")):
                return j["RequestedObject"]["Id"]
        return None

    @memoize
    def get_fields_for_level(self, levelId):
        """Return array of fields for the given level"""
        return json.loads(self._rest_call(f"/api/core/system/fielddefinition/level/{levelId}"))

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
        j = self._rest_call(f"/api/core/system/level/module/{mid}")
        j = json.loads(j)[0]
        if not j["IsSuccessful"]:
            return None
        return j["RequestedObject"]["Id"]

    def concatenate_list_data(self, fv_list):
        """Concatenates list values and create string"""
        result = ""
        for element in fv_list:
            result += str(element)
        return result

    @memoize
    def get_field_details(self, fieldId):
        """Returns details about the field with the given ID."""
        r = self._rest_call(f"/api/core/system/fielddefinition/{fieldId}")
        return json.loads(r)["RequestedObject"]

    def get_content_id(self, app, field_name, field_value):
        try:
            fid = int(field_name)
        except (ValueError, TypeError):
            try:
                fid = self.get_fieldId_for_app_and_name(app, field_name)
            except Exception as e:
                err = self._get_error_message_from_exception(e)
                raise Exception(f'Failed to find field "{field_name}" in "{app}": {err}')
        modid = self.get_moduleid(app)

        if not field_value:
            raise TypeError("Either content id or Tracking ID field and record name are required")
        fv = filter(lambda x: x.isdigit(), field_value)
        fv = self.concatenate_list_data(list(fv))
        if not fv:
            return None
        fv = int(fv)

        records = self.asoap.find_records(modid, app, fid, field_name, fv, filter_type="numeric")
        # should only get one
        if records:
            return records[0].get("contentId")
        return None

    def get_name_of_field(self, fieldId):
        """Returns the name of the field with the given ID."""
        return self.get_field_details(fieldId)["Name"]

    def get_level_of_field(self, fieldId):
        """Returns the level of the field with the given ID."""
        return self.get_field_details(fieldId)["LevelId"]

    def get_type_of_field(self, fieldId):
        """Returns the type of the field with the given ID."""
        return self.get_field_details(fieldId)["Type"]

    def get_valuesetvalue_of_field(self, fieldId, value):
        """Returns the value set appropriately to update the given filedId

        TODO: support subforms
        """
        fld = self.get_field_details(fieldId)

        if fld["Type"] not in (4, 8, 6):
            return value

        if fld["Type"] in (4, 6):
            W(f'Valufying "{value}" as values-list field {fld}')
            vlid = fld["RelatedValuesListId"]
            vlval, othertext = self.get_valueslistvalue_id(vlid, value)
            if not vlval:
                raise Exception(f"Failed to set valueslist field vlid:{vlid}/val:{value}")
            return {"value_id": vlval, "other_text": othertext}

        if fld["Type"] == 8:
            if value and isinstance(value, str):
                value = [x.strip() for x in value.split(",")]
            user_id = []
            group_id = []
            for val in value:
                uid = self.asoap.find_user(val)
                gid = self.asoap.find_group(val)
                group_id.append(gid)
                user_id.append(uid)
                if not uid and not gid:
                    W("Users/Groups not found in local user search")
                    duid = self.asoap.find_domain_user(val)
                    user_id.append(duid)
                    if not duid:
                        W("Users/Groups not found in domain user search")
                        raise Exception(f"Failed to find Users/Groups {val}")

            return [user_id, group_id]

        W(f'Valufying "{value}" as cross-reference field {fld}')

        try:
            value = int(value)
        except (ValueError, TypeError):
            W(f"Cross-reference values must be integers: {value}")
            return None
        # refrecs = self.get_referenced_records(fld.get('ReferencedFieldId'))
        refrecs = self.get_referenced_records(fld.get("Id"))
        if refrecs:
            rec = [x["Id"] for x in refrecs if x["SequentialId"] == value]
            if len(rec) != 1:
                W(f"Zero or multiple referenced records found by SeqId: {rec} in reference records: {refrecs}")
                with open("/tmp/this.json", "w") as of:
                    json.dump(refrecs, of)
            else:
                W(f"Cross-reference is a Sequential ID: {value}")
                return rec[0]
        content = self._rest_call(f"/api/core/content/{value}", "get")
        if json.loads(content)["IsSuccessful"]:
            W(f"Cross-reference is a content ID: {value}")
            return value
        raise Exception(f"Failed to set Cross-Reference field vlid:{vlid}/val:{value}")

    def get_referenced_records(self, rfid):
        """Returns records that could be linked by the given reference field"""
        j = json.loads(self._rest_call(f"/api/core/content/referencefield/{rfid}", "get"))
        if "Message" in j or not j[0]["IsSuccessful"]:
            W(f"Failed to get referenced records for rfid {rfid}")
            return None
        return [x["RequestedObject"] for x in j]

    @memoize
    def get_valueslist(self, vlid):
        """Returns the ValuesList with the give Id"""
        j = json.loads(self._rest_call(f"/api/core/system/valueslistvalue/flat/valueslist/{vlid}", "get"))
        if "Message" in j:
            W("Error getting valueslist {}: {}".format(vlid, j["Message"]))
            return None
        return [x["RequestedObject"] for x in j]

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
        match_flds = ("Name", "Alias", "NumericValue", "Description", "Id")
        vlid = []

        if isinstance(value, list):
            lval = [str(x.lower()) for x in value]
        elif isinstance(value, dict):
            lval = value
        else:
            lval = [str(value.lower())]

        if values:
            for val in values:
                for lv in lval:
                    if lv in (self.get_value(val[y]) for y in match_flds if val[y]):
                        W(f"Get value : {self.get_value(val['Id'])}")
                        vlid.append(val["Id"])
                        break

            return vlid, None

        if ":" in value:
            vname, vval = value.split(":", 1)
            vname = vname.lower()
            for other in (x for x in values if x["EnableOtherText"]):
                if vname in (self.get_value(other[x]) for x in match_flds if other[x]):
                    W(f"get_valueslistvalue_id other['Id'] {other['Id']}")
                    return other["Id"], vval
        W(f"No valueslistvalue found for vlid:{vlid} and value:{value}")
        return None, None

    def get_content_by_id(self, cid):
        """Returns the full record with the given id."""
        j = json.loads(self._rest_call(f"/api/core/content/{cid}", "get"))
        if not j["IsSuccessful"]:
            W("Failed to fetch record with cid {}: {}".format(cid, j["ValidationMessages"][0]["ResourcedMessage"]))
            return None
        return j["RequestedObject"]

    def _get_field_id_map(self, app):
        mid = self.get_moduleid(app)

        levelid = self.get_levelId_for_app(mid)
        q_fields = self.get_fields_for_level(levelid)
        if not q_fields or type(q_fields) is not list or type(q_fields[0]) is not dict or "RequestedObject" not in q_fields[0]:
            raise Exception(f'Could not find any fields for application "{app}". Please verify the application is correct.')
        fields = {}
        for f in q_fields:
            try:
                ftype = int(f["RequestedObject"]["Type"])
                if ftype not in (1, 2, 3, 4, 6, 8, 9, 11, 19, 20, 21, 22, 23, 26, 27, 29, 1001):
                    W(f"Unexpected field type {ftype} trying anyway: {json.dumps(f)}")
                if f["RequestedObject"]["Name"].lower() in self.excluded_fields:
                    W("Skipping {}".format(f["RequestedObject"]["Name"]))
                    continue
                elif ftype not in self.BLACKLIST_TYPES:
                    fields[int(f["RequestedObject"]["Id"])] = f["RequestedObject"]["Name"]
                else:
                    W("unable to parse field {}, type {}: {}".format(f["RequestedObject"]["Name"], f["RequestedObject"]["Type"], json.dumps(f)))
            except Exception as e:
                err = self._get_error_message_from_exception(e)
                W(f"Failed to parse: {f}: {err}")
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
                lst_records = self.asoap.find_records(
                    mid,
                    app,
                    fid,
                    field_name,
                    value,
                    filter_type="text",
                    max_count=records_req,
                    fields=fields,
                    comparison=comparison,
                    sort=sort,
                    page=page,
                )
                if lst_records:
                    records.extend(lst_records)
            if not lst_records:
                try:
                    lst_inter_records = self.asoap.find_records(
                        mid,
                        app,
                        fid,
                        field_name,
                        int(value),
                        filter_type="numeric",
                        max_count=records_req,
                        fields=fields,
                        comparison=comparison,
                        sort=sort,
                        page=page,
                    )
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
            raise Exception(f'Failed to find field "{field_name}" in "{app}": {err}')
        mid = self.get_moduleid(app)
        fields = self._get_field_id_map(app)

        records = self.get_records(app, field_name, value, max_count, mid, fid, fields, comparison, sort, page)
        if not records:
            return records

        recs = etree.Element("Records")
        document = etree.ElementTree(recs)
        for r in records:
            recs.append(r)
        rec_xml = etree.tostring(document, pretty_print=True)

        rec_dict = (records and xmltodict.parse(rec_xml)) or {}
        records = rec_dict.get("Records", {}).get("Record")
        # remove blanks and add readable name
        if not records:
            return []

        if not isinstance(records, list):
            records = [records]

        for r in records:
            cur_fields = r.get("Field", [])
            new_fields = []
            for f in cur_fields:
                try:
                    t = f.get("#text")
                    if t:
                        f["@name"] = fields.get(int(f["@id"]), f["@id"])
                        new_fields.append(f)
                    elif f.get("@type") == "4":
                        f["@name"] = fields.get(int(f["@id"]), f["@id"])
                        value_list = f.get("ListValues", {}).get("ListValue", {})
                        if value_list:
                            if isinstance(value_list, dict):
                                value_list = [value_list]
                            value_list = set(x.get("#text", "") for x in value_list)
                            v = f.get("@value")
                            if v:
                                value_list.add(v)
                            f["multi_value"] = list(value_list)
                            f["#text"] = ", ".join(f["multi_value"])
                        else:
                            f["#text"] = None
                        new_fields.append(f)
                except Exception as e:
                    err = self._get_error_message_from_exception(e)
                    W(f"Failed to parse {f}: {err}")
            r["Field"] = new_fields

        return records

    def get_record_by_id(self, app, contentId, cl=None):
        """Returns the full record with the given id."""
        fields = self._get_field_id_map(app)
        moduleId = self.get_moduleid(app)

        data = self.asoap.get_record(contentId, moduleId)

        rec_dict = xmltodict.parse(data) or {}

        rec_dict["@moduleId"] = moduleId
        rec_dict["@contentId"] = contentId
        empty_name_count = 0
        for i, field in enumerate(rec_dict["Record"]["Field"]):
            try:
                field_type = int(field.get("@type"))
                field["@name"] = fields.get(int(field.get("@id")))
                if field["@name"] is None:
                    empty_name_count += 1
                if field.get("@value", "").startswith("<p>"):
                    field["@value"] = field["@value"][3:-4]
                if field_type in self.BLACKLIST_TYPES:
                    W(f"Skpping field (unsupported type): {field}")
                    continue
                if field_type == 4:
                    value_list = field.get("MultiValue", [])
                    if value_list:
                        value_list = set(x.get("@value", "") for x in value_list)
                        value_list.add(field.get("@value"))
                        field["multi_value"] = list(value_list)
            except Exception as e:
                err = self._get_error_message_from_exception(e)
                W(f"Failed to parse {field}: {err}")
        # All name fields should not be None for valid record
        if empty_name_count == len(rec_dict["Record"]["Field"]):
            W("Failed to get name field. Check input parameters")
            raise Exception("Failed to get name field. Check input parameters")
        return rec_dict

    def create_record(self, app, data={}):
        """Create a new record at the given level with the given data.

        data has fieldId/value pairs with which to call `update_record`.
        """
        W(f"In create_record({app},{data})")

        W("Crafting data for new record...")
        moduleId = self.get_moduleid(app)
        fields = []

        levelid = self.get_levelId_for_app(moduleId)
        q_fields = self.get_fields_for_level(levelid)
        if not q_fields or type(q_fields) is not list or type(q_fields[0]) is not dict or "RequestedObject" not in q_fields[0]:
            raise Exception(f'Could not find any fields for application "{app}". Please verify the application is correct.')
        field_data = {}
        for f in q_fields:
            try:
                ftype = int(f["RequestedObject"]["Type"])
                field_data[f["RequestedObject"]["Name"]] = {"id": int(f["RequestedObject"]["Id"]), "type": ftype}
            except Exception as e:
                err = self._get_error_message_from_exception(e)
                W(f"Failed to parse: {f}: {err}")
        for field, value in list(data.items()):
            fd = field_data.get(field)
            if not fd:
                raise Exception(f"Could not identify field {field}")
            value = self.get_valuesetvalue_of_field(fd["id"], value)

            field = {"value": value}
            field.update(fd)
            fields.append(field)
        cid = self.asoap.create_record(moduleId, fields)
        return cid

    def update_record(self, app, contentId, fieldId, value, doit=True):
        W(f"In update_record({contentId}, {fieldId}, {value})")
        data = {}
        moduleId, field = self.get_data(app, fieldId, value, doit)
        data = self.asoap.update_record(contentId, moduleId, [field])
        W(data)
        return bool(data)

    def get_data(self, app, fieldId, value, doit=True):
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

        """
        W(f"In get_data({fieldId}, {value})")
        try:
            fid = int(fieldId)
        except (ValueError, TypeError):
            fid = self.get_fieldId_for_app_and_name(app, fieldId)

        try:
            fieldId = int(fid)
            W(f"fieldId is integer, using as-is: {fieldId}")
        except (ValueError, TypeError):
            newId = self.get_fieldId_for_app_and_name(app, fieldId)
            W(f"Got fieldId from app_and_name: {newId}")
            if newId is None:
                raise Exception(f"Can't resolve field: {fieldId}")
            elif doit:
                raise Exception("Can't update without content_id")
            fieldId = newId

        fieldType = int(self.get_type_of_field(fieldId))
        W(f"Got fieldType: {fieldType}")
        levelId = self.get_level_of_field(fieldId)
        W(f"Got levelId: {levelId}")
        value = self.get_valuesetvalue_of_field(fieldId, value)
        moduleId = self.get_moduleid(app)

        field = {"id": fieldId, "type": fieldType, "value": value}
        W(f"Updating to value: {value}")
        W(f"Updating to id: {fieldId}")
        W(f"Updating to type: {fieldType}")

        return moduleId, field

    def update_record_by_json(self, app, contentId, data=None, doit=True):
        if data is None:
            data = {}
        fields = []

        for field, value in list(data.items()):
            moduleId, field = self.get_data(app, field, value, doit)
            fields.append(field)

        data = self.asoap.update_record(contentId, moduleId, fields)
        return bool(data)

    def get_report_by_id(self, guid, max_count, max_pages):
        """Returns the report with the given guid."""

        # Initialize result dictionary
        result_dict = {"status": "failed", "message": "Failed - default message", "page_count": 0, "records": []}

        # Initialize the current count of records
        total_count = 0

        # Try to loop through report pages until no records are returned, max pages reached,
        # or max number of record results reached
        try:
            for page_number in range(1, max_pages + 1):
                # Try to get current report page
                try:
                    data_dict = self.asoap.get_report(guid, page_number)
                    if data_dict["status"] != "success":
                        result_dict["message"] = data_dict["result"]
                        return result_dict
                    data = data_dict["result"]

                except Exception as e:
                    result_dict["message"] = f"Failed to get page {page_number} of report. Check input parameters are valid. e = {e}"
                    return result_dict

                # Try to parse current report page from xml to a dictionary
                try:
                    if data is None:
                        raw_dict = {}
                    else:
                        raw_dict = xmltodict.parse(data) or {}
                except Exception as e:
                    result_dict["message"] = f"Failed to parse report page {page_number} to dict - e = {e}"
                    return result_dict

                # Try to get tickets/records from current report page
                try:
                    try:
                        raw_records = raw_dict["Records"]["Record"]
                        num_raw_records = len(raw_records)
                    except:
                        num_raw_records = 0

                    # If no report records were found in the current
                    # page, assume all records have been found
                    if num_raw_records < 1:
                        result_dict["status"] = "success"
                        if len(result_dict["records"]) < 1:
                            result_dict["message"] = "No report tickets found"
                        else:
                            result_dict["message"] = "Report retrieved"
                            result_dict["page_count"] = page_number - 1
                        return result_dict

                except Exception as e:
                    result_dict["message"] = f"Failed to get tickets from report page {page_number} - {e}"
                    return result_dict

                # Try to get field definitions for current report page
                try:
                    field_defs = raw_dict["Records"]["Metadata"]["FieldDefinitions"]["FieldDefinition"]

                except Exception as e:
                    result_dict["message"] = f"Failed to get field definitions for report page {page_number} - e = {e}"
                    return result_dict

                # Merge the field definitions with the record/ticket data for the current report page
                merge_dict = self.merge_field_defs(field_defs, raw_records, max_count, total_count, page_number)
                result_dict["records"].extend(merge_dict["records"])
                total_count = len(result_dict["records"])
                if merge_dict["status"] == "max records reached":
                    result_dict["status"] = "success"
                    result_dict["page_count"] = page_number
                    result_dict["message"] = merge_dict["message"]
                    return result_dict
                elif merge_dict["status"] != "success":
                    result_dict["message"] = merge_dict["message"]
                    return result_dict

            result_dict["status"] = "success"
            result_dict["message"] = "Report retrieved"
            result_dict["page_count"] = page_number
            return result_dict

        except Exception as e:
            result_dict["status"] = "failed"
            result_dict["message"] = f"Failed while getting report page(s) - e = {e}"
            return result_dict

    def merge_field_defs(self, field_defs, raw_records, max_count, total_count, page_number):
        try:
            # Initialize result dictionary
            merge_dict = {"status": "failed", "message": "Failed - default message", "records": []}

            if not isinstance(raw_records, list):
                raw_records = [raw_records]

            for raw_record in raw_records:
                # Initialize field variables and increment the total record count
                valid_name_count = 0
                new_fields = []
                total_count = total_count + 1

                # Merge the field definitions into the current record
                for field in raw_record["Field"]:
                    try:
                        field_id = int(field.get("@id"))
                        field_name = None
                        for field_def in field_defs:
                            if field_id == int(field_def.get("@id")):
                                field_name = str(field_def.get("@name"))
                                break
                        if field_name is not None:
                            valid_name_count += 1
                        field["@name"] = field_name
                        field_type = int(field.get("@type"))
                        if field_type == 4:
                            value_list = field.get("ListValues", {}).get("ListValue", {})
                            if value_list:
                                if isinstance(value_list, dict):
                                    value_list = [value_list]
                                value_list = set(x.get("#text", "") for x in value_list)
                                v = field.get("@value")
                                if v:
                                    value_list.add(v)
                                field["multi_value"] = list(value_list)
                                field["#text"] = ", ".join(field["multi_value"])
                        elif field_type == 8:
                            value_list = field.get("Users", {}).get("User", {})
                            if value_list:
                                if isinstance(value_list, dict):
                                    value_list = [value_list]
                                value_list = set([self.process_user_multivalue(x) for x in value_list])
                                v = field.get("@value")
                                if v:
                                    value_list.add(v)
                                field["multi_value"] = list(value_list)
                                field["#text"] = ", ".join(field["multi_value"])
                        elif field_type == 9:
                            field["#text"] = field.get("Reference", {}).get("#text", "")

                    except Exception as e:
                        err = self._get_error_message_from_exception(e)
                        W(f"Failed to parse {field}: {err}")
                        field["@name"] = None
                    new_fields.append(field)

                # If none of the name fields were merged, return fail
                if valid_name_count < 1:
                    merge_dict["message"] = "Failed to merge any field name(s). Check Archer report configuration"
                    return merge_dict

                # Append merged record to the results record dictionary
                raw_record["Field"] = new_fields
                merge_dict["records"].append(raw_record)

                # If the record count is reached, return
                if total_count >= max_count:
                    merge_dict["status"] = "max records reached"
                    merge_dict["message"] = "Report retrieved - max results reached"
                    return merge_dict

            merge_dict["status"] = "success"
            merge_dict["message"] = "Report retrieved"
            return merge_dict

        except Exception as e:
            merge_dict["message"] = f"Failed to merge field definitions with report page {page_number} ticket data - e = {e}"
            return merge_dict

    def process_user_multivalue(self, x):
        firstname = x.get("@firstName", "")
        middlename = x.get("@middleName", "")
        lastname = x.get("@lastName", "")
        name = firstname
        if middlename != "":
            name = f"{name} {middlename}"
        if lastname != "":
            name = f"{name} {lastname}"
        return name
