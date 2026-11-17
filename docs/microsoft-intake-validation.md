# Microsoft employee intake qualification — 2026-11-17

This stage adds Microsoft-only employee intake before AI Stage 1. It does not activate a new identity provider on the running pilot or change native Smartsheet assets.

## Completed

- Optional single-tenant Microsoft MSAL code flow, profile lookup and tenant/object-ID eligibility checks, distinct requester session and CSRF.
- Requester form with name/email from Microsoft, department prefill, original project details/notes, links, references and minimal private confirmation.
- Separate pinned Smartsheet integration account for create/add-only DEV submissions; no designer authorization fallback.
- Persistent owner-scoped idempotency/receipt records, add-only uploads, quotas and pending-outcome protection.
- Confirmation preserves the original title and displays only requester-uploaded filenames; later internal references are excluded.
- Designer workspace retains personal Smartsheet authorization and existing offer/accept/stage behavior.
- Runtime, static configuration, syntax, brand palette and credential scans.

Automated validation: **5 JavaScript + 55 Python tests = 60 tests**. Tests use fictional identity and Smartsheet transports. The Microsoft adapter test checks the selected single-tenant authority, `User.Read`-only scope, offline scope exclusion, callback and sanitized errors. Other tests exercise state replay/browser binding, Guest/wrong-tenant/ineligible identity rejection, missing profile contact data, independent sessions, source access failure, CSRF/Origin, preflight expiry, no-delete/write restrictions, owned receipts, input preservation, same-key retry across restart, unknown write outcomes, append-only attachments and quota enforcement. The launcher rejects the old macOS system Python/LibreSSL runtime before asking for secrets when Microsoft intake is configured.

Browser qualification used an isolated server on loopback port 4186 with **fictional APIs only**, never the live tunnel. Verified prefilled contact fields, request entry, a reference upload, confirmation, a fresh request and local sign-out. Test-only sign-in bootstrap existed only in an ignored local fixture; it is absent from application source/routes. The fixture was stopped after inspection.

## Not yet proven

The live ORNL Microsoft app registration, consent callback, real directory prefill, integration identity/token approval and real DEV submission/attachment readback remain pending. Entra's **New registration** page returned **You do not have access**, error 401, for the current account. No app, secret or consent grant was created.

The running laptop pilot still uses its prior process and no `microsoftIntake` object was added to its private configuration. No live jobs, native forms, dashboards, reports, sharing, workflow definitions or formulas were edited in this stage. The public Pages site remains a fictional demo.

The existing isolated laptop interpreter is Python 3.9 with LibreSSL, which emits the requests/urllib3 TLS support warning during mocked MSAL tests. Prepare a supported Python 3.12/OpenSSL environment before live authentication. CI uses Python 3.12; a passing CI result is separate from the outstanding live checks.

See [setup, constraints and activation checklist](microsoft-requester-intake.md). A private IT request with the actual tenant/callback/source IDs is saved locally outside tracked source at `.local/Microsoft-Intake-IT-Request.md`.
