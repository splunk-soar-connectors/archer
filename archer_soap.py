# File: archer_soap.py
#
# Copyright (c) 2016-2026 Splunk Inc.
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
from io import BytesIO

import requests
from bs4 import UnicodeDammit
from lxml import etree

import archer_consts
from archer_auth import ArcherAPIError, ArcherPermissionError, request_failure_reason


SOAPNS = "http://schemas.xmlsoap.org/soap/envelope/"
XSINS = "http://www.w3.org/2001/XMLSchema-instance"
XSDNS = "http://www.w3.org/2001/XMLSchema"
ARCHERNS = "http://archer-tech.com/webservices/"

NS_MAP = {
    "soap": SOAPNS,
    "xsi": XSINS,
    "xsd": XSDNS,
}

ARCHER_MAP = {
    None: ARCHERNS,
}

ALL_NS_MAP = NS_MAP.copy()
ALL_NS_MAP["dummy"] = ARCHERNS

DEBUG = False
MAX_XML_RESPONSE_BYTES = 10 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 30
RESPONSE_CHUNK_BYTES = 64 * 1024


def parse_untrusted_xml(xml_data):
    if isinstance(xml_data, str):
        xml_data = xml_data.encode("utf-8")
    if len(xml_data) > MAX_XML_RESPONSE_BYTES:
        raise ValueError("Archer XML response exceeds the 10 MiB safety limit")
    if b"<!DOCTYPE" in xml_data.upper():
        raise ValueError("Archer XML responses must not contain a DTD")
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
    )
    document = etree.parse(BytesIO(xml_data), parser=parser)
    if document.docinfo.doctype:
        raise ValueError("Archer XML responses must not contain a DTD")
    return document


def read_bounded_response(response):
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            content_length = int(content_length)
        except ValueError:
            content_length = None
        if content_length is not None and content_length > MAX_XML_RESPONSE_BYTES:
            raise ValueError("Archer XML response exceeds the 10 MiB safety limit")

    body = bytearray()
    for chunk in response.iter_content(chunk_size=RESPONSE_CHUNK_BYTES):
        if not chunk:
            continue
        if len(body) + len(chunk) > MAX_XML_RESPONSE_BYTES:
            raise ValueError("Archer XML response exceeds the 10 MiB safety limit")
        body.extend(chunk)
    return bytes(body)


class ArcherSOAP:
    def __init__(self, host, username, password, instance, verify_cert=True, usersDomain=None, conn_obj=None):
        self.base_uri = host + "/ws"
        self.username = username
        self.password = password
        self.instance = instance
        self.verify_cert = verify_cert
        self.users_domain = usersDomain
        self.conn_obj = conn_obj
        self.auth = conn_obj.auth
        if not self.auth.is_pat and not self.auth.session_token:
            self._authenticate()

    def _authenticate(self):
        if self.auth.is_pat:
            raise ArcherAPIError("Password login is unavailable when PAT authentication is selected")
        doc, body = self._generate_xml_stub()

        if self.users_domain:
            return self._domain_user_authenticate()

        n = etree.SubElement(body, "CreateUserSessionFromInstance", nsmap=ARCHER_MAP)
        un = etree.SubElement(n, "userName")
        un.text = self.username
        inn = etree.SubElement(n, "instanceName")
        inn.text = self.instance
        p = etree.SubElement(n, "password")
        p.text = self.password
        sess_doc = self._do_request(self.base_uri + "/general.asmx", doc)
        sess_root = sess_doc.getroot()
        result = sess_root.xpath(archer_consts.ARCHER_XPATH_AUTH, namespaces=ALL_NS_MAP)
        if result:
            self.auth.session_token = result[0].text
            self.auth.token
            return
        raise ArcherAPIError("Archer SOAP password authentication failed")

    def _domain_user_authenticate(self):
        if self.auth.is_pat:
            raise ArcherAPIError("Password login is unavailable when PAT authentication is selected")
        doc, body = self._generate_xml_stub()

        n = etree.SubElement(body, "CreateDomainUserSessionFromInstance", nsmap=ARCHER_MAP)
        un = etree.SubElement(n, "userName")
        un.text = self.username
        inn = etree.SubElement(n, "instanceName")
        inn.text = self.instance
        p = etree.SubElement(n, "password")
        p.text = self.password
        p = etree.SubElement(n, "usersDomain")
        p.text = self.users_domain
        sess_doc = self._do_request(self.base_uri + "/general.asmx", doc)
        sess_root = sess_doc.getroot()
        result = sess_root.xpath(archer_consts.ARCHER_XPATH_DOMAIN_USER_AUTH, namespaces=ALL_NS_MAP)
        if result:
            self.auth.session_token = result[0].text
            self.auth.token
            return
        raise ArcherAPIError("Archer SOAP domain authentication failed")

    def find_group(self, groupname):
        doc, body = self._generate_xml_stub()
        lu = etree.SubElement(body, "LookupGroup", nsmap=ARCHER_MAP)
        to = etree.SubElement(lu, "sessionToken")
        to.text = self.auth.token
        u = etree.SubElement(lu, "keyword")
        u.text = groupname
        resp_doc = self._do_request(self.base_uri + "/accesscontrol.asmx", doc)
        resp_root = resp_doc.getroot()
        result = resp_root.xpath(archer_consts.ARCHER_XPATH_GROUP, namespaces=ALL_NS_MAP)
        for name_element in result:
            if name_element.text == groupname:
                for node in name_element.itersiblings(tag="Id"):
                    return int(node.text)

        result = resp_root.xpath(archer_consts.ARCHER_XPATH_GROUP_OTHER, namespaces=ALL_NS_MAP)
        if result and result[0].text:
            inner_document = parse_untrusted_xml(result[0].text)
            for group in inner_document.xpath("//*[local-name()='Group']"):
                names = group.xpath("./*[local-name()='Name']")
                identifiers = group.xpath("./*[local-name()='Id']")
                if names and identifiers and names[0].text == groupname:
                    return int(identifiers[0].text)

        return

    def find_user(self, username):
        doc, body = self._generate_xml_stub()
        lu = etree.SubElement(body, "LookupUserId", nsmap=ARCHER_MAP)
        to = etree.SubElement(lu, "sessionToken")
        to.text = self.auth.token
        u = etree.SubElement(lu, "username")
        u.text = username
        resp_doc = self._do_request(self.base_uri + "/accesscontrol.asmx", doc)
        resp_root = resp_doc.getroot()
        result = resp_root.xpath("/soap:Envelope/soap:Body/dummy:LookupUserIdResponse/dummy:LookupUserIdResult", namespaces=ALL_NS_MAP)
        if result:
            return int(result[0].text)
        return

    def find_domain_user(self, username):
        doc, body = self._generate_xml_stub()
        lu = etree.SubElement(body, "LookupDomainUserId", nsmap=ARCHER_MAP)
        to = etree.SubElement(lu, "sessionToken")
        to.text = self.auth.token
        u = etree.SubElement(lu, "username")
        u.text = username
        u = etree.SubElement(lu, "usersDomain")
        u.text = self.users_domain
        resp_doc = self._do_request(self.base_uri + "/accesscontrol.asmx", doc)
        resp_root = resp_doc.getroot()
        result = resp_root.xpath(
            "/soap:Envelope/soap:Body/dummy:LookupDomainUserIdResponse/dummy:LookupDomainUserIdResult", namespaces=ALL_NS_MAP
        )
        if result:
            return int(result[0].text)
        return

    def find_records(
        self, mod_id, mod_name, key_id, key_name, value, filter_type="text", max_count=1000, fields=None, comparison="Equals", sort=None, page=1
    ):
        if fields is None:
            fields = {key_id: key_name}
        doc, body = self._generate_xml_stub()
        se = etree.SubElement(body, "ExecuteSearch", nsmap=ARCHER_MAP)
        to = etree.SubElement(se, "sessionToken")
        to.text = self.auth.token
        pn = etree.SubElement(se, "pageNumber")
        pn.text = str(page)
        so = etree.SubElement(se, "searchOptions")

        sr = etree.Element("SearchReport")
        report_doc = etree.ElementTree(sr)

        ps = etree.SubElement(sr, "PageSize")
        ps.text = str(max_count)
        dfs = etree.SubElement(sr, "DisplayFields")
        for field_id, field_name in list(fields.items()):
            df = etree.SubElement(dfs, "DisplayField")
            df.text = str(field_id)
            df.set("name", UnicodeDammit(field_name).unicode_markup.encode("ascii", "xmlcharrefreplace"))

        cr = etree.SubElement(sr, "Criteria")
        if not comparison:
            if filter_type == "numeric":
                comparison = "Equals"
            else:
                comparison = "Contains"
        if value is not None and value != "":
            fi = etree.SubElement(cr, "Filter")
            co = etree.SubElement(fi, "Conditions")
            if filter_type == "numeric":
                fc = etree.SubElement(co, "NumericFilterCondition")
                op = etree.SubElement(fc, "Operator")
                op.text = comparison
            else:
                fc = etree.SubElement(co, "TextFilterCondition")
                op = etree.SubElement(fc, "Operator")
                op.text = comparison
            fi = etree.SubElement(fc, "Field")
            fi.text = str(key_id)
            v = etree.SubElement(fc, "Value")
            v.text = str(value)

        mc = etree.SubElement(cr, "ModuleCriteria")
        m = etree.SubElement(mc, "Module")
        if sort:
            sfs = etree.SubElement(mc, "SortFields")
            sf = etree.SubElement(sfs, "SortField")
            sfid = etree.SubElement(sf, "Field")
            sfid.text = str(key_id)
            sft = etree.SubElement(sf, "SortType")
            sft.text = sort
        m.set("name", mod_name)
        m.text = str(mod_id)

        so.text = etree.tostring(report_doc, pretty_print=True)

        resp_doc = self._do_request(self.base_uri + "/search.asmx", doc)

        resp_root = resp_doc.getroot()
        result = resp_root.xpath("/soap:Envelope/soap:Body/dummy:ExecuteSearchResponse/dummy:ExecuteSearchResult", namespaces=ALL_NS_MAP)

        if not result:
            return []

        search_result = parse_untrusted_xml(result[0].text)
        return search_result.xpath("/Records/Record")

    def get_record(self, content_id, module_id):
        doc, body = self._generate_xml_stub()
        gr = etree.SubElement(body, "GetRecordById", nsmap=ARCHER_MAP)
        to = etree.SubElement(gr, "sessionToken")
        to.text = self.auth.token
        mi = etree.SubElement(gr, "moduleId")
        mi.text = str(module_id)
        ci = etree.SubElement(gr, "contentId")
        ci.text = str(content_id)
        resp_doc = self._do_request(self.base_uri + "/record.asmx", doc)
        resp_root = resp_doc.getroot()
        rec_xml = resp_root.xpath("/soap:Envelope/soap:Body/dummy:GetRecordByIdResponse/dummy:GetRecordByIdResult", namespaces=ALL_NS_MAP)

        return rec_xml[0].text

    def plain_field(self, field, parent):
        f = etree.SubElement(parent, "Field")

        # Try the original code to set the field value, if it fails let the library have a go at it, if that also fails, the action will fail
        try:
            f.set("value", str(field["value"]))
        except:
            f.set("value", field["value"])

        f.set("id", str(field["id"]))

    def mv_field(self, field, parent):
        f = etree.SubElement(parent, "Field")
        values = field["value"]
        o = None
        if isinstance(values, dict):
            o = field.get("other_text")
            values = values["value_id"]

        if isinstance(values, list):
            f.set("value", str(values[0]))
            for v in values[1:]:
                mv = etree.SubElement(f, "MultiValue")
                mv.set("value", str(v))
        else:
            f.set("value", str(values))

        f.set("id", str(field["id"]))
        f.set("type", str(field["type"]))
        if o:
            f.set("othertext", str(o))

    def user_field(self, field, parent):
        user_id, group_id = field["value"]
        f = etree.SubElement(parent, "Field")
        f.set("id", str(field["id"]))
        if user_id:
            u = etree.SubElement(f, "Users")
            if isinstance(user_id, list):
                for user in user_id:
                    if user:
                        uid = etree.SubElement(u, "User")
                        uid.set("id", str(user))
            else:
                uid = etree.SubElement(u, "User")
                uid.set("id", str(user_id))
        if group_id:
            g = etree.SubElement(f, "Groups")
            if isinstance(group_id, list):
                for group in group_id:
                    if group:
                        gid = etree.SubElement(g, "Group")
                        gid.set("id", str(group))
            else:
                gid = etree.SubElement(g, "Group")
                gid.set("id", str(group_id))

    def get_field_map(self):
        type_formatter_map = {}
        for i in (1, 2, 3, 19):
            type_formatter_map[i] = self.plain_field
        for i in (4, 6, 9, 18, 27, 23):
            type_formatter_map[i] = self.mv_field
        for i in (8,):
            type_formatter_map[i] = self.user_field
        return type_formatter_map

    def update_record(self, content_id, module_id, fields):
        type_formatter_map = self.get_field_map()

        doc, body = self._generate_xml_stub()
        gr = etree.SubElement(body, "UpdateRecord", nsmap=ARCHER_MAP)
        to = etree.SubElement(gr, "sessionToken")
        to.text = self.auth.token
        mi = etree.SubElement(gr, "moduleId")
        mi.text = str(module_id)
        ci = etree.SubElement(gr, "contentId")
        ci.text = str(content_id)
        fv = etree.SubElement(gr, "fieldValues")

        r = etree.Element("Records")
        update_doc = etree.ElementTree(r)
        for field in fields:
            fn = type_formatter_map.get(field["type"])
            if not fn:
                raise ValueError(f"Unsupported Archer field type {field['type']} for field {field['id']}")
            fn(field, r)

        fv.text = etree.tostring(update_doc, pretty_print=True)

        resp_doc = self._do_request(self.base_uri + "/record.asmx", doc)

        resp_root = resp_doc.getroot()
        result = resp_root.xpath("/soap:Envelope/soap:Body/dummy:UpdateRecordResponse/dummy:UpdateRecordResult", namespaces=ALL_NS_MAP)
        if result and len(result) > 0:
            try:
                return int(result[0].text)
            except:
                pass
        return False

    def create_record(self, moduleid, fields):
        type_formatter_map = self.get_field_map()

        doc, body = self._generate_xml_stub()
        gr = etree.SubElement(body, "CreateRecord", nsmap=ARCHER_MAP)
        to = etree.SubElement(gr, "sessionToken")
        to.text = self.auth.token
        mi = etree.SubElement(gr, "moduleId")
        mi.text = str(moduleid)
        fv = etree.SubElement(gr, "fieldValues")

        r = etree.Element("Record")
        update_doc = etree.ElementTree(r)
        for field in fields:
            fn = type_formatter_map.get(field["type"])
            if not fn:
                raise ValueError(f"Unsupported Archer field type {field['type']} for field {field['id']}")
            fn(field, r)

        fv.text = etree.tostring(update_doc, pretty_print=True)

        resp_doc = self._do_request(self.base_uri + "/record.asmx", doc)

        resp_root = resp_doc.getroot()
        result = resp_root.xpath("/soap:Envelope/soap:Body/dummy:CreateRecordResponse/dummy:CreateRecordResult", namespaces=ALL_NS_MAP)
        if result and len(result) > 0:
            try:
                return int(result[0].text)
            except:
                pass
        return False

    def _generate_xml_stub(self):
        envelope = etree.Element(etree.QName(SOAPNS, "Envelope"), nsmap=NS_MAP)
        document = etree.ElementTree(envelope)
        body = etree.SubElement(envelope, etree.QName(SOAPNS, "Body"))
        return document, body

    def get_report(self, guid, page_number):
        doc, body = self._generate_xml_stub()
        gr = etree.SubElement(body, "SearchRecordsByReport", nsmap=ARCHER_MAP)
        to = etree.SubElement(gr, "sessionToken")
        to.text = self.auth.token
        gi = etree.SubElement(gr, "reportIdOrGuid")
        gi.text = str(guid)
        pn = etree.SubElement(gr, "pageNumber")
        pn.text = str(page_number)
        resp_doc = self._do_request(self.base_uri + "/search.asmx", doc)
        resp_root = resp_doc.getroot()
        rec_xml = resp_root.xpath(
            "/soap:Envelope/soap:Body/dummy:SearchRecordsByReportResponse/dummy:SearchRecordsByReportResult", namespaces=ALL_NS_MAP
        )

        if len(rec_xml) > 0:
            return {"status": "success", "result": rec_xml[0].text}
        else:
            return {"status": "failed", "result": "Archer did not return a saved report result"}

    def validate_pat(self):
        doc, body = self._generate_xml_stub()
        lookup = etree.SubElement(body, "LookupGroup", nsmap=ARCHER_MAP)
        etree.SubElement(lookup, "sessionToken").text = self.auth.token
        etree.SubElement(lookup, "keyword").text = "__splunk_soar_pat_connectivity_probe__"
        response = self._do_request(self.base_uri + "/accesscontrol.asmx", doc)
        if not response.xpath(archer_consts.ARCHER_XPATH_GROUP_OTHER, namespaces=ALL_NS_MAP):
            raise ArcherAPIError("SOAP PAT validation failed: Archer did not return a LookupGroup result")

    def _do_request(self, uri, doc, method="post"):
        if method != "post":
            raise ValueError("Invalid Method")
        api = doc.xpath("/soap:Envelope/soap:Body", namespaces=NS_MAP)[0].getchildren()
        if not api:
            raise ArcherAPIError("Could not find API node")
        api_tag = api[0].tag
        session_tokens = api[0].xpath("./*[local-name()='sessionToken']")

        for attempt in range(2):
            xml = etree.tostring(doc, pretty_print=True)
            headers = {
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f'"http://archer-tech.com/webservices/{api_tag}"',
            }
            headers.update(self.auth.headers("soap"))
            try:
                response = requests.post(
                    uri,
                    data=xml,
                    headers=headers,
                    verify=self.verify_cert,
                    stream=True,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                try:
                    response_body = read_bounded_response(response)
                finally:
                    response.close()
            except requests.RequestException as e:
                status = f" (HTTP {e.response.status_code})" if getattr(e, "response", None) is not None else ""
                raise ArcherAPIError(f"Archer SOAP {api_tag} request {request_failure_reason(e)}{status}") from None

            invalid_session = any(
                message.lower().encode() in response_body.lower() for message in archer_consts.ARCHER_INVALID_SESSION_TOKEN_MSG
            )
            if response.status_code == 403:
                raise ArcherPermissionError(archer_consts.ARCHER_PERMISSION_ERROR)
            if response.status_code == 401 or invalid_session:
                if self.auth.is_pat or attempt or not session_tokens:
                    raise self.auth.authentication_error()
                self.auth.session_token = None
                self._authenticate()
                session_tokens[0].text = self.auth.token
                continue

            try:
                response_doc = parse_untrusted_xml(response_body)
            except (etree.LxmlError, ValueError):
                raise ArcherAPIError(f"Archer returned invalid SOAP data for {api_tag} (HTTP {response.status_code})") from None
            faults = response_doc.xpath("//*[local-name()='Fault']")
            if faults:
                raise ArcherAPIError(
                    f"Archer returned a SOAP fault for {api_tag} (HTTP {response.status_code}). Check parameters and permissions"
                )
            try:
                response.raise_for_status()
            except requests.RequestException as e:
                status = f" (HTTP {e.response.status_code})" if getattr(e, "response", None) is not None else ""
                raise ArcherAPIError(f"Archer SOAP {api_tag} request {request_failure_reason(e)}{status}") from None
            return response_doc
