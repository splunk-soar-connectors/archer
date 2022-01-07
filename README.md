[comment]: # "Auto-generated SOAR connector documentation"
# RSA Archer

Publisher: Splunk  
Connector Version: 2\.1\.4  
Product Vendor: RSA  
Product Name: Archer GRC  
Product Version Supported (regex): "\.\*"  
Minimum Product Version: 5\.0\.0  

This app implements ticket management actions on RSA Archer GRC

[comment]: # "File: readme.md"
[comment]: # "Copyright (c) 2016-2021 Splunk Inc."
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

### Scheduled \| Interval polling

-   During scheduled \| interval polling, for the first run, the app will start from the first
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
**endpoint\_url** |  required  | string | API endpoint \(e\.g\., http\://host/RSAarcher\)
**instance\_name** |  required  | string | Instance name \(e\.g\., Default\)
**username** |  required  | string | Username
**password** |  required  | password | Password
**verify\_ssl** |  optional  | boolean | Verify server certificate
**cef\_mapping** |  optional  | string | CEF to Archer mapping
**exclude\_fields** |  optional  | string | Fields to exclude \(comma separated\)
**domain** |  optional  | string | User's Domain

### Supported Actions  
[test connectivity](#action-test-connectivity) - Validate the asset configuration for connectivity and field mapping  
[create ticket](#action-create-ticket) - Create a new ticket  
[update ticket](#action-update-ticket) - Update the value of a field of a record  
[get ticket](#action-get-ticket) - Get ticket information  
[list tickets](#action-list-tickets) - Get a list of tickets in an application  
[on poll](#action-on-poll) - Callback action for the on\_poll ingest functionality  

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

<p>JSON specifying the field names and values for a new Archer record \(key/value pairs\)\. For Cross\-Reference fields, the value must be the content id of the referenced content\.</p><p>Create record sample JSON\: </p><pre><code>\{ "Incident Summary"\: "test incident summary data", "Incident Owner"\: "susan" \}</code></pre><br><p>Parameter application is case\-sensitive\.</p>

#### Action Parameters
PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**application** |  required  | Application/Module name \(e\.g\. Incidents\) | string |  `archer application` 
**json\_string** |  required  | JSON data string | string | 

#### Action Output
DATA PATH | TYPE | CONTAINS
--------- | ---- | --------
action\_result\.status | string | 
action\_result\.parameter\.application | string |  `archer application` 
action\_result\.parameter\.json\_string | string | 
action\_result\.data\.\*\.content\_id | numeric |  `archer content id` 
action\_result\.summary\.content\_id | numeric |  `archer content id` 
action\_result\.message | string | 
summary\.total\_objects | numeric | 
summary\.total\_objects\_successful | numeric |   

## action: 'update ticket'
Update the value of a field of a record

Type: **generic**  
Read only: **False**

There are multiple ways of locating a ticket to update\. You must either give the content ID for the record, which can be obtained from Archer, or by specifying both the name of the Tracking ID field \(name\_field\) and the Tracking ID \(name\_value\)\. If all three parameters are provided, the content ID will be used as an overriding parameter to fetch the ticket\. Parameters application, name\_field, name\_value, field\_id, and value are case\-sensitive\.

#### Action Parameters
PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**application** |  required  | Application/Module name \(e\.g\. Incidents\) | string |  `archer application` 
**content\_id** |  optional  | Content ID \(Identifies the specific record\) | numeric |  `archer content id` 
**name\_field** |  optional  | Name of Tracking ID field \(e\.g\. "Incident ID"\) | string | 
**name\_value** |  optional  | Name of record \(e\.g\. "INC\-1234"\) | string |  `archer user friendly id` 
**field\_id** |  required  | ID or name of the field to update in the record | string | 
**value** |  required  | New value of the record's field | string | 

#### Action Output
DATA PATH | TYPE | CONTAINS
--------- | ---- | --------
action\_result\.status | string | 
action\_result\.parameter\.application | string |  `archer application` 
action\_result\.parameter\.content\_id | numeric |  `archer content id` 
action\_result\.parameter\.field\_id | string | 
action\_result\.parameter\.name\_field | string | 
action\_result\.parameter\.name\_value | string |  `archer user friendly id` 
action\_result\.parameter\.value | string | 
action\_result\.data | string | 
action\_result\.summary\.content\_id | numeric |  `archer content id` 
action\_result\.message | string | 
summary\.total\_objects | numeric | 
summary\.total\_objects\_successful | numeric |   

## action: 'get ticket'
Get ticket information

Type: **investigate**  
Read only: **True**

There are multiple ways of locating a ticket to update\. You must either give the content ID for the record, which can be obtained from Archer, or by specifying both the name of the Tracking ID field \(name\_field\) and the Tracking ID \(name\_value\)\. If all three parameters are provided, the content ID will be used as an overriding parameter to fetch the ticket\. Parameters application, name\_field, and name\_value are case\-sensitive\.

#### Action Parameters
PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**application** |  required  | Application/Module name \(e\.g\. Incidents\) | string |  `archer application` 
**content\_id** |  optional  | Content ID \(Identifies the specific record\) | numeric |  `archer content id` 
**name\_field** |  optional  | Name of Tracking ID field \(e\.g\. "Incident ID"\) | string | 
**name\_value** |  optional  | Name of record \(e\.g\. "INC\-1234"\) | string |  `archer user friendly id` 

#### Action Output
DATA PATH | TYPE | CONTAINS
--------- | ---- | --------
action\_result\.status | string | 
action\_result\.parameter\.application | string |  `archer application` 
action\_result\.parameter\.content\_id | numeric |  `archer content id` 
action\_result\.parameter\.name\_field | string | 
action\_result\.parameter\.name\_value | string |  `archer user friendly id` 
action\_result\.data\.\*\.\@contentId | numeric |  `archer content id` 
action\_result\.data\.\*\.\@moduleId | numeric | 
action\_result\.data\.\*\.Record\.\@id | string | 
action\_result\.data\.\*\.Record\.\@sequentialId | string | 
action\_result\.data\.\*\.Record\.\@updateDate | string | 
action\_result\.data\.\*\.Record\.\@updateLogin | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.\@height | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.\@id | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.\@name | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.\@parentId | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.\@type | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.\@updateDate | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.\@updateLogin | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.\@value | string |  `ip` 
action\_result\.data\.\*\.Record\.Field\.\*\.\@valueID | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.\@width | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Groups\.Group\.\*\.\@desc | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Groups\.Group\.\*\.\@id | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Groups\.Group\.\*\.\@name | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Groups\.Group\.\*\.\@updateDate | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Groups\.Group\.\*\.\@updateLogin | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Groups\.Group\.\@desc | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Groups\.Group\.\@id | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Groups\.Group\.\@name | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Groups\.Group\.\@updateDate | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Groups\.Group\.\@updateLogin | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.\*\.\@id | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.\*\.\@levelId | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.\*\.Field\.\*\.\@id | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.\*\.Field\.\*\.\@parentId | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.\*\.Field\.\*\.\@type | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.\*\.Field\.\*\.\@value | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.\*\.Field\.\*\.\@valueID | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.\*\.Field\.\*\.Users\.User\.\@firstName | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.\*\.Field\.\*\.Users\.User\.\@id | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.\*\.Field\.\*\.Users\.User\.\@lastName | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.\*\.Field\.\*\.Users\.User\.\@middleName | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.\*\.Field\.\*\.Users\.User\.\@updateDate | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.\*\.Field\.\*\.Users\.User\.\@updateLogin | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.\@id | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.\@levelId | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.Field\.\*\.\@id | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.Field\.\*\.\@type | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.Field\.\*\.\@value | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.Field\.\@id | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.Field\.\@type | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Record\.Field\.\@value | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Users\.User\.\*\.\@firstName | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Users\.User\.\*\.\@id | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Users\.User\.\*\.\@lastName | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Users\.User\.\*\.\@middleName | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Users\.User\.\*\.\@updateDate | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Users\.User\.\*\.\@updateLogin | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Users\.User\.\@firstName | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Users\.User\.\@id | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Users\.User\.\@lastName | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Users\.User\.\@middleName | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Users\.User\.\@updateDate | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.Users\.User\.\@updateLogin | string | 
action\_result\.data\.\*\.Record\.Field\.\*\.multi\_value | string | 
action\_result\.summary\.content\_id | numeric | 
action\_result\.message | string | 
summary\.total\_objects | numeric | 
summary\.total\_objects\_successful | numeric |   

## action: 'list tickets'
Get a list of tickets in an application

Type: **investigate**  
Read only: **True**

You must provide both the field name/ID \(name\_field\) and the value to search for \(search\_value\) to search in records\. If the combination of field name and search value is incorrect or the user provides neither of them, you may get an unfiltered list\. Parameters application, name\_field, and search\_value are case\-sensitive\.

#### Action Parameters
PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**application** |  required  | Application/Module name \(e\.g\. Incidents\) | string |  `archer application` 
**max\_results** |  required  | Max number of records to return | numeric | 
**name\_field** |  optional  | Name of field to search in \(e\.g\. "Incident ID"\) | string | 
**search\_value** |  optional  | Value to search for in this application | string | 

#### Action Output
DATA PATH | TYPE | CONTAINS
--------- | ---- | --------
action\_result\.status | string | 
action\_result\.parameter\.application | string |  `archer application` 
action\_result\.parameter\.max\_results | numeric | 
action\_result\.parameter\.name\_field | string | 
action\_result\.parameter\.search\_value | string | 
action\_result\.data\.\*\.\@contentId | numeric |  `archer content id` 
action\_result\.data\.\*\.\@levelGuid | string | 
action\_result\.data\.\*\.\@levelId | string | 
action\_result\.data\.\*\.\@moduleId | string | 
action\_result\.data\.\*\.\@parentId | string | 
action\_result\.data\.\*\.Field\.\*\.\#text | string |  `ip` 
action\_result\.data\.\*\.Field\.\*\.\@guid | string | 
action\_result\.data\.\*\.Field\.\*\.\@id | string | 
action\_result\.data\.\*\.Field\.\*\.\@name | string | 
action\_result\.data\.\*\.Field\.\*\.\@type | string | 
action\_result\.data\.\*\.Field\.\*\.\@xmlConvertedValue | string | 
action\_result\.data\.\*\.Field\.\*\.ListValues\.ListValue\.\#text | string | 
action\_result\.data\.\*\.Field\.\*\.ListValues\.ListValue\.\@displayName | string | 
action\_result\.data\.\*\.Field\.\*\.ListValues\.ListValue\.\@id | string | 
action\_result\.data\.\*\.Field\.\*\.multi\_value | string | 
action\_result\.summary\.records\_found | numeric | 
action\_result\.message | string | 
summary\.total\_objects | numeric | 
summary\.total\_objects\_successful | numeric |   

## action: 'on poll'
Callback action for the on\_poll ingest functionality

Type: **ingest**  
Read only: **True**

This action has a persistent copy of the most recent 'Date Created' value it's seen on any successfully processed record\. It uses this to pull all records created since then and creates a Phantom container for each\. Records are pulled by referencing that 'poll\_report' key of each cef\_mapping entry\. If any such entry does not have a 'poll\_report' key, it is skipped; otherwise, the Archer report named by that key's value will be used as a list of records to pull and process according to that mapping\.

#### Action Parameters
PARAMETER | REQUIRED | DESCRIPTION | TYPE | CONTAINS
--------- | -------- | ----------- | ---- | --------
**start\_time** |  optional  | Parameter ignored for this app | numeric | 
**end\_time** |  optional  | Parameter ignored for this app | numeric | 
**container\_count** |  optional  | Maximum number of container records to query for | numeric | 
**artifact\_count** |  optional  | Maximum number of artifact records to query for | numeric | 

#### Action Output
No Output