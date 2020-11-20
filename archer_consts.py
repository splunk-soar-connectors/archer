# --
# File: archer_consts.py
#
# Copyright (c) 2016-2020 Splunk Inc.
#
# SPLUNK CONFIDENTIAL - Use or disclosure of this material in whole or in part
# without a valid written license from Splunk Inc. is PROHIBITED.
#
# --

ARCHER_ACTION_CREATE_TICKET = "create_ticket"
ARCHER_ACTION_UPDATE_TICKET = "update_ticket"
ARCHER_ACTION_GET_TICKET = "get_ticket"
ARCHER_ACTION_LIST_TICKET = "list_tickets"
ARCHER_ACTION_ON_POLL = "on_poll"

ARCHER_SUCC_CONFIGURATION = "Archer configuration test SUCCESS"

ARCHER_SORT_TYPE_ASCENDING = "Ascending"
ARCHER_SORT_TYPE_DESCENDING = "Descending"

ARCHER_LAST_RECORD_FILE = "last_record_{}.txt"

ARCHER_URL_FETCH_ARTIFACT_CONTAINER = "http://127.0.0.1/rest/container/{}/artifacts{}"
ARCHER_URL_FETCH_CONTAINER = "http://127.0.0.1/rest/container/{}"
ARCHER_URL_FETCH_ARTIFACT = "http://127.0.0.1/rest/artifact/{}"

ARCHER_ERR_PYTHON_MAJOR_VERSION = "Error occurred while getting the Phantom server's Python major version"
ARCHER_ERR_CODE_UNAVAILABLE = "Error code unavailable"
ARCHER_ERR_CHECK_ASSET_CONFIG = "Error message unavailable. Please check the asset configuration and|or action parameters."
ARCHER_UNICODE_DAMMIT_TYPE_ERR_MESSAGE = "Error occurred while connecting to the Archer Server. Please check the asset configuration and|or the action parameters."
ARCHER_ERR_CEF_MAPPING_REQUIRED = "CEF Mapping is required for ingestion. Please add CEF mapping to the asset config."
ARCHER_ERR_APPLICATION_NOT_PROVIDED = 'Application is not provided in CEF Mapping (use key: "application")'
ARCHER_ERR_TRACKING_ID_NOT_PROVIDED = 'Tracking ID Field name not provided in CEF Mapping (use key: "tracking")'
ARCHER_ERR_VALID_JSON = "JSON field does not contain a valid JSON value"
ARCHER_ERR_MESSAGE = "Error Message: {0}"
ARCHER_ERR_CODE_MESSAGE = "Error Code: {0}. Error Message: {1}"
ARCHER_ERR_RECORD_NOT_FOUND = "Record Name not found"
ARCHER_ERR_NON_DICT = "Non-dict map: {}"
ARCHER_ERR_ACTION_EXECUTION = "Exception during execution of archer action: {} and the error is: {}"
ARCHER_ERR_VALID_INTEGER = "Please provide a valid integer value in the {}"
ARCHER_ERR_NON_NEGATIVE = "Please provide a valid non-negative integer value in the {}"
