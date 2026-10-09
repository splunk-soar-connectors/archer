# File: test_archer_auth.py
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

import copy
import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from lxml import etree


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archer_consts as consts
from archer_auth import ArcherAPIError, ArcherAuth, ArcherAuthenticationError, ArcherPermissionError
from archer_soap import ARCHERNS, SOAPNS
from archer_utils import ArcherAPISession


PAT_CONFIG = {"auth_type": consts.ARCHER_AUTH_PAT, "personal_access_token": "customer-test-pat"}
PASSWORD_CONFIG = {"username": "service-user", "password": "login-password"}  # pragma: allowlist secret


def http_response(body, status=200):
    response = requests.Response()
    response.status_code = status
    response._content = body.encode() if isinstance(body, str) else body
    response._content_consumed = True
    response.url = "https://archer.example/api"
    response.close = Mock()
    response.iter_content = Mock(return_value=iter([response._content]))
    return response


def soap_response(method, result=""):
    envelope = etree.Element(etree.QName(SOAPNS, "Envelope"))
    body = etree.SubElement(envelope, etree.QName(SOAPNS, "Body"))
    reply = etree.SubElement(body, etree.QName(ARCHERNS, f"{method}Response"))
    etree.SubElement(reply, etree.QName(ARCHERNS, f"{method}Result")).text = result
    return http_response(etree.tostring(envelope))


def soap_fault(message, status=500):
    envelope = etree.Element(etree.QName(SOAPNS, "Envelope"))
    body = etree.SubElement(envelope, etree.QName(SOAPNS, "Body"))
    fault = etree.SubElement(body, etree.QName(SOAPNS, "Fault"))
    etree.SubElement(fault, "faultstring").text = message
    return http_response(etree.tostring(envelope), status)


def api_session(config=None, token=None, domain="DOMAIN"):
    auth = ArcherAuth(config or PAT_CONFIG)
    auth.session_token = token
    connector = SimpleNamespace(auth=auth, error_print=Mock())
    return ArcherAPISession("https://archer.example", "service-user", "login-password", "Default", domain, True, connector)


def test_default_mode_and_transport_selection():
    auth = ArcherAuth(PASSWORD_CONFIG)
    auth.session_token = "cached-session"
    assert not auth.is_pat
    assert auth.headers("soap") == {}
    assert auth.headers("rest") == {"Authorization": 'Archer session-id="cached-session"'}
    pat = ArcherAuth({**PAT_CONFIG, **PASSWORD_CONFIG})
    pat.session_token = "stale-session"
    assert pat.headers("rest") == pat.headers("soap") == {"Authorization": 'Archer session-id="customer-test-pat"'}


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"username": "service-user"},
        {"auth_type": "unsupported"},
        {"auth_type": consts.ARCHER_AUTH_PAT},
        {**PAT_CONFIG, "personal_access_token": ""},
        {**PAT_CONFIG, "personal_access_token": 123},
    ],
)
def test_invalid_configuration_rejected(config):
    with pytest.raises(ValueError):
        ArcherAuth(config)


@pytest.mark.parametrize("method", ["get", "post", "put"])
def test_rest_pat_headers_payload_and_timeout(monkeypatch, method):
    session = api_session()
    response = http_response('{"IsSuccessful":true}')
    request = Mock(return_value=response)
    monkeypatch.setattr(requests, method, request)
    assert json.loads(session._rest_call("/api/core/content/", method, {"Content": {"Id": 1}}))["IsSuccessful"]
    assert request.call_args.kwargs["headers"]["Authorization"] == 'Archer session-id="customer-test-pat"'
    assert request.call_args.kwargs["json"] == {"Content": {"Id": 1}}
    assert request.call_args.kwargs["timeout"] == consts.DEFAULT_TIMEOUT
    response.close.assert_called_once()


@pytest.mark.parametrize("status,error", [(401, ArcherAuthenticationError), (403, ArcherPermissionError)])
def test_rest_pat_rejection_does_not_login_or_retry(monkeypatch, status, error):
    session = api_session()
    request = Mock(return_value=http_response("rejected", status))
    monkeypatch.setattr(requests, "get", request)
    login = Mock(side_effect=AssertionError("PAT must never login"))
    monkeypatch.setattr(session.asoap, "_authenticate", login)
    with pytest.raises(error):
        session._rest_call("/api/core/system/application")
    assert request.call_count == 1
    login.assert_not_called()


@pytest.mark.parametrize("second_status", [200, 401])
def test_rest_password_renews_once(monkeypatch, second_status):
    session = api_session(PASSWORD_CONFIG, "old-session")
    request = Mock(side_effect=[http_response("expired", 401), http_response("[]", second_status)])
    monkeypatch.setattr(requests, "get", request)
    login = Mock(side_effect=lambda: setattr(session.auth, "session_token", "renewed-session"))
    monkeypatch.setattr(session.asoap, "_authenticate", login)
    if second_status == 401:
        with pytest.raises(ArcherAuthenticationError):
            session._rest_call("/api/core/system/application")
    else:
        assert session._rest_call("/api/core/system/application") == "[]"
    login.assert_called_once()
    assert request.call_count == 2
    assert request.call_args_list[1].kwargs["headers"]["Authorization"] == 'Archer session-id="renewed-session"'


@pytest.mark.parametrize(
    "method,args,result",
    [
        ("find_group", ["analysts"], "<Groups><Group><Name>analysts</Name><Id>2</Id></Group></Groups>"),
        ("find_user", ["analyst"], "2"),
        ("find_domain_user", ["analyst"], "2"),
        ("find_records", [1, "Incidents", 2, "Title", "example"], "<Records/>"),
        ("get_record", [1, 2], "<Record/>"),
        ("create_record", [1, [{"id": 2, "type": 1, "value": "example"}]], "3"),
        ("update_record", [1, 2, [{"id": 3, "type": 1, "value": "example"}]], "1"),
        ("get_report", ["report-guid", 1], "<Records/>"),
    ],
)
def test_all_soap_operations_use_pat_header_and_body(monkeypatch, method, args, result):
    session = api_session()
    observed = []

    def request(url, **kwargs):
        document = etree.fromstring(kwargs["data"])
        operation = document.find(f"{{{SOAPNS}}}Body")[0]
        assert operation.xpath("./*[local-name()='sessionToken']/text()") == ["customer-test-pat"]
        assert not operation.xpath(".//*[local-name()='password']")
        assert kwargs["headers"]["Authorization"] == 'Archer session-id="customer-test-pat"'
        assert "SOAPAction" in kwargs["headers"]
        assert kwargs["timeout"] == 30
        if method == "find_domain_user":
            assert operation.xpath("./*[local-name()='usersDomain']/text()") == ["DOMAIN"]
        observed.append(url)
        return soap_response(etree.QName(operation).localname, result)

    monkeypatch.setattr(requests, "post", request)
    getattr(session.asoap, method)(*args)
    assert len(observed) == 1


@pytest.mark.parametrize("status", [200, 500])
def test_pat_soap_auth_fault_never_renews(monkeypatch, status):
    session = api_session()
    request = Mock(return_value=soap_fault("Invalid session token", status))
    monkeypatch.setattr(requests, "post", request)
    with pytest.raises(ArcherAuthenticationError):
        session.asoap.find_records(1, "Incidents", 2, "Title", None)
    assert request.call_count == 1


@pytest.mark.parametrize("status", [200, 500])
def test_non_auth_soap_fault_is_not_an_empty_search(monkeypatch, status):
    session = api_session()
    monkeypatch.setattr(requests, "post", Mock(return_value=soap_fault("Access denied to customer-test-pat", status)))
    with pytest.raises(ArcherAPIError) as error:
        session.asoap.find_records(1, "Incidents", 2, "Title", None)
    assert "SOAP fault" in str(error.value)
    assert "ExecuteSearch" in str(error.value)
    assert "customer-test-pat" not in str(error.value)


@pytest.mark.parametrize("second_invalid", [False, True])
@pytest.mark.parametrize("domain", [None, "DOMAIN"])
def test_soap_password_renewal_replaces_body_once(monkeypatch, second_invalid, domain):
    session = api_session(PASSWORD_CONFIG, "old-session", domain)
    login_method = "CreateDomainUserSessionFromInstance" if domain else "CreateUserSessionFromInstance"
    observed = []

    def request(url, **kwargs):
        operation = etree.fromstring(kwargs["data"]).find(f"{{{SOAPNS}}}Body")[0]
        method = etree.QName(operation).localname
        assert "Authorization" not in kwargs["headers"]
        observed.append((method, operation.xpath("./*[local-name()='sessionToken']/text()")))
        if method == login_method:
            return soap_response(method, "renewed-session")
        if len(observed) == 1 or second_invalid:
            return soap_fault("Unable to validate session")
        return soap_response(method, "2")

    monkeypatch.setattr(requests, "post", request)
    if second_invalid:
        with pytest.raises(ArcherAuthenticationError):
            session.asoap.find_user("analyst")
    else:
        assert session.asoap.find_user("analyst") == 2
    assert observed == [
        ("LookupUserId", ["old-session"]),
        (login_method, []),
        ("LookupUserId", ["renewed-session"]),
    ]


def test_login_auth_failure_does_not_recurse(monkeypatch):
    request = Mock(return_value=soap_fault("Invalid session token"))
    monkeypatch.setattr(requests, "post", request)
    with pytest.raises(ArcherAuthenticationError):
        api_session(PASSWORD_CONFIG)
    assert request.call_count == 1


def test_network_errors_return_controlled_messages(monkeypatch):
    session = api_session({**PAT_CONFIG, **PASSWORD_CONFIG})
    failure = requests.ConnectionError("Failed customer-test-pat login-password")
    monkeypatch.setattr(requests, "get", Mock(side_effect=failure))
    monkeypatch.setattr(requests, "post", Mock(side_effect=failure))
    for operation in (lambda: session._rest_call("/api/core/system/application"), lambda: session.asoap.find_user("analyst")):
        with pytest.raises(ArcherAPIError) as error:
            operation()
        assert "could not connect" in str(error.value)
        assert "customer-test-pat" not in str(error.value)
        assert "login-password" not in str(error.value)


@pytest.fixture
def connector(monkeypatch):
    class BaseConnector:
        def __init__(self):
            self.config = {**PAT_CONFIG, "endpoint_url": "https://archer.example", "instance_name": "Default"}
            self.stored_state = {}
            self.messages = []

        def get_asset_id(self):
            return "pat-unit-test"

        def get_app_config(self):
            return {}

        def get_config(self):
            return self.config

        def load_state(self):
            return copy.deepcopy(self.stored_state)

        def save_state(self, state):
            self.stored_state = copy.deepcopy(state)

        def get_app_json(self):
            return {"app_version": "4.1.0"}

        def get_action_identifier(self):
            return self.action_id

        def get_container_id(self):
            return 1

        def get_state_file_path(self):
            return "/state"

        def is_poll_now(self):
            return False

        def set_status(self, status, message):
            self.messages.append(message)
            return status

        def add_action_result(self, result):
            self.result = result

        def debug_print(self, *args):
            self.messages.append(" ".join(str(arg) for arg in args))

        error_print = debug_print
        send_progress = debug_print
        save_progress = debug_print

    class ActionResult:
        def __init__(self, param):
            self.status = 0
            self.message = ""
            self.summary = {}

        def set_status(self, status, message, *args):
            self.status, self.message = status, message
            return status

        def get_status(self):
            return self.status

        def update_summary(self, summary):
            self.summary.update(summary)

        def add_data(self, data):
            self.data = [*getattr(self, "data", []), data]

    phantom = types.ModuleType("phantom")
    app = types.ModuleType("phantom.app")
    app.APP_SUCCESS, app.APP_ERROR = 0, 1
    app.ACTION_ID_TEST_ASSET_CONNECTIVITY = "test_asset_connectivity"
    app.is_fail = lambda status: status == app.APP_ERROR
    phantom.app = app
    phantom.vault = SimpleNamespace(vault_info=Mock())
    base = types.ModuleType("phantom.base_connector")
    base.BaseConnector = BaseConnector
    action = types.ModuleType("phantom.action_result")
    action.ActionResult = ActionResult
    encryption = types.ModuleType("encryption_helper")
    encryption.encrypt = Mock(side_effect=lambda value, asset: f"encrypted:{value}")
    encryption.decrypt = Mock(side_effect=lambda value, asset: value.removeprefix("encrypted:"))
    for name, module in {
        "phantom": phantom,
        "phantom.app": app,
        "phantom.base_connector": base,
        "phantom.action_result": action,
        "encryption_helper": encryption,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location("archer_connector", Path(__file__).resolve().parents[1] / "archer_connector.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    instance = module.ArcherConnector()
    instance.test_module = module
    instance.encryption = encryption
    return instance


def test_pat_clears_legacy_session_without_decryption_or_secret_persistence(connector):
    connector.stored_state = {"session_token": "encrypted:old-session", "Incidents": {"max_content_id": 9}}
    assert connector.initialize() == 0
    connector.finalize()
    connector.encryption.decrypt.assert_not_called()
    connector.encryption.encrypt.assert_not_called()
    assert connector.stored_state == {"auth_type": consts.ARCHER_AUTH_PAT, "Incidents": {"max_content_id": 9}}
    assert "customer-test-pat" not in json.dumps(connector.stored_state)


def test_existing_password_asset_retains_encrypted_session(connector):
    connector.config = {**connector.config, **PASSWORD_CONFIG, "auth_type": consts.ARCHER_AUTH_PASSWORD}
    connector.stored_state = {"session_token": "encrypted:cached-session"}
    assert connector.initialize() == 0
    assert connector.auth.token == "cached-session"
    connector.finalize()
    assert connector.stored_state["session_token"] == "encrypted:cached-session"


def test_switch_from_pat_to_password_starts_new_session(connector, monkeypatch):
    connector.config = {**connector.config, **PASSWORD_CONFIG, "auth_type": consts.ARCHER_AUTH_PASSWORD}
    connector.stored_state = {"auth_type": consts.ARCHER_AUTH_PAT, "session_token": "encrypted:stale-session"}
    request = Mock(return_value=soap_response("CreateUserSessionFromInstance", "new-session"))
    monkeypatch.setattr(requests, "post", request)
    assert connector.initialize() == 0
    connector.encryption.decrypt.assert_not_called()
    assert connector.auth.token == "new-session"


def test_pat_rotation_reads_updated_asset(connector):
    assert connector.initialize() == 0
    connector.finalize()
    connector.config["personal_access_token"] = "replacement-pat"
    connector.proxy = None
    assert connector.initialize() == 0
    assert connector.auth.token == "replacement-pat"


def test_connectivity_checks_both_transports_with_empty_results(connector, monkeypatch):
    rest = Mock(return_value=http_response("[]"))
    soap = Mock(return_value=soap_response("LookupGroup"))
    monkeypatch.setattr(requests, "get", rest)
    monkeypatch.setattr(requests, "post", soap)
    assert connector.initialize() == 0
    connector.action_id = "test_asset_connectivity"
    assert connector.handle_action({}) == 0
    rest.assert_called_once()
    soap.assert_called_once()
    assert "REST PAT authentication... SUCCESS" in connector.messages
    assert "SOAP PAT authentication... SUCCESS" in connector.messages


@pytest.mark.parametrize("body", ['{"IsSuccessful":false}', '[{"IsSuccessful":false}]'])
def test_connectivity_rejects_unsuccessful_rest_body(monkeypatch, body):
    monkeypatch.setattr(requests, "get", Mock(return_value=http_response(body)))
    with pytest.raises(ArcherAPIError):
        api_session().validate_pat_rest()


def test_connectivity_requires_actual_soap_result(monkeypatch):
    monkeypatch.setattr(requests, "post", Mock(return_value=soap_response("UnexpectedMethod")))
    with pytest.raises(ArcherAPIError):
        api_session().asoap.validate_pat()


ACTION_PARAMS = [
    ("test_asset_connectivity", {}),
    ("create_ticket", {"application": "Incidents", "json_string": '{"Title":"example"}'}),
    ("update_ticket", {"application": "Incidents", "content_id": 1, "field_id": 2, "value": "example"}),
    ("get_ticket", {"application": "Incidents", "content_id": 1}),
    ("list_tickets", {"application": "Incidents"}),
    ("create_attachment", {"vault_id": "example"}),
    ("get_report", {"guid": "report-guid"}),
    ("on_poll", {}),
    ("assign_ticket", {"application": "Incidents", "content_id": 1, "field_id": 5, "users": "3"}),
    ("attach_alert", {"application": "Incidents", "content_id": 1, "field_id": 3, "security_alert_id": "4"}),
]


@pytest.mark.parametrize("action_id,param", ACTION_PARAMS)
def test_all_actions_report_pat_rejection_without_login(connector, monkeypatch, tmp_path, action_id, param):
    get = Mock(side_effect=lambda *args, **kwargs: http_response("rejected", 401))
    post = Mock(side_effect=lambda *args, **kwargs: http_response("rejected", 401))
    put = Mock(side_effect=lambda *args, **kwargs: http_response("rejected", 401))
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "put", put)
    attachment = tmp_path / "attachment.txt"
    attachment.write_text("example")
    connector.test_module.vault.vault_info.return_value = (True, "", [{"path": str(attachment), "name": "attachment.txt"}])
    connector.config["cef_mapping"] = '{"application":"Incidents","tracking":"Tracking ID"}'
    connector.stored_state = {"Incidents": {"max_content_id": 9}}
    assert connector.initialize() == 0
    connector.action_id = action_id
    assert connector.handle_action(param) == 1
    if action_id == "test_asset_connectivity":
        assert any("PAT authentication was rejected" in message for message in connector.messages)
    else:
        assert "PAT authentication was rejected" in connector.result.message
    assert get.call_count + post.call_count + put.call_count == 1
    for call in post.call_args_list:
        assert "CreateUserSession" not in str(call)
    connector.finalize()
    assert connector.stored_state["Incidents"]["max_content_id"] == 9
    assert "customer-test-pat" not in json.dumps(connector.messages)


def test_password_login_guards_in_pat_mode():
    session = api_session()
    for login in (session.get_token, session.asoap._authenticate, session.asoap._domain_user_authenticate):
        with pytest.raises(ArcherAPIError, match="Password login is unavailable"):
            login()


@pytest.mark.parametrize(
    "action_id,param",
    [
        *ACTION_PARAMS,
        ("get_ticket", {"application": "Incidents", "name_field": "Tracking ID", "name_value": "INC-7"}),
        ("update_ticket", {"application": "Incidents", "name_field": "Tracking ID", "name_value": "INC-7", "field_id": 2, "value": "example"}),
        ("assign_ticket", {"application": "Incidents", "name_field": "Tracking ID", "name_value": "INC-7", "field_id": 5, "users": "3"}),
        (
            "attach_alert",
            {"application": "Incidents", "name_field": "Tracking ID", "name_value": "INC-7", "field_id": 3, "security_alert_id": "4"},
        ),
    ],
)
def test_all_actions_complete_using_pat_on_both_transports(connector, monkeypatch, tmp_path, action_id, param):
    fields = [
        {"Id": 2, "Name": "Title", "Type": 1, "LevelId": 10},
        {"Id": 3, "Name": "Security Alerts", "Type": 23, "LevelId": 10},
        {"Id": 4, "Name": "Tracking ID", "Type": 3, "LevelId": 10},
        {"Id": 5, "Name": "Owner", "Type": 8, "LevelId": 10},
    ]
    calls = []
    updates = []

    def request(url, **kwargs):
        assert kwargs["headers"]["Authorization"] == 'Archer session-id="customer-test-pat"'
        assert kwargs["timeout"] == 30
        calls.append(url)
        if "/ws/" in url:
            operation = etree.fromstring(kwargs["data"]).find(f"{{{SOAPNS}}}Body")[0]
            method = etree.QName(operation).localname
            assert operation.xpath("./*[local-name()='sessionToken']/text()") == ["customer-test-pat"]
            assert "SessionFromInstance" not in method
            if method == "LookupGroup":
                result = "<Groups/>"
            elif method in ("CreateRecord", "UpdateRecord"):
                result = "7"
            elif method == "GetRecordById":
                result = (
                    '<Record id="7"><Field id="2" type="1" value="example"/>'
                    '<Field id="3" type="23"><Record id="9"/></Field>'
                    '<Field id="4" type="3" value="7"/></Record>'
                )
            elif method in ("ExecuteSearch", "SearchRecordsByReport"):
                result = (
                    '<Records><Metadata><FieldDefinitions><FieldDefinition id="2" name="Title"/>'
                    '<FieldDefinition id="4" name="Tracking ID"/></FieldDefinitions></Metadata>'
                    '<Record contentId="7"><Field id="2" type="1">example</Field>'
                    '<Field id="4" type="3">7</Field></Record></Records>'
                )
            else:
                raise AssertionError(f"Unexpected SOAP method: {method}")
            return soap_response(method, result)
        if "json" in kwargs:
            json.dumps(kwargs["json"])
        if url.endswith("/system/application"):
            body = [{"IsSuccessful": True, "RequestedObject": {"Id": 1, "Name": "Incidents", "Alias": "incidents"}}]
        elif "/system/level/module/" in url:
            body = [{"IsSuccessful": True, "RequestedObject": {"Id": 10}}]
        elif "/fielddefinition/level/" in url:
            body = [{"IsSuccessful": True, "RequestedObject": field} for field in fields]
        elif "/fielddefinition/" in url:
            field_id = int(url.rsplit("/", 1)[1])
            body = {"IsSuccessful": True, "RequestedObject": next(field for field in fields if field["Id"] == field_id)}
        elif url.endswith("/content/attachment"):
            body = {"IsSuccessful": True, "RequestedObject": {"Id": 8}}
        elif url.endswith("/content/"):
            updates.append(kwargs["json"])
            body = {"IsSuccessful": True, "RequestedObject": {"Id": 7}}
        else:
            raise AssertionError(f"Unexpected REST endpoint: {url}")
        return http_response(json.dumps(body))

    for method in ("get", "post", "put"):
        monkeypatch.setattr(requests, method, request)
    attachment = tmp_path / "attachment.txt"
    attachment.write_text("example")
    connector.test_module.vault.vault_info.return_value = (True, "", [{"path": str(attachment), "name": "attachment.txt"}])
    connector.config["cef_mapping"] = '{"application":"Incidents","tracking":"Tracking ID","Title":"message"}'
    containers, artifacts = [], []
    connector.save_container = lambda container: (containers.append(container) or 0, "", 1)
    connector.save_artifact = lambda artifact: (artifacts.append(artifact) or 0, "", 1)
    assert connector.initialize() == 0
    connector.action_id = action_id
    params = {**param, "max_pages": 1} if action_id == "get_report" else param
    assert connector.handle_action(params) == 0, connector.result.message
    assert calls
    if action_id == "attach_alert":
        assert updates[0]["Content"]["FieldContents"]["3"]["Value"] == ["9", "4"]
    if action_id == "on_poll":
        assert len(containers) == len(artifacts) == 1
        assert artifacts[0]["cef"]["message"] == "example"
        assert connector._state["Incidents"]["max_content_id"] == 7
        assert "customer-test-pat" not in json.dumps(containers + artifacts)
    connector.finalize()
    assert "customer-test-pat" not in json.dumps(connector.stored_state)
