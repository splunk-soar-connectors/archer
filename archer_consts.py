# File: archer_consts.py
#
# Copyright (c) 2016-2023 Splunk Inc.
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
ARCHER_ACTION_CREATE_TICKET = "create_ticket"
ARCHER_ACTION_UPDATE_TICKET = "update_ticket"
ARCHER_ACTION_GET_TICKET = "get_ticket"
ARCHER_ACTION_LIST_TICKET = "list_tickets"
ARCHER_ACTION_ON_POLL = "on_poll"

ARCHER_SUCC_CONFIGURATION = "Archer configuration test SUCCESS"

ARCHER_SORT_TYPE_ASCENDING = "Ascending"
ARCHER_SORT_TYPE_DESCENDING = "Descending"

ARCHER_LAST_RECORD_FILE = "last_record_{}.txt"

ARCHER_ERROR_CODE_UNAVAILABLE = "Error code unavailable"
ARCHER_ERROR_CHECK_ASSET_CONFIG = "Error message unavailable. Please check the asset configuration and|or action parameters"
ARCHER_ERROR_CEF_MAPPING_REQUIRED = "CEF Mapping is required for ingestion. Please add CEF mapping to the asset config"
ARCHER_ERROR_APPLICATION_NOT_PROVIDED = 'Application is not provided in CEF Mapping (use key: "application")'
ARCHER_ERROR_TRACKING_ID_NOT_PROVIDED = 'Tracking ID Field name not provided in CEF Mapping (use key: "tracking")'
ARCHER_ERROR_VALID_JSON = "JSON field does not contain a valid JSON value"
ARCHER_ERROR_MESSAGE = "Error Message: {0}"
ARCHER_ERROR_CODE_MESSAGE = "Error Code: {0}, Error Message: {1}"
ARCHER_ERROR_RECORD_NOT_FOUND = "Record Name not found"
ARCHER_ERROR_NON_DICT = "Non-dict map: {}"
ARCHER_ERROR_ACTION_EXECUTION = "Exception during execution of archer action: {} and the error is: {}"
ARCHER_ERROR_VALID_INTEGER = "Please provide a valid integer value in the {}"
ARCHER_ERROR_NON_NEGATIVE = "Please provide a valid non-negative integer value in the {}"

ARCHER_XPATH_AUTH = '/soap:Envelope/soap:Body/dummy:CreateUserSessionFromInstanceResponse/dummy:CreateUserSessionFromInstanceResult'
ARCHER_XPATH_DOMAIN_USER_AUTH = \
    '/soap:Envelope/soap:Body/dummy:CreateDomainUserSessionFromInstanceResponse/dummy:CreateDomainUserSessionFromInstanceResult'
ARCHER_XPATH_GROUP = '/soap:Envelope/soap:Body/dummy:LookupGroupResponse/dummy:LookupGroupResult/dummy:Groups/dummy:/Group/dummy:Name'
