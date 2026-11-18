# DEV portal QA and security review — November 18, 2026

Status: bounded review completed; reproducible fixes loaded into the laptop DEV pilot. **139 automated tests pass (15 JavaScript, 124 Python)**. No authorization bypass was reproduced in the tested cases. This is not an independent penetration test or production security certification.

## Scope and preservation

Reviewed the current authenticated portal, shared job policy, optional Microsoft requester paths, private-state operations, source writes, files, AI handoff, frontend rendering and startup. Live checks were read-only. All creates, offers, acceptances, declines, edits, uploads, stage/archive changes and adversarial inputs used fictional transports and an isolated loopback browser fixture. No native dashboard, form, workflow, schema, formula, sharing configuration or production source was changed. No deletion, email, calendar, SCOUT or Dropbox operation was performed.

Private config and an online SQLite backup were retained before restart. Existing tunnel, expiry, selected copies and feature settings were preserved. Microsoft intake remains disabled pending IT. Scan outputs, fixture scripts and screenshots are ignored by Git; no credentials or private project data are included here.

## Findings and corrections

| Finding | Assessment | Correction / evidence |
| --- | --- | --- |
| Ordinary save JSON accepted duplicate keys | Low severity validation ambiguity; no permission bypass demonstrated. A fictional `hours` field supplied twice was accepted with the last value. | Staff and requester JSON writes now use the strict parser already used for AI. Duplicate keys, non-finite values and nesting beyond 64 levels are rejected. Normal request JSON is capped at 128 KiB; tutorial/sharing retain 4 KiB limits and AI retains its existing bound. Wrong content types are rejected. Ambiguous input now returns 400 before native reads/writes. |
| File MIME parameters disabled otherwise safe previews | Reproducible UX bug for native metadata such as `Text/Plain; charset=UTF-8`. | Preview classification normalizes case and parameters. Plain text stays inert; HTML/unknown active content remains a forced octet-stream download with nosniff. Original source metadata/context fingerprints are preserved. A stored live reference opened correctly after rollout. |
| HTML gateway responses produced misleading JSON errors | Reproducible error-handling bug; failed operations could look like parser errors rather than a network/sign-in problem. | Shared response decoding for staff, requester and AI APIs verifies JSON content type, preserves denied statuses and clearly says an operation is unconfirmed. Unreadable responses fail closed. The isolated browser displayed a clear reconnect message rather than a JSON parser diagnostic. |
| Attachment URL handling accepted arbitrary ports and could raise parser errors | Defense in depth; no actual attacker-controlled Smartsheet URL or credential leak was demonstrated. | Downloads require HTTPS, the existing supported hostname suffixes, no URL credentials and port 443/default. Malformed URLs fail closed. Tests verify no download call for rejected URLs and no Smartsheet Authorization header forwarded to allowed file storage. Redirect blocking remains intact. |
| Restart preflight falsely reported a busy port after shutdown | Reproduced during rollout with no remaining listener. | The port probe now matches the server's SO_REUSEADDR behavior. A real loopback regression verifies a live listener is still rejected and a closed connection does not block restart. Only the explicitly matched owned DEV process was stopped. |
| Outdated environment pip installer | Dependency-maintenance finding, not a reproduced HTTP app exploit. | The installed pip 25.0.1 was updated to 26.3. Runtime app library versions were not changed. The repeat installed-environment scan reports zero known advisories. |

## Automated security coverage

The complete suite, including existing cases, exercises:

- Anonymous access, allowlisted static files, private-path traversal denial and secure error headers.
- Browser-bound, single-use OAuth state; uninvited accounts; verified alias/immutable user binding; session expiry, revocation and logout.
- Coordinator/designer scope, role downgrade during a native read, cross-user/cross-job denial and no shared-token staff fallback.
- Exact Origin and CSRF, disabled DELETE/PUT/OPTIONS/TRACE at the browser API, body limits, malformed/deep/duplicate JSON and non-finite numeric values.
- DEV marker plus saved-filter/source checks, schema/formula protection, workflow review expiry, active-automation denial, copied-row read-only rules, expected revisions and idempotent/uncertain save outcomes.
- Attachment ownership, add-only upload constraints, filenames/content types/size limits, redirect/host/port checks, safe delivery and requester content-hash grants/revocation.
- Microsoft tenant/member/object-ID/role checks, immutable submission ownership, same-email/different-object isolation, private notes excluded from requester projection, original snapshots and no inferred legacy ownership. These remain simulated until real Microsoft activation.
- AI source scope, citation/evidence/coverage validation, prompt injection as inert source text, changed source/file rejection, human-review authority and no automatic business-field/model/email action.
- Stale background results across saves, unsaved-input preservation and background authorization failures.

The bounded login-attempt test runs only in a fixture: thirty attempts fill the current budget and the next receives 429 without contacting an identity provider. No load or stress test was run against the pilot or external services.

## Browser QA evidence

A fictional loopback instance exercised new request submission, searched categories, explicit department entry, details, acceptance, editing an estimate/final date, In Progress → In Review → Completed → Archived, retained archive details and files, a new reference upload, decline back to New and closed-work exclusion from workload. Existing selected-copy mutations are denied by the automated transport cases.

HTML-like request titles, descriptions, filenames and text references were displayed literally; no injected element appeared in the inspected DOM. A parameterized text reference opened in an escaped preformatted preview. Logout followed by browser Back showed the sign-in page rather than the old workspace. A simulated HTML network-gateway page produced the new unconfirmed-operation reconnect message. The fixture was stopped afterward.

After restart, the owner completed Smartsheet consent with a single click. Live read-only checks verified authenticated workspace access, the stored text reference preview and zero edit/stage/upload/AI controls on a copied record. No live source write was attempted as a security probe. The separate test tab was closed and the owner's working tab was preserved.

## Scanners and repeatability

- `pip-audit 2.10.1`: scanned **26 installed packages** in the pilot environment after patching pip; **zero known advisories reported**. This is an advisory-database result at review time, not a proof of vulnerability absence.
- `Bandit 1.9.4`: **zero medium/high and six low alerts**. The low alerts were reviewed: four mark empty-string credential initialization/clearing, and two flag the fixed Python PDF-worker subprocess. That worker uses no shell, accepts file bytes on stdin, and retains timeout/CPU/output/address-space bounds. No broad suppression was added.
- Public configuration, ORNL style, syntax and tracked-text credential-pattern checks pass. A targeted Git-history search for common GitHub/Bearer token patterns found no matches; it is not comprehensive secret forensics.

PR validation now installs the optional pinned scanners from `requirements-security.txt`, audits resolved runtime requirements and fails on medium/high Bandit findings. No cron or unattended AI task was added. Public deployment remains restricted to the existing main-branch path and uploads only fictional `web/` assets.

Local checks:

```sh
npm test
npm run check
python -m bandit -r backend -ll
python -m pip_audit -r requirements-pilot.txt
```

Run scanner commands from a separate tooling environment or CI; do not install tools into a running production service. The actual installed pilot environment was also audited directly by its site-packages path.

## Remaining qualification and open UX issue

1. The owner observed that double-clicking Smartsheet Allow can return to sign-in, while one click works. This is consistent with the one-time callback/state being consumed or replaced; its exact provider/browser race was not isolated. **Keep the one-time protection intact.** Use one click and wait. Improving duplicate-callback UX without accepting replayed credentials remains open.
2. Real Microsoft requester registration, eligibility, dedicated integration identity and independent two-requester tests remain pending IT. Fixture tests do not qualify that live tenant setup.
3. A second designer's independent real-account full flow, cross-browser/mobile/accessibility qualification, production hosting/secret/session operations and an IT-approved independent security assessment remain separate checks before production.
4. Capacity/rate-limit tuning and operational monitoring were not load-tested. The current global pilot login budget can be exhausted by another permitted tunnel visitor. The existing Microsoft tunnel gate, six named staff invites and pilot expiry remain important pilot constraints.
