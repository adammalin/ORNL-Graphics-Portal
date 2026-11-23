# Starting a laptop demo

## One-time credential setup on this Mac

1. Open [Smartsheet](https://app.smartsheet.com/) using the account that registered the existing pilot app.
2. Select **Account > Developer Tools**, then open **ORNL Graphics Portal - DEV Pilot** with its View/Edit action. This is an in-app modal, not a documented standalone settings URL.
3. Copy **App secret**. This is not a personal API token or your Smartsheet password. You can look it up again here; do not create another app or rotate it just to recover it.
4. Double-click `save-pilot-credentials.command` in the project folder. Paste at its hidden prompt and press Return. Nothing appears as you type. Wait for **App secret saved in macOS Keychain**. The App client ID is loaded from existing private config; if absent, setup asks once and saves it there.
5. If macOS asks, review the Keychain access request for the local Python launcher. The Keychain service is **ORNL Graphics Portal - Smartsheet OAuth DEV**, with the App client ID as account. No secret is embedded in the launcher, PDF, shell arguments, environment or plaintext config.

Run the same setup script after intentionally rotating the App secret, changing the registered client ID or setting up another Mac. Otherwise reuse the saved item. Memory-only fallback: `./start-pilot.command --secret-source prompt`.

## Each demo

1. Keep the laptop awake and online. Connect the VPN if required for the test environment.
2. If the tunnel Terminal is already hosting, leave it running. Otherwise double-click `start-pilot-tunnel.command`. Complete its Microsoft sign-in if requested. Keep that Terminal open; use its printed **Hosting port** HTTPS address.
3. If the server Terminal already says **Authenticated pilot ready**, reuse it. Otherwise double-click `start-pilot.command`. It loads the App ID and Keychain secret automatically. Leave that Terminal open. If port 4175 is occupied, reuse the existing server or stop it with Ctrl+C before relaunching; the launcher does not kill another process.
4. Open the configured HTTPS pilot link. Complete the outer Microsoft tunnel login and the invited Smartsheet account login as needed. Review **Allow** when Smartsheet requests consent.
5. Before a demo involving saves, verify the native DEV workflow review is valid through the current pilot window, pilot/tunnel access have not expired and a synthetic job can be read/saved. The launcher reports when saves are paused. Review the workflows properly; do not change the timestamp merely to bypass the gate. Access expiry renewal is a separate scoped action.

The GitHub Pages site is a fictional demo and does not save to the DEV sheet. Use the tunnel link for actual DEV jobs. Do not tunnel the shared-token local editor on port 4174. Do not start a second backend/tunnel while the existing one is in use.

## Why Smartsheet asks for Allow again

The App secret identifies the application; each person's OAuth access token represents that user's permission. Saving the App secret in Keychain does not save user sessions. This pilot retains opaque browser sessions and access tokens only in memory, discards refresh tokens, expires idle sessions after 30 minutes and caps a session at six hours (or earlier token/app expiry).

Normal navigation and reloads within a valid session do not ask again. A backend restart, explicit sign-out, expired session or another browser leads to a fresh OAuth authorization and can show **Allow** again. This is more than a first-install event in the current pilot. Keeping the backend running reduces interruptions during a demo.

Smartsheet supports refresh tokens. Secure per-user session/token persistence with encryption, rotation and revocation handling could reduce repeat authorization in a hosted version. It is not implemented by this Keychain change, and provider policy/revocation may still require future consent.

## Stop and recover

Press Ctrl+C in the backend Terminal, then in the tunnel Terminal when the demo ends. Retain `.local/pilot-config.json`, `.local/pilot-state.sqlite3` and the Keychain item. Jobs, attachments, drafts and review history persist; signed-in sessions do not.

| Symptom | Next action |
| --- | --- |
| Keychain locked/denied | Unlock the login Keychain and retry; setup does not overwrite an item after denial. |
| Wrong secret / invalid client | Reopen the existing app details, confirm the client ID, then rerun credential setup with the current App secret. |
| Tunnel unavailable | Check the tunnel Terminal, network, Microsoft authentication and access expiration. |
| Board works but saves are paused | Check the configured native workflow-review window, writes switch and your own DEV sheet permissions. |
| Pilot expired | Arrange an authorized renewal of app and tunnel access; the launcher never extends them automatically. |
| You see fictional DEMO jobs | Open the private tunnel link instead of GitHub Pages. |

Official references: [Smartsheet Developer Tools and OAuth](https://developers.smartsheet.com/api/smartsheet/guides/advanced-topics/oauth), [token refresh](https://developers.smartsheet.com/api/smartsheet/openapi/tokens/tokens-getorrefresh). Implementation: `backend/pilot_credentials.py` and the launchers in the project root. Native Smartsheet dashboards and workflows are not changed by starting this portal.
