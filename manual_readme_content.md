### Authentication

Select an **Authentication type** when configuring the asset:

- **Username and password** is the default for existing assets. Supply the
  username and password. The app obtains and caches an encrypted Archer session
  token.
- **Personal access token** uses an Archer-generated PAT. Generate the token
  in Archer's Personal Access Tokens page and enter it in the asset's
  **Personal access token** field. Username and password can be left blank.
  The app uses the PAT owner's permissions and does not perform password login.

The authentication type determines which credentials are used even when both
credential sets are populated. The PAT is stored as a secret in the asset, and
is not copied into connector state. Changing authentication type clears the
cached login session while retaining ingestion checkpoints.

This customer validation build targets Archer v2025.12.01 under the assumption
that its existing REST and SOAP endpoints accept
`Authorization: Archer session-id="<PAT>"`. SOAP requests also supply the PAT
in their existing `sessionToken` XML parameter. This combination must be
validated on the target deployment before production use.

In PAT mode, **test connectivity** checks REST application metadata and SOAP
group lookup separately. An empty application or group result can still be
successful. The PAT owner needs permission to execute both probe operations;
successful connectivity does not establish permission for every action.

If a PAT expires or is revoked, replace the asset's PAT and run **test
connectivity** again. The next execution reads the updated token. The app does
not automatically rotate PATs or fall back to username/password login. Check
the PAT owner's permissions if Archer denies an operation. Keep **Verify server
certificate** enabled when using a trusted server certificate.

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
- With username/password authentication, this parameter selects domain-user
  login. Leave it blank for local-user login.
- With PAT authentication, the PAT determines the authenticated identity. The
  domain parameter remains available to resolve domain users when creating or
  updating user/group fields. The PAT owner must have the corresponding lookup
  and record permissions.

### Steps to update the session time on Archer UI:

These settings apply to login-generated sessions when using username/password
authentication. PAT expiration is configured separately in Archer.

By default the session timeout in Archer will be 10 minutes, It is recommended to increase the timeout so that a token generated works for longer time.
Steps to update the session timeout:

- Go to Administration settings > Security Parameters

- Select the Security Parameter name to update session timeout for

- Under the Authorization Properties, update the “Session Timeout” value
