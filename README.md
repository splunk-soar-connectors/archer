# RSA Archer

Publisher: Splunk \
Connector Version: 3.2.2 \
Product Vendor: RSA \
Product Name: Archer GRC \
Minimum Product Version: 6.2.1

This app implements ticket management actions on RSA Archer GRC

When configuring the CEF to Archer mapping (cef_mapping), include the following...

- The name of the application (e.g. Incidents)
- The name of the tracking ID field (e.g. Incident ID)
- Separate entries for each field that should go into the CEF of an artifact

When done, your mapping will take the names of Archer fields and map them into the CEF of an artifact. It should look something like the following...

```
"application": "Incidents",
"tracking": "Incident ID",
"Status": "status",
"Category": "category",
"Details": "details",
"Archer field name": "CEF name"
...
```

Where Status, Category, Details, etc. are fields that exist in your Archer Application that you would like to import.
Certain field types and attachments from Archer are not currently supported.

If a field is specified both in the cef_mapping and in the excluded fields list, the field will be excluded and not ingested.

### Scheduled | Interval polling

- During scheduled | interval polling, for the first run, the app will start from the first record and will ingest a maximum of 100 records per poll. Then it remembers the last page and content id and stores it in the state file against the key 'last_page' & 'max_content_id'. For the following scheduled ingestions, it will consider the last_page stored in the state file and will ingest the next 100 records based on the provided Application.

### Manual polling

- During manual polling, the app will start from the recently created record and will ingest up to the number of records specified in the 'Maximum containers' parameter.

### Explanation of the **[User's Domain]** asset configuration parameter

- This asset configuration parameter affects [test connectivity] and all the other actions of the application.
- When the value of this asset parameter is specified, the application will consider the user specified in the asset parameter [username] as the domain user of a given domain, and all the actions will be executed with the domain user session token created while running the action.
- The user will be considered as a local user when the value of this parameter is not present. And if the local user attempts to change/add any of the field value(fields that expect the username value) with the domain user, then the action will fail because it requires a domain user session token to look up the domain user. And this token is generated only if the test connectivity is successfully run by the domain user

### Steps to update the session time on Archer UI:

By default the session timeout in Archer will be 10 minutes, It is recommended to increase the timeout so that a token generated works for longer time.
Steps to update the session timeout:

- Go to Administration settings > Security Parameters

- Select the Security Parameter name to update session timeout for

- Under the Authorization Properties, update the “Session Timeout” value

### Configuration variables

This table lists the configuration variables required to operate RSA Archer. These variables are specified when configuring a Archer GRC asset in Splunk SOAR.

VARIABLE | REQUIRED | TYPE | DESCRIPTION
-------- | -------- | ---- | -----------
**endpoint_url** | required | string | API endpoint (e.g., http://host/RSAarcher) |
**instance_name** | required | string | Instance name (e.g., Default) |
**username** | required | string | Username |
**password** | required | password | Password |
**verify_ssl** | optional | boolean | Verify server certificate |
**cef_mapping** | optional | string | CEF to Archer mapping |
**exclude_fields** | optional | string | Fields to exclude (comma separated) |
**domain** | optional | string | User's Domain |

### Supported Actions

[test connectivity](#action-test-connectivity) - Validate the asset configuration for connectivity and field mapping \
[create ticket](#action-create-ticket) - Create a new ticket \
[update ticket](#action-update-ticket) - Update the value of a field of a record \
[get ticket](#action-get-ticket) - Get ticket information \
[list tickets](#action-list-tickets) - Get a list of tickets in an application \
[create attachment](#action-create-attachment) - Create an attachment \
[get report](#action-get-report) - Get a list of tickets from a report \
[on poll](#action-on-poll) - Callback action for the on_poll ingest functionality \
[assign ticket](#action-assign-ticket) - Assign users and/or groups to record \
[attach alert](#action-attach-alert) - Attach Security alert to the record

## action: 'test connectivity'

Validate the asset configuration for connectivity and field mapping

Type: **test** \
Read only: **True**

#### Action Parameters

No parameters are required for this action

#### Action Output

No Output

## action: 'create ticket'

Create a new ticket

Type: **generic** \
Read only: **False**

<p>JSON specifying the field names and values for a new Archer record (key/value pairs). For Cross-Reference fields, the value must be the content id of the referenced content.</p><p>Create record sample JSON: </p><pre><code>{ "Incident Summary": "test incident summary data", "Incident Owner": "testuser" }</code></pre><br><p>Parameter application is case-sensitive. The following field types are supported for creating a ticket:<ul><li>Type 1 (TextString)</li><li>Type 2 (Numeric)</li><li>Type 3 (Date with Time)</li><li>Type 4 (Values List)</li><li>Type 8 (Users/Groups List)</li><li>Type 9 (Cross-Reference)</li><li>Type 23 (Related Records).</li></ul></p>

#### Action Parameters

PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**application** | required | Application/Module name (e.g. Incidents) | string | `archer application` |
**json_string** | required | JSON data string | string | |

#### Action Output

DATA PATH | TYPE | CONTAINS | EXAMPLE VALUES
--------- | ---- | -------- | --------------
action_result.status | string | | success failed |
action_result.parameter.application | string | `archer application` | Incidents |
action_result.parameter.json_string | string | | { "Incident Summary": "Final test incident summary data" } |
action_result.data.\*.content_id | numeric | `archer content id` | 210036 |
action_result.summary.content_id | numeric | `archer content id` | 210036 |
action_result.message | string | | Created ticket |
summary.total_objects | numeric | | 1 |
summary.total_objects_successful | numeric | | 1 |

## action: 'update ticket'

Update the value of a field of a record

Type: **generic** \
Read only: **False**

There are multiple ways of locating a ticket to update. You must either give the content ID for the record, which can be obtained from Archer, or by specifying both the name of the Tracking ID field (name_field) and the Tracking ID (name_value). If all three parameters are provided, the content ID will be used as an overriding parameter to update the ticket. Parameters application, name_field, name_value, field_id, and value are case-sensitive. Here, if both json_string, and field_id and value are specified, preference would be given to json_string parameter and ticket will be updated based on that. The following field types are supported for creating a ticket:<ul><li>Type 1 (TextString)</li><li>Type 2 (Numeric)</li><li>Type 3 (Date with Time)</li><li>Type 4 (Values List)</li><li>Type 8 (Users/Groups List)</li><li>Type 9 (Cross-Reference)</li><li>Type 23 (Related Records).</li></ul>

#### Action Parameters

PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**application** | required | Application/Module name (e.g. Incidents) | string | `archer application` |
**content_id** | optional | Content ID (Identifies the specific record) | numeric | `archer content id` |
**name_field** | optional | Name of Tracking ID field (e.g. "Incident ID") | string | |
**name_value** | optional | Name of record (e.g. "INC-1234") | string | `archer user friendly id` |
**field_id** | optional | ID or name of the field to update in the record | string | |
**value** | optional | New value of the record's field (Comma-separated values allowed if Users or Groups to be updated to a field) | string | |
**json_string** | optional | JSON data string | string | |

#### Action Output

DATA PATH | TYPE | CONTAINS | EXAMPLE VALUES
--------- | ---- | -------- | --------------
action_result.status | string | | success failed |
action_result.parameter.application | string | `archer application` | Incidents |
action_result.parameter.content_id | numeric | `archer content id` | 210035 |
action_result.parameter.field_id | string | | Incident Summary |
action_result.parameter.json_string | string | | { "Incident Summary": "Final test incident summary data" } |
action_result.parameter.name_field | string | | Incident ID |
action_result.parameter.name_value | string | `archer user friendly id` | 10009 |
action_result.parameter.value | string | | Hello Test Summary 1 |
action_result.data | string | | |
action_result.summary.content_id | numeric | `archer content id` | 210035 |
action_result.message | string | | Updated ticket |
summary.total_objects | numeric | | 1 |
summary.total_objects_successful | numeric | | 1 |

## action: 'get ticket'

Get ticket information

Type: **investigate** \
Read only: **True**

There are multiple ways of locating a ticket to update. You must either give the content ID for the record, which can be obtained from Archer, or by specifying both the name of the Tracking ID field (name_field) and the Tracking ID (name_value). If all three parameters are provided, the content ID will be used as an overriding parameter to fetch the ticket. Parameters application, name_field, and name_value are case-sensitive.

#### Action Parameters

PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**application** | required | Application/Module name (e.g. Incidents) | string | `archer application` |
**content_id** | optional | Content ID (Identifies the specific record) | numeric | `archer content id` |
**name_field** | optional | Name of Tracking ID field (e.g. "Incident ID") | string | |
**name_value** | optional | Name of record (e.g. "INC-1234") | string | `archer user friendly id` |

#### Action Output

DATA PATH | TYPE | CONTAINS | EXAMPLE VALUES
--------- | ---- | -------- | --------------
action_result.status | string | | success failed |
action_result.parameter.application | string | `archer application` | Incidents |
action_result.parameter.content_id | numeric | `archer content id` | 210035 |
action_result.parameter.name_field | string | | Incident ID |
action_result.parameter.name_value | string | `archer user friendly id` | INC-10009 |
action_result.data.\*.@contentId | numeric | `archer content id` | 210035 |
action_result.data.\*.@moduleId | numeric | | 75 |
action_result.data.\*.Record.@id | string | | 210035 |
action_result.data.\*.Record.@sequentialId | string | | 10000 |
action_result.data.\*.Record.@updateDate | string | | 10/1/2018 8:04:28 AM |
action_result.data.\*.Record.@updateLogin | string | | 2 |
action_result.data.\*.Record.Field.\*.@fileID | string | | 21 |
action_result.data.\*.Record.Field.\*.@fileName | string | | test.png |
action_result.data.\*.Record.Field.\*.@height | string | | |
action_result.data.\*.Record.Field.\*.@id | string | | 206 |
action_result.data.\*.Record.Field.\*.@name | string | | Incident ID |
action_result.data.\*.Record.Field.\*.@otherText | string | | This is no impact incident to check the ownership and the contact field/. |
action_result.data.\*.Record.Field.\*.@parentId | string | | |
action_result.data.\*.Record.Field.\*.@type | string | | 6 |
action_result.data.\*.Record.Field.\*.@updateDate | string | | 10/1/2018 6:57:46 AM |
action_result.data.\*.Record.Field.\*.@updateLogin | string | | 2 |
action_result.data.\*.Record.Field.\*.@value | string | `ip` | 10000 |
action_result.data.\*.Record.Field.\*.@valueID | string | | 409 |
action_result.data.\*.Record.Field.\*.@width | string | | |
action_result.data.\*.Record.Field.\*.Groups.Group.\*.@desc | string | | This group is the default for users with the IM: Solution Admin role. |
action_result.data.\*.Record.Field.\*.Groups.Group.\*.@id | string | | 50 |
action_result.data.\*.Record.Field.\*.Groups.Group.\*.@name | string | | IM: Admin |
action_result.data.\*.Record.Field.\*.Groups.Group.\*.@updateDate | string | | 7/01/2009 10:12:52 AM |
action_result.data.\*.Record.Field.\*.Groups.Group.\*.@updateLogin | string | | 2 |
action_result.data.\*.Record.Field.\*.Groups.Group.@desc | string | | This group is the default for users with the IM: Solution Admin role. |
action_result.data.\*.Record.Field.\*.Groups.Group.@id | string | | 1 |
action_result.data.\*.Record.Field.\*.Groups.Group.@name | string | | IM: Admin |
action_result.data.\*.Record.Field.\*.Groups.Group.@updateDate | string | | 1/18/2006 4:28:14 AM |
action_result.data.\*.Record.Field.\*.Groups.Group.@updateLogin | string | | 2 |
action_result.data.\*.Record.Field.\*.Record.\*.@contentName | string | | 308246 |
action_result.data.\*.Record.Field.\*.Record.\*.@id | string | | 200049 |
action_result.data.\*.Record.Field.\*.Record.\*.@levelId | string | | 60 |
action_result.data.\*.Record.Field.\*.Record.\*.@moduleId | string | | 165 |
action_result.data.\*.Record.Field.\*.Record.\*.@moduleName | string | | Task Management |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.@id | string | | 206 |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.@parentId | string | | |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.@type | string | | 6 |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.@value | string | | 1 |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.@valueID | string | | 406 |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.\*.@firstName | string | | Test |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.\*.@id | string | | 207 |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.\*.@lastName | string | | lab |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.\*.@middleName | string | | |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.\*.@updateDate | string | | 12/15/2022 10:22:17 AM |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.\*.@updateLogin | string | | 2 |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.@firstName | string | | test |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.@id | string | | 190 |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.@lastName | string | | user |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.@middleName | string | | |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.@updateDate | string | | 6/01/2016 12:58:55 AM |
action_result.data.\*.Record.Field.\*.Record.\*.Field.\*.Users.User.@updateLogin | string | | 190 |
action_result.data.\*.Record.Field.\*.Record.@contentName | string | | 308608 |
action_result.data.\*.Record.Field.\*.Record.@id | string | | 210033 |
action_result.data.\*.Record.Field.\*.Record.@levelId | string | | 60 |
action_result.data.\*.Record.Field.\*.Record.@moduleId | string | | 435 |
action_result.data.\*.Record.Field.\*.Record.@moduleName | string | | Incident Journal |
action_result.data.\*.Record.Field.\*.Record.@sequentialId | string | | 1 |
action_result.data.\*.Record.Field.\*.Record.@updateDate | string | | 12/27/2022 9:38:24 AM |
action_result.data.\*.Record.Field.\*.Record.@updateLogin | string | | 208 |
action_result.data.\*.Record.Field.\*.Record.Field.\*.@fileID | string | | 2 |
action_result.data.\*.Record.Field.\*.Record.Field.\*.@fileName | string | | Archive_test.zip |
action_result.data.\*.Record.Field.\*.Record.Field.\*.@height | string | | |
action_result.data.\*.Record.Field.\*.Record.Field.\*.@id | string | | 607 |
action_result.data.\*.Record.Field.\*.Record.Field.\*.@parentId | string | | |
action_result.data.\*.Record.Field.\*.Record.Field.\*.@type | string | | 1 |
action_result.data.\*.Record.Field.\*.Record.Field.\*.@value | string | | |
action_result.data.\*.Record.Field.\*.Record.Field.\*.@valueID | string | | 66329 |
action_result.data.\*.Record.Field.\*.Record.Field.\*.@width | string | | |
action_result.data.\*.Record.Field.\*.Record.Field.\*.Record.@id | string | | 285743 |
action_result.data.\*.Record.Field.\*.Record.Field.\*.Record.@levelId | string | | 37 |
action_result.data.\*.Record.Field.\*.Record.Field.\*.Record.Field.\*.@id | string | | 540 |
action_result.data.\*.Record.Field.\*.Record.Field.\*.Record.Field.\*.@type | string | | 1 |
action_result.data.\*.Record.Field.\*.Record.Field.\*.Record.Field.\*.@value | string | | Soc L1 L1 |
action_result.data.\*.Record.Field.\*.Record.Field.\*.Record.Field.@id | string | | 540 |
action_result.data.\*.Record.Field.\*.Record.Field.\*.Record.Field.@type | string | | 1 |
action_result.data.\*.Record.Field.\*.Record.Field.\*.Record.Field.@value | string | | Test |
action_result.data.\*.Record.Field.\*.Record.Field.\*.Users.User.@firstName | string | | Test |
action_result.data.\*.Record.Field.\*.Record.Field.\*.Users.User.@id | string | | 207 |
action_result.data.\*.Record.Field.\*.Record.Field.\*.Users.User.@lastName | string | | lab |
action_result.data.\*.Record.Field.\*.Record.Field.\*.Users.User.@middleName | string | | |
action_result.data.\*.Record.Field.\*.Record.Field.\*.Users.User.@updateDate | string | | 12/15/2022 10:22:17 AM |
action_result.data.\*.Record.Field.\*.Record.Field.\*.Users.User.@updateLogin | string | | 2 |
action_result.data.\*.Record.Field.\*.Record.Field.@id | string | | 120 |
action_result.data.\*.Record.Field.\*.Record.Field.@type | string | | 1 |
action_result.data.\*.Record.Field.\*.Record.Field.@value | string | | Phoenix PD |
action_result.data.\*.Record.Field.\*.Users.User.\*.@firstName | string | | System |
action_result.data.\*.Record.Field.\*.Users.User.\*.@id | string | | 206 |
action_result.data.\*.Record.Field.\*.Users.User.\*.@lastName | string | | Administrator |
action_result.data.\*.Record.Field.\*.Users.User.\*.@middleName | string | | |
action_result.data.\*.Record.Field.\*.Users.User.\*.@updateDate | string | | 10/6/2020 12:57:15 PM |
action_result.data.\*.Record.Field.\*.Users.User.\*.@updateLogin | string | | 207 |
action_result.data.\*.Record.Field.\*.Users.User.@firstName | string | | System |
action_result.data.\*.Record.Field.\*.Users.User.@id | string | | 2 |
action_result.data.\*.Record.Field.\*.Users.User.@lastName | string | | Administrator |
action_result.data.\*.Record.Field.\*.Users.User.@middleName | string | | |
action_result.data.\*.Record.Field.\*.Users.User.@updateDate | string | | 10/1/2018 8:46:55 AM |
action_result.data.\*.Record.Field.\*.Users.User.@updateLogin | string | | 2 |
action_result.data.\*.Record.Field.\*.multi_value | string | | |
action_result.summary.content_id | numeric | | 210035 |
action_result.message | string | | Ticket retrieved |
summary.total_objects | numeric | | 1 |
summary.total_objects_successful | numeric | | 1 |

## action: 'list tickets'

Get a list of tickets in an application

Type: **investigate** \
Read only: **True**

<p>You must provide both the field name/ID (name_field) and the value to search for (search_value) to search in records. If the combination of field name and search value is incorrect or the user provides neither of them, you may get an unfiltered list. Parameters application, name_field, and search_value are case-sensitive. <br>There are two set of parameters to filter the records: <br><ul><li>search_value and name_filed</li><li>results_filter_json, results_filter_operator and results_filter_equality</li></ul><br>Filters search_value and name_field are applied at the time of fetching the tickets and the results_filter_json, results_filter_operator and results_filter_equality are applied after the data is fetched. If value in both the set of filters are defined then records will be returned which matched both the conditions. <br>For example, if results_filter_json =  <pre>{"Subject" : "This is summary", "Description" : "This is description"}</pre> results_filter_operator = 'and' and results_filter_equality = 'Contains', the records would be filtered in such a way that 'Subject' contains the string 'This is summary' in it and  'Description' contains 'This is description' in it. <br>In results_filter_equality, if 'Equals' is selected then it will check if the field value is same as provided. <br>In results_filter_equality, if 'Contains' is selected then it will check if the given field value contains the provided value. <br>In results_filter_operator, if 'Or' is selected then it will return the records matching at least one of the provided conditions. <br>In results_filter_operator, if 'And' is selected then it will return the records matching all of the provided conditions.</p>

#### Action Parameters

PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**application** | required | Application/Module name (e.g. Incidents) | string | `archer application` |
**max_results** | required | Max number of records to return | numeric | |
**name_field** | optional | Name of field to search in (e.g. "Incident ID") | string | |
**search_value** | optional | Value to search for in this application | string | |
**results_filter_json** | optional | JSON with field names and values of results filter for this application | string | |
**results_filter_operator** | optional | Boolean operator of key/value pairs in the results filter JSON for this application (its value would be "and" if only one condition is specified) | string | |
**results_filter_equality** | optional | Equality operator of key/value pairs in the results filter JSON for this application | string | |

#### Action Output

DATA PATH | TYPE | CONTAINS | EXAMPLE VALUES
--------- | ---- | -------- | --------------
action_result.status | string | | success failed |
action_result.parameter.application | string | `archer application` | Incidents |
action_result.parameter.max_results | numeric | | 100 |
action_result.parameter.name_field | string | | Incident ID |
action_result.parameter.results_filter_equality | string | | Contains Equals |
action_result.parameter.results_filter_json | string | | {'Incident ID': '10000'} |
action_result.parameter.results_filter_operator | string | | AND OR |
action_result.parameter.search_value | string | | 10000 |
action_result.data.\*.@contentId | numeric | `archer content id` | 210035 |
action_result.data.\*.@levelGuid | string | | b0c2da91-167c-4fee-ad91-4b4e7b098b4b |
action_result.data.\*.@levelId | string | | 60 |
action_result.data.\*.@moduleId | string | | 70 |
action_result.data.\*.@parentId | string | | 0 |
action_result.data.\*.Field.\*.#text | string | `ip` | <p>Testing address</p> |
action_result.data.\*.Field.\*.@guid | string | | d00ae4c0-c75f-4eac-8900-81cf93cb4e21 |
action_result.data.\*.Field.\*.@id | string | | 1600 |
action_result.data.\*.Field.\*.@name | string | | Address |
action_result.data.\*.Field.\*.@type | string | | 1 |
action_result.data.\*.Field.\*.@xmlConvertedValue | string | | 2018-10-01T06:59:00Z |
action_result.data.\*.Field.\*.ListValues.ListValue.#text | string | | California |
action_result.data.\*.Field.\*.ListValues.ListValue.\*.#text | string | | Arcsight |
action_result.data.\*.Field.\*.ListValues.ListValue.\*.@displayName | string | | Arcsight |
action_result.data.\*.Field.\*.ListValues.ListValue.\*.@id | string | | 9526 |
action_result.data.\*.Field.\*.ListValues.ListValue.@displayName | string | | California |
action_result.data.\*.Field.\*.ListValues.ListValue.@id | string | | 91 |
action_result.data.\*.Field.\*.multi_value | string | | No |
action_result.summary.records_found | numeric | | 1 |
action_result.message | string | | Tickets retrieved |
summary.total_objects | numeric | | 1 |
summary.total_objects_successful | numeric | | 1 |

## action: 'create attachment'

Create an attachment

Type: **generic** \
Read only: **False**

<p>Newly created attachment ID will be returned. Here the attachment would be created on the path specified in 'file repository' section mentioned in the archer instance configuration <br> (https://help.archerirm.cloud/610-en/content/archercontrolpanel/acp_inst_gen_file_repository_path_designating.htm).</p>

#### Action Parameters

PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**vault_id** | required | Vault ID of the file | string | `vault id` |
**file_name** | optional | File name | string | |

#### Action Output

DATA PATH | TYPE | CONTAINS | EXAMPLE VALUES
--------- | ---- | -------- | --------------
action_result.status | string | | success failed |
action_result.parameter.file_name | string | | test.txt |
action_result.parameter.vault_id | string | `vault id` | f0fee71865babe4df97088370e44b7aa76d949d0 |
action_result.data | string | | |
action_result.data.\*.Attachment_ID | numeric | | 31 |
action_result.summary | string | | |
action_result.message | string | | Attachment created successfully |
summary.total_objects | numeric | | 1 |
summary.total_objects_successful | numeric | | 1 |

## action: 'get report'

Get a list of tickets from a report

Type: **investigate** \
Read only: **True**

<p>The records for a report GUID (guid) are returned. Per page, Archer returns 50 records. Here the behavior of max_pages and max_results would be such that, if max_pages = 1 and max_results = 100, then the action would fetch only 50 records i.e. 1st page. If max_pages = 1 and max_results = 10, the action will return 10 records based on the max_results parameter. <br>Also, the number of columns and record search depends on the columns displayed in reports on the Archer instance's UI, i.e if on UI the "Summary" column is not added to visible columns, it won't be displayed in action output as well as no records will be fetched if used in the filter parameters. <br>For example, if results_filter_json =  <pre>{"Subject" : "This is summary", "Description" : "This is description"}</pre> results_filter_operator = 'and' and results_filter_equality = 'Contains', the records would be filtered in such a way that 'Subject' contains the string 'This is summary' in it and  'Description' contains 'This is description' in it. <br>In results_filter_equality, if 'Equals' is selected then it will check if the field value is same as provided. <br>In results_filter_equality, if 'Contains' is selected then it will check if the given field value contains the provided value. <br>In results_filter_operator, if 'Or' is selected then it will return the records matching at least one of the provided conditions. <br>In results_filter_operator, if 'And' is selected then it will return the records matching all of the provided conditions.</p>

#### Action Parameters

PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**guid** | required | Report GUID | string | `archer guid` |
**max_results** | optional | Max number of records to return | numeric | |
**max_pages** | optional | Max number of report pages to return | numeric | |
**results_filter_json** | optional | JSON with field names and values of results filter for a report | string | |
**results_filter_operator** | optional | Boolean operator of key/value pairs in the results filter JSON for a report (its value would be "and" if only one condition is specified) | string | |
**results_filter_equality** | optional | Equality operator of key/value pairs in the results filter JSON for a report | string | |

#### Action Output

DATA PATH | TYPE | CONTAINS | EXAMPLE VALUES
--------- | ---- | -------- | --------------
action_result.status | string | | success failed |
action_result.parameter.guid | string | `archer guid` | d00ae4c0-c75f-4eac-8900-81cf93cb4e21 |
action_result.parameter.max_pages | numeric | | 10 |
action_result.parameter.max_results | numeric | | 100 |
action_result.parameter.results_filter_equality | string | | Contains Equals |
action_result.parameter.results_filter_json | string | | {'Incident ID': '10000'} |
action_result.parameter.results_filter_operator | string | | AND OR |
action_result.data.\*.@contentId | numeric | `archer content id` | 210035 |
action_result.data.\*.@levelGuid | string | | b0c2da91-167c-4fee-ad91-4b4e7b098b4b |
action_result.data.\*.@levelId | string | | 60 |
action_result.data.\*.@moduleId | string | | 70 |
action_result.data.\*.@parentId | string | | 0 |
action_result.data.\*.Field.\*.#text | string | `ip` | <p>Testing address</p> |
action_result.data.\*.Field.\*.@guid | string | | d00ae4c0-c75f-4eac-8900-81cf93cb4e21 |
action_result.data.\*.Field.\*.@id | string | | 1600 |
action_result.data.\*.Field.\*.@name | string | | Address |
action_result.data.\*.Field.\*.@type | string | | 1 |
action_result.data.\*.Field.\*.@xmlConvertedValue | string | | 2018-10-01T06:59:00Z |
action_result.data.\*.Field.\*.Groups | string | | |
action_result.data.\*.Field.\*.ListValues.ListValue.#text | string | | California |
action_result.data.\*.Field.\*.ListValues.ListValue.@displayName | string | | California |
action_result.data.\*.Field.\*.ListValues.ListValue.@id | string | | 91 |
action_result.data.\*.Field.\*.ScoreCard.@total | string | | 0 |
action_result.data.\*.Field.\*.Users.User.#text | string | | socl1 |
action_result.data.\*.Field.\*.Users.User.@firstName | string | | SOC |
action_result.data.\*.Field.\*.Users.User.@id | string | | 208 |
action_result.data.\*.Field.\*.Users.User.@lastName | string | | L1 |
action_result.data.\*.Field.\*.multi_value | string | | No |
action_result.summary.pages_found | numeric | | 1 |
action_result.summary.records_found | numeric | | 1 |
action_result.message | string | | Tickets retrieved |
summary.total_objects | numeric | | 1 |
summary.total_objects_successful | numeric | | 1 |

## action: 'on poll'

Callback action for the on_poll ingest functionality

Type: **ingest** \
Read only: **True**

This action has a persistent copy of the most recent 'Date Created' value it's seen on any successfully processed record. It uses this to pull all records created since then and creates a Splunk SOAR container for each. Records are pulled by referencing that 'poll_report' key of each cef_mapping entry. If any such entry does not have a 'poll_report' key, it is skipped; otherwise, the Archer report named by that key's value will be used as a list of records to pull and process according to that mapping.

#### Action Parameters

PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**start_time** | optional | Parameter ignored for this app | numeric | |
**end_time** | optional | Parameter ignored for this app | numeric | |
**container_count** | optional | Maximum number of container records to query for | numeric | |
**artifact_count** | optional | Maximum number of artifact records to query for | numeric | |

#### Action Output

No Output

## action: 'assign ticket'

Assign users and/or groups to record

Type: **generic** \
Read only: **False**

Assigns users and/or groups to an record. Users and groups must be specified via ID (Comma-separated values allowed).

#### Action Parameters

PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**application** | required | Application/Module name (e.g. Incidents) | string | `archer application` |
**content_id** | optional | Content ID (Identifies the specific record) | numeric | `archer content id` |
**name_field** | optional | Name of Tracking ID field (e.g. "Incident ID") | string | |
**name_value** | optional | Name of record (e.g. "INC-1234") | string | `archer user friendly id` |
**field_id** | optional | Field id of field to add users or groups | string | |
**users** | optional | Users to assign to incident/tasks. Provide numeric values (Comma-separated values allowed) | string | |
**groups** | optional | Groups to assign to incident/tasks. Provide numeric values (Comma-separated values allowed) | string | |

#### Action Output

DATA PATH | TYPE | CONTAINS | EXAMPLE VALUES
--------- | ---- | -------- | --------------
action_result.status | string | | success failed |
action_result.parameter.application | string | `archer application` | Incidents |
action_result.parameter.content_id | numeric | `archer content id` | 210035 |
action_result.parameter.field_id | string | | Incident Summary |
action_result.parameter.groups | string | | Test Group |
action_result.parameter.name_field | string | | Incident ID |
action_result.parameter.name_value | string | `archer user friendly id` | INC-10009 |
action_result.parameter.users | string | | testuser |
action_result.data.\*.IsSuccessful | boolean | | False True |
action_result.data.\*.RequestedObject.Id | numeric | | 324031 |
action_result.summary | string | | |
action_result.summary.content_id | string | | 324031 |
action_result.message | string | | Groups/Users successfully assigned |
summary.total_objects | numeric | | 1 |
summary.total_objects_successful | numeric | | 1 |

## action: 'attach alert'

Attach Security alert to the record

Type: **generic** \
Read only: **False**

#### Action Parameters

PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**application** | required | Application/Module name (e.g. Security Incidents) | string | `archer application` |
**content_id** | optional | Content ID (Identifies the specific incident) | numeric | `archer content id` |
**name_field** | optional | Name of Tracking ID field (e.g. "Incident ID") | string | |
**name_value** | optional | Name of record (e.g. "INC-1234") | string | `archer user friendly id` |
**field_id** | optional | Field ID of field to edit. If not provided, searches for Field ID of Security Alerts field | string | |
**security_alert_id** | required | Security Alert that will be assigned to record (Comma-separated values allowed) | string | |

#### Action Output

DATA PATH | TYPE | CONTAINS | EXAMPLE VALUES
--------- | ---- | -------- | --------------
action_result.status | string | | success failed |
action_result.parameter.application | string | `archer application` | Incidents |
action_result.parameter.content_id | numeric | `archer content id` | 210035 |
action_result.parameter.field_id | string | | Incident Summary |
action_result.parameter.name_field | string | | Incident ID |
action_result.parameter.name_value | string | `archer user friendly id` | INC-10009 |
action_result.parameter.security_alert_id | string | | 325840 |
action_result.data.\*.IsSuccessful | boolean | | False True |
action_result.data.\*.RequestedObject.Id | numeric | | 324784 |
action_result.summary | string | | |
action_result.summary.content_id | string | | 324784 |
action_result.message | string | | Alert successfully attached to Incident |
summary.total_objects | numeric | | 1 |
summary.total_objects_successful | numeric | | 1 |

______________________________________________________________________

Auto-generated Splunk SOAR Connector documentation.

Copyright 2025 Splunk Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
