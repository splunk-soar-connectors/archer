[comment]: # "Auto-generated SOAR connector documentation"
# RSA Archer

Publisher: Splunk  
Connector Version: 2.2.2  
Product Vendor: RSA  
Product Name: Archer GRC  
Product Version Supported (regex): ".\*"  
Minimum Product Version: 5.3.3  

This app implements ticket management actions on RSA Archer GRC

[comment]: # "File: README.md"
[comment]: # "Copyright (c) 2016-2023 Splunk Inc."
[comment]: # ""
[comment]: # "Licensed under the Apache License, Version 2.0 (the 'License');"
[comment]: # "you may not use this file except in compliance with the License."
[comment]: # "You may obtain a copy of the License at"
[comment]: # ""
[comment]: # "    http://www.apache.org/licenses/LICENSE-2.0"
[comment]: # ""
[comment]: # "Unless required by applicable law or agreed to in writing, software distributed under"
[comment]: # "the License is distributed on an 'AS IS' BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,"
[comment]: # "either express or implied. See the License for the specific language governing permissions"
[comment]: # "and limitations under the License."
[comment]: # ""
When configuring the CEF to Archer mapping (cef_mapping), include the following...

  

-   The name of the application (e.g. Incidents)
-   The name of the tracking ID field (e.g. Incident ID)
-   Separate entries for each field that should go into the CEF of an artifact

When done, your mapping will take the names of Archer fields and map them into the CEF of an
artifact. It should look something like the following...

    {
        "application": "Incidents",
        "tracking": "Incident ID",
        "Status": "status",
        "Category": "category",
        "Details": "details",
        "Archer field name": "CEF name"
        ...
    }

  

Where Status, Category, Details, etc. are fields that exist in your Archer Application that you
would like to import.  
Certain field types and attachments from Archer are not currently supported. If a field is specified
both in the cef_mapping and in the excluded fields list, the field will be excluded and not
ingested.

### Scheduled | Interval polling

-   During scheduled | interval polling, for the first run, the app will start from the first
    record and will ingest a maximum of 100 records per poll. Then it remembers the last page and
    content id and stores it in the state file against the key 'last_page' & 'max_content_id'. For
    the following scheduled ingestions, it will consider the last_page stored in the state file and
    will ingest the next 100 records based on the provided Application.

### Manual polling

-   During manual polling, the app will start from the recently created record and will ingest up to
    the number of records specified in the 'Maximum containers' parameter.

### Explanation of the **\[User's Domain\]** asset configuration parameter

-   This asset configuration parameter affects \[test connectivity\] and all the other actions of
    the application.
-   When the value of this asset parameter is specified, the application will consider the user
    specified in the asset parameter \[username\] as the domain user of a given domain, and all the
    actions will be executed with the domain user session token created while running the action.
-   The user will be considered as a local user when the value of this parameter is not present. And
    if the local user attempts to change/add any of the field value(fields that expect the username
    value) with the domain user, then the action will fail because it requires a domain user session
    token to look up the domain user. And this token is generated only if the test connectivity is
    successfully run by the domain user.


### Configuration Variables
The below configuration variables are required for this Connector to operate.  These variables are specified when configuring a Archer GRC asset in SOAR.

VARIABLE | REQUIRED | TYPE | DESCRIPTION
-------- | -------- | ---- | -----------
**endpoint_url** |  required  | string | API endpoint (e.g., http://host/RSAarcher)
**instance_name** |  required  | string | Instance name (e.g., Default)
**username** |  required  | string | Username
**password** |  required  | password | Password
**verify_ssl** |  optional  | boolean | Verify server certificate
**cef_mapping** |  optional  | string | CEF to Archer mapping
**exclude_fields** |  optional  | string | Fields to exclude (comma separated)
**domain** |  optional  | string | User's Domain

### Supported Actions  
[test connectivity](#action-test-connectivity) - Validate the asset configuration for connectivity and field mapping  
[create ticket](#action-create-ticket) - Create a new ticket  
[update ticket](#action-update-ticket) - Update the value of a field of a record  
[get ticket](#action-get-ticket) - Get ticket information  
[list tickets](#action-list-tickets) - Get a list of tickets in an application  
[on poll](#action-on-poll) - Callback action for the on_poll ingest functionality  

## action: 'test connectivity'
Validate the asset configuration for connectivity and field mapping

Type: **test**  
Read only: **True**

#### Action Parameters
No parameters are required for this action

#### Action Output
No Output  

## action: 'create ticket'
Create a new ticket

Type: **generic**  
Read only: **False**

<p>JSON specifying the field names and values for a new Archer record (key/value pairs). For Cross-Reference fields, the value must be the content id of the referenced content.</p><p>Create record sample JSON: </p><pre><code>{ "Incident Summary": "test incident summary data", "Incident Owner": "susan" }</code></pre><br><p>Parameter application is case-sensitive.</p>

#### Action Parameters
PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**application** |  required  | Application/Module name (e.g. Incidents) | string |  `archer application` 
**json_string** |  required  | JSON data string | string | 

#### Action Output
DATA PATH | TYPE | CONTAINS | EXAMPLE VALUES
--------- | ---- | -------- | --------------
action_result.status | string |  |   success  failed 
action_result.parameter.application | string |  `archer application`  |   Incidents 
action_result.parameter.json_string | string |  |   { "Incident Summary": "Final test incident summary data" } 
action_result.data.\*.content_id | numeric |  `archer content id`  |   210036 
action_result.summary.content_id | numeric |  `archer content id`  |   210036 
action_result.message | string |  |   Created ticket 
summary.total_objects | numeric |  |   1 
summary.total_objects_successful | numeric |  |   1   

## action: 'update ticket'
Update the value of a field of a record

Type: **generic**  
Read only: **False**

There are multiple ways of locating a ticket to update. You must either give the content ID for the record, which can be obtained from Archer, or by specifying both the name of the Tracking ID field (name_field) and the Tracking ID (name_value). If all three parameters are provided, the content ID will be used as an overriding parameter to fetch the ticket. Parameters application, name_field, name_value, field_id, and value are case-sensitive.

#### Action Parameters
PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**application** |  required  | Application/Module name (e.g. Incidents) | string |  `archer application` 
**content_id** |  optional  | Content ID (Identifies the specific record) | numeric |  `archer content id` 
**name_field** |  optional  | Name of Tracking ID field (e.g. "Incident ID") | string | 
**name_value** |  optional  | Name of record (e.g. "INC-1234") | string |  `archer user friendly id` 
**field_id** |  required  | ID or name of the field to update in the record | string | 
**value** |  required  | New value of the record's field | string | 

#### Action Output
DATA PATH | TYPE | CONTAINS | EXAMPLE VALUES
--------- | ---- | -------- | --------------
action_result.status | string |  |   success  failed 
action_result.parameter.application | string |  `archer application`  |   Incidents 
action_result.parameter.content_id | numeric |  `archer content id`  |   210035 
action_result.parameter.field_id | string |  |   Incident Summary 
action_result.parameter.name_field | string |  |   Incident ID 
action_result.parameter.name_value | string |  `archer user friendly id`  |   10009 
action_result.parameter.value | string |  |   Hello Test Summary 1 
action_result.data | string |  |  
action_result.summary.content_id | numeric |  `archer content id`  |   210035 
action_result.message | string |  |   Updated ticket 
summary.total_objects | numeric |  |   1 
summary.total_objects_successful | numeric |  |   1   

## action: 'get ticket'
Get ticket information

Type: **investigate**  
Read only: **True**

There are multiple ways of locating a ticket to update. You must either give the content ID for the record, which can be obtained from Archer, or by specifying both the name of the Tracking ID field (name_field) and the Tracking ID (name_value). If all three parameters are provided, the content ID will be used as an overriding parameter to fetch the ticket. Parameters application, name_field, and name_value are case-sensitive.

#### Action Parameters
PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**application** |  required  | Application/Module name (e.g. Incidents) | string |  `archer application` 
**content_id** |  optional  | Content ID (Identifies the specific record) | numeric |  `archer content id` 
**name_field** |  optional  | Name of Tracking ID field (e.g. "Incident ID") | string | 
**name_value** |  optional  | Name of record (e.g. "INC-1234") | string |  `archer user friendly id` 

#### Action Output
DATA PATH | TYPE | CONTAINS | EXAMPLE VALUES
--------- | ---- | -------- | --------------
action_result.status | string |  |   success  failed 
action_result.parameter.application | string |  `archer application`  |   Incidents 
action_result.parameter.content_id | numeric |  `archer content id`  |   210035 
action_result.parameter.name_field | string |  |   Incident ID 
action_result.parameter.name_value | string |  `archer user friendly id`  |   INC-10009 
action_result.data.\*.@contentId | numeric |  `archer content id`  |   210035 
action_result.data.\*.@moduleId | numeric |  |   75 
action_result.data.\*.Record.@id | string |  |   210035 
action_result.data.\*.Record.@sequentialId | string |  |   10000 
action_result.data.\*.Record.@updateDate | string |  |   10/1/2018 8:04:28 AM 
action_result.data.\*.Record.@updateLogin | string |  |   2 
action_result.data.\*.Record.Field.\*.@height | string |  |  
action_result.data.\*.Record.Field.\*.@id | string |  |   206 
action_result.data.\*.Record.Field.\*.@name | string |  |   Incident ID 
action_result.data.\*.Record.Field.\*.@parentId | string |  |  
action_result.data.\*.Record.Field.\*.@type | string |  |   6 
action_result.data.\*.Record.Field.\*.@updateDate | string |  |   10/1/2018 6:57:46 AM 
action_result.data.\*.Record.Field.\*.@updateLogin | string |  |   2 
action_result.data.\*.Record.Field.\*.@value | string |  `ip`  |   10000 
action_result.data.\*.Record.Field.\*.@valueID | string |  |   409 
action_result.data.\*.Record.Field.\*.@width | string |  |  
action_result.data.\*.Record.Field.\*.Groups.Group.\*.@desc | string |  |   This group is the default for users with the IM: Solution Admin role. 
action_result.data.\*.Record.Field.\*.Groups.Group.\*.@id | string |  |   50 
action_result.data.\*.Record.Field.\*.Groups.Group.\*.@name | string |  |   IM: Admin 
action_result.data.\*.Record.Field.\*.Groups.Group.\*.@updateDate | string |  |   7/01/2009 10:12:52 AM 
action_result.data.\*.Record.Field.\*.Groups.Group.\*.@updateLogin | string |  |   2 
action_result.data.\*.Record.Field.\*.Groups.Group.@desc | string |  |   This group is the default for users with the IM: Solution Admin role. 
action_result.data.\*.Record.Field.\*.Groups.Group.@id | string |  |   1 
action_result.data.\*.Record.Field.\*.Groups.Group.@name | string |  |   IM: Admin 
action_result.data.\*.Record.Field.\*.Groups.Group.@updateDate | string |  |   1/18/2006 4:28:14 AM 
action_result.data.\*.Record.Field.\*.Groups.Group.@updateLogin | string |  |   2 
action_result.data.\*.Record.Field.\*.Record.\*.@id | string |  |   200049 
action_result.data.\*.Record.Field.\*.Record.\*.@levelId | string |  |   60 
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.@id | string |  |   206 
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.@parentId | string |  |  
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.@type | string |  |   6 
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.@value | string |  |   1 
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.@valueID | string |  |   406 
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.@firstName | string |  |   test 
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.@id | string |  |   190 
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.@lastName | string |  |   user 
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.@middleName | string |  |  
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.@updateDate | string |  |   6/01/2016 12:58:55 AM 
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.@updateLogin | string |  |   190 
action_result.data.\*.Record.Field.\*.Record.@id | string |  |   210033 
action_result.data.\*.Record.Field.\*.Record.@levelId | string |  |   60 
action_result.data.\*.Record.Field.\*.Record.Field.\*.@id | string |  |   607 
action_result.data.\*.Record.Field.\*.Record.Field.\*.@type | string |  |   1 
action_result.data.\*.Record.Field.\*.Record.Field.\*.@value | string |  |  
action_result.data.\*.Record.Field.\*.Record.Field.@id | string |  |   120 
action_result.data.\*.Record.Field.\*.Record.Field.@type | string |  |   1 
action_result.data.\*.Record.Field.\*.Record.Field.@value | string |  |   Phoenix PD 
action_result.data.\*.Record.Field.\*.Users.User.\*.@firstName | string |  |   System 
action_result.data.\*.Record.Field.\*.Users.User.\*.@id | string |  |   206 
action_result.data.\*.Record.Field.\*.Users.User.\*.@lastName | string |  |   Administrator 
action_result.data.\*.Record.Field.\*.Users.User.\*.@middleName | string |  |  
action_result.data.\*.Record.Field.\*.Users.User.\*.@updateDate | string |  |   10/6/2020 12:57:15 PM 
action_result.data.\*.Record.Field.\*.Users.User.\*.@updateLogin | string |  |   207 
action_result.data.\*.Record.Field.\*.Users.User.@firstName | string |  |   System 
action_result.data.\*.Record.Field.\*.Users.User.@id | string |  |   2 
action_result.data.\*.Record.Field.\*.Users.User.@lastName | string |  |   Administrator 
action_result.data.\*.Record.Field.\*.Users.User.@middleName | string |  |  
action_result.data.\*.Record.Field.\*.Users.User.@updateDate | string |  |   10/1/2018 8:46:55 AM 
action_result.data.\*.Record.Field.\*.Users.User.@updateLogin | string |  |   2 
action_result.data.\*.Record.Field.\*.multi_value | string |  |  
action_result.summary.content_id | numeric |  |   210035 
action_result.message | string |  |   Ticket retrieved 
summary.total_objects | numeric |  |   1 
summary.total_objects_successful | numeric |  |   1   

## action: 'list tickets'
Get a list of tickets in an application

Type: **investigate**  
Read only: **True**

You must provide both the field name/ID (name_field) and the value to search for (search_value) to search in records. If the combination of field name and search value is incorrect or the user provides neither of them, you may get an unfiltered list. Parameters application, name_field, and search_value are case-sensitive.

#### Action Parameters
PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**application** |  required  | Application/Module name (e.g. Incidents) | string |  `archer application` 
**max_results** |  required  | Max number of records to return | numeric | 
**name_field** |  optional  | Name of field to search in (e.g. "Incident ID") | string | 
**search_value** |  optional  | Value to search for in this application | string | 

#### Action Output
DATA PATH | TYPE | CONTAINS | EXAMPLE VALUES
--------- | ---- | -------- | --------------
action_result.status | string |  |   success  failed 
action_result.parameter.application | string |  `archer application`  |   Incidents 
action_result.parameter.max_results | numeric |  |   100 
action_result.parameter.name_field | string |  |   Incident ID 
action_result.parameter.search_value | string |  |   10000 
action_result.data.\*.@contentId | numeric |  `archer content id`  |   210035 
action_result.data.\*.@levelGuid | string |  |   b0c2da91-167c-4fee-ad91-4b4e7b098b4b 
action_result.data.\*.@levelId | string |  |   60 
action_result.data.\*.@moduleId | string |  |   70 
action_result.data.\*.@parentId | string |  |   0 
action_result.data.\*.Field.\*.#text | string |  `ip`  |   <p>Testing address</p> 
action_result.data.\*.Field.\*.@guid | string |  |   d00ae4c0-c75f-4eac-8900-81cf93cb4e21 
action_result.data.\*.Field.\*.@id | string |  |   1600 
action_result.data.\*.Field.\*.@name | string |  |   Address 
action_result.data.\*.Field.\*.@type | string |  |   1 
action_result.data.\*.Field.\*.@xmlConvertedValue | string |  |   2018-10-01T06:59:00Z 
action_result.data.\*.Field.\*.ListValues.ListValue.#text | string |  |   California 
action_result.data.\*.Field.\*.ListValues.ListValue.@displayName | string |  |   California 
action_result.data.\*.Field.\*.ListValues.ListValue.@id | string |  |   91 
action_result.data.\*.Field.\*.multi_value | string |  |   No 
action_result.summary.records_found | numeric |  |   1 
action_result.message | string |  |   Tickets retrieved 
summary.total_objects | numeric |  |   1 
summary.total_objects_successful | numeric |  |   1   

## action: 'on poll'
Callback action for the on_poll ingest functionality

Type: **ingest**  
Read only: **True**

This action has a persistent copy of the most recent 'Date Created' value it's seen on any successfully processed record. It uses this to pull all records created since then and creates a Phantom container for each. Records are pulled by referencing that 'poll_report' key of each cef_mapping entry. If any such entry does not have a 'poll_report' key, it is skipped; otherwise, the Archer report named by that key's value will be used as a list of records to pull and process according to that mapping.

#### Action Parameters
PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**start_time** |  optional  | Parameter ignored for this app | numeric | 
**end_time** |  optional  | Parameter ignored for this app | numeric | 
**container_count** |  optional  | Maximum number of container records to query for | numeric | 
**artifact_count** |  optional  | Maximum number of artifact records to query for | numeric | 

#### Action Output
No Output