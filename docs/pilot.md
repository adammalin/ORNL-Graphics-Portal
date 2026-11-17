# Invited Smartsheet OAuth pilot

This service is separate from the local shared-token editor and the public fictional Pages demo. It uses one OAuth token per signed-in person; there is no shared-owner-token fallback. Never tunnel port 4174 or the original `backend/server.py` editor.

## Setup

Use one process on the laptop, behind an authenticated HTTPS development tunnel forwarding to `127.0.0.1:4175`. The tunnel owner signs in through Microsoft Dev Tunnels. Keep the outer tunnel private until the inner application has passed its sign-in and access checks. The printed **Hosting port** URL is authoritative; it can differ from the tunnel ID.

Preserve the browser's original headers before testing saves:

```sh
devtunnel update YOUR_TUNNEL_ID --host-header unchanged --origin-header unchanged
```

Dev Tunnels otherwise rewrites Origin to localhost, which the portal correctly rejects. Preserve the original value; do not loosen the app's exact-origin check or force all origins to a trusted literal. The local `start-pilot-tunnel.command` applies these settings before hosting the existing private tunnel configured by `tunnelId`.

Register an unpublished Smartsheet OAuth app in Developer Tools. Set its app URL to the exact tunnel HTTPS origin and its redirect URL to that origin plus `/auth/smartsheet/callback`. Each user consents to `READ_SHEETS WRITE_SHEETS`. These provider scopes are broader than the app's DEV restrictions: the server enforces the approved sheet/filter, named invites, role, row permissions and no-delete API. Smartsheet consent does not itself restrict the token to one sheet.

```sh
python3 -m venv .local/pilot-venv
.local/pilot-venv/bin/python -m pip install -r requirements-pilot.txt
```

Create a private, permission-600 `.local/pilot-config.json`; never commit it. Example shape (replace placeholders and timestamps):

```json
{
  "publicOrigin": "https://YOUR-PRINTED-TUNNEL-HOST",
  "clientId": "YOUR_REGISTERED_APP_CLIENT_ID",
  "sheetId": "APPROVED_DEV_SHEET_ID",
  "filterId": "APPROVED_DEV_FILTER_ID",
  "statePath": ".local/pilot-state.sqlite3",
  "expiresAt": "REPLACE_WITH_TIMEZONE_AWARE_ISO_TIMESTAMP_WITHIN_7_DAYS",
  "writesEnabled": false,
  "invites": [
    {"email": "coordinator@example.org", "role": "coordinator"},
    {"email": "designer@example.org", "role": "designer"}
  ]
}
```

On macOS, run `./save-pilot-credentials.command` once to save the existing App secret in the login Keychain using a hidden prompt. Find it in Smartsheet: **Account > Developer Tools > ORNL Graphics Portal - DEV Pilot > View/Edit**. It can be looked up again; creating a new app or regenerating the secret is not necessary just because it was not saved earlier. The public App client ID is already in private config; if missing, setup asks once and saves only that identifier there.

Then start `./start-pilot.command`. It retrieves the matching secret from Keychain automatically and keeps it in server memory. A missing item starts explicit one-time setup; a locked/denied Keychain fails closed without replacing anything. macOS may ask permission for the Python interpreter to access the item. The secret is never put in arguments, environment variables, plaintext config, browser output or logs. `./save-pilot-credentials.command` also replaces the saved value after an intentional secret rotation. Do not paste secrets into chat, source files, screenshots or GitHub settings. The App secret is unrelated to a personal Smartsheet API token.

For memory-only entry instead, use `./start-pilot.command --secret-source prompt`; this does not save the secret. Other platforms default to memory-only entry. See the [demo startup guide](demo-startup.md).

Before enabling saves, inspect **all** workflows in the native DEV sheet UI. Smartsheet's automation API does not return multistep workflows, so the API check alone cannot establish that all actions are disabled. Preserve workflow definitions; if anything is active or uncertain, leave pilot saves disabled. Record a completed review with:

```json
{
  "writesEnabled": true,
  "workflowReview": {
    "allNativeWorkflowsChecked": true,
    "reviewedAt": "REPLACE_WITH_CURRENT_TIMEZONE_AWARE_ISO_TIMESTAMP"
  }
}
```

The review expires after 24 hours and automatically pauses saves. Every new write also checks the native DEV filter, assignment formula, schema, API-visible disabled automation rules, row locks, current revision and the signed-in user's write access. If Smartsheet refuses an account's workflow inspection, that account's write fails closed; do not substitute an owner token. Review the account/access requirement before inviting testers.

## Access and behavior

- Exact invited email addresses are matched against Smartsheet's current-user profile, including only confirmed aliases. First sign-in binds the invite to the immutable Smartsheet user ID. Unexpected identity changes require owner review.
- A coordinator can see all synthetic DEV jobs and offer work to invited users. Only the offered designer can accept or decline. A coordinator cannot impersonate the designer's acceptance.
- Designers see jobs offered to them plus requests they created. They can edit accepted assignments or their own still-New requests, subject to their native sheet permissions. Viewer accounts remain read-only.
- Intake uses the verified sign-in name/email. Project details, stage updates and add-only reference uploads persist in Smartsheet. No row, attachment or folder deletion routes exist.
- Workload totals cover invited participants; designers do not receive other designers' job payloads. Calendar availability is not connected. Native Smartsheet access remains separate: portal filtering does not revoke a user's direct sheet access.
- Requests use server-side roles, same-origin CSRF checks and opaque secure cookies. OAuth state is one-use and browser-bound. No tokens or client secrets are included in frontend configuration, application logs or the audit table.
- Sessions expire after 30 idle minutes or at most six hours. Tokens stay in memory; no refresh token is retained. Restarting the process signs everybody out. Provider authorization may remain until revoked in Smartsheet even after the portal discards its token.
- The pilot expires within seven days. Removing an invite from the private config invalidates that account's next request. Roles, review freshness and the write switch reload without restarting. Changing the origin/client/source requires restart.
- The private SQLite file retains invite-to-user bindings, creator ownership, idempotency receipts and minimal action audit entries. Preserve it across restarts to avoid repeating uncertain saves. Do not run replicas against the same sheet.

The six invitees still need their own access to the DEV sheet. The optional [Microsoft employee intake](microsoft-requester-intake.md) supplies a separate `/request` route without employee Smartsheet accounts. It remains disabled pending IT registration and an approved integration connection; production hosting and qualification are separate.

## Verify before sharing

```sh
PATH="$PWD/.local/pilot-venv/bin:$PATH" npm test
npm run check
```

CI installs the pilot dependencies and runs the OAuth HTTP tests. A baseline Python environment without Flask explicitly skips those tests; that baseline run is not pilot validation. Tests exercise two independent identities, token separation, designer/coordinator boundaries, current source access, spoofing, state/cookies, CSRF, expiry/revocation, user-scoped retries and no-delete endpoints.

Automated synthetic transports do not prove live Smartsheet OAuth or a second person's real login. Verify the actual consent callback, source read, synthetic job save, reference upload/readback and sign-out in the browser. Then have a second tester verify their own Microsoft tunnel sign-in and invited Smartsheet account. Do not label those steps complete until observed.

Keep the outer tunnel authenticated. A tenant access rule admits the Microsoft organization to the tunnel boundary; the designer workspace still admits only the exact Smartsheet invite list. Optional employee intake uses its own configured Microsoft eligibility policy and create-only integration service. Confirm the intended Microsoft tenant before enabling such a rule. Do not replace it with an anonymous shared editor. Set tunnel access expiration no later than the app expiration.

## Stop or restart

Keep two Terminal windows open when running the pilot yourself: `./start-pilot-tunnel.command` hosts the existing tunnel, and `./start-pilot.command` starts the backend using Keychain on macOS. The tunnel helper needs `tunnelId` in the private config. Do not start a second host while the existing one is running. The backend launcher checks its port before accessing credentials and explains how to reuse or stop an existing process.

Ctrl+C in the pilot terminal stops the backend and clears in-memory sessions. Stop the tunnel host as well when testing is over. Retain the private SQLite file, configuration and Keychain item; the launcher retrieves the saved App secret on restart. This does not persist user OAuth sessions: users reconnect and can see Smartsheet consent on each fresh authorization, including after restart, explicit sign-out, idle expiry or maximum session expiry. Normal navigation/refresh in a valid session does not reauthorize. Secure per-user token/session persistence and refresh would be a separate change, not part of saving the App secret. Review native workflows again before re-enabling writes after the review expires. The laptop must stay awake, online and connected as required for the pilot link to work.

## References

- [Smartsheet OAuth registration and scopes](https://developers.smartsheet.com/api/smartsheet/guides/advanced-topics/oauth)
- [Automation API limits](https://developers.smartsheet.com/api/smartsheet/openapi/automationrules)
- [Microsoft Dev Tunnels access controls](https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/security)

