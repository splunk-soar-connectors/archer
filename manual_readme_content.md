[comment]: # "File: README.md"
[comment]: # "Copyright (c) 2016-2022 Splunk Inc."
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
