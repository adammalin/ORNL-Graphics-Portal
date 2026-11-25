> Current browser integration (2026-11-25): authenticated page WebMCP is implemented in [browser-page-tools.md](browser-page-tools.md). It inherits the existing browser session and has no separate server grant. The unused stdio candidate has been retired. Remote/server-agent sections below remain future design, not deployed capabilities.

> November 23 pilot renewal: the manual automation review may now cover the approved testing window, capped at seven days and the pilot expiration. Per-write native automation checks remain mandatory. See [pilot setup](pilot.md). References below to the 24-hour review describe the earlier policy.

# User, agent and job-ownership security audit

Date: November 18, 2026. Scope: the private DEV Graphics Portal, its browser/API adapters, job service, AI-context/draft routes, reports, references, optional requester integration and local deployment. This is a bounded engineering assessment with adversarial fixtures, not independent penetration-test certification or a qualification of unrelated MCP connections.

## Approved policy

The pilot owner explicitly requested that all six existing invitees become **admins**, and selected **recoverable portal deletion**, rather than permanent Smartsheet row/file deletion. No additional account, source sheet, OAuth scope or tunnel audience is granted by this change.

| Role | Read | Edit | Delete / restore |
| --- | --- | --- | --- |
| Admin | Every currently approved portal job | Any approved test or selected copied DEV job, subject to native edit access, workflow/schema/lock checks and the global write switch | Any approved portal job, recoverably |
| Coordinator | Approved portal jobs and reports | Eligible test jobs; route offers; cannot impersonate another designer's acceptance | Only verified staff-created jobs belonging to that account |
| Designer / ordinary staff | Their verified creations and offered/assigned jobs | Their newly created jobs while New, or their own accepted assignments | Only their verified creations; assignment is not ownership |
| Microsoft requester | Their verified submission and permitted progress/files | Submission and bounded reference upload only | None; requester tracking remains read-only |
| Browser agent | Same authenticated user and job boundary as its browser session | Same backend rules as that user | Same rules as that user; an admin browser session is powerful |
| Separate portal MCP / bearer client | Not enabled | Not enabled | Not enabled |

Admin describes a **portal role**, not a Smartsheet workspace/tenant administrator. Native source access still caps authority. An admin cannot select an arbitrary sheet/row, change formulas/schema/sharing, impersonate designer acceptance, bypass a locked/protected cell or override a global write pause through these endpoints. AI context/draft tools retain their separate, explicitly configured synthetic-job allowlist; admin role does not broaden that processing list.

The `readOnly` source flag remains a legacy marker for copied-source provenance. Non-admins retain read-only copied rows. Admin action permissions are now the authoritative edit check. The public fictional demo does not gain authenticated deletion/admin tools.

## What deletion does

`POST /api/v1/jobs/{job}/lifecycle` accepts one contracted `delete` or `restore` action with the current source revision, lifecycle version, exact job-number confirmation and optional bounded reason. `GET /api/v1/deleted-jobs` shows admins the approved deleted jobs and other staff only their own verified creations. Authentication, exact Origin, CSRF and server-resolved identity remain mandatory.

Delete records a private tombstone; it performs **no Smartsheet DELETE, row update, attachment removal or workflow change**. It hides the job from active/archived portal lists, workload, report generation, normal job/file reads, AI-context/draft operations, requester tracking and requester uploads. Files, native rows, source fields, private AI history and lifecycle history remain intact. Restore reveals the retained native job; it does not reset fields or discard changes made through native Smartsheet while the job was hidden.

Native dashboards/forms/flows continue seeing the native row. This is portal deletion, not a claim that the native row was removed. Restore depends on that native row still existing and remaining within the approved source selection; it cannot undo independent native deletion or an outside API action. The portal has no permanent purge endpoint or automatic job/file purge.

Events retain immutable actor ID, source row/job identity, source revision, reason, timestamp and server-supplied client/origin labels. Repeated operation keys cannot repeat a state transition, switch content, or re-delete a job after restoration. Source edits, stale lifecycle versions, removed source selection and changed authorization fail closed. Lifecycle changes invalidate workspace polling and report snapshots even if Smartsheet's native version stays unchanged.

Private delete/restore needs the global write switch and current native editor access, but does not renew or depend on the 24-hour automation review because no native write occurs. Native editing/uploading still needs that fresh review. This distinction avoids granting native mutation through a private recovery action.

## Findings and hardening

| Finding | Assessment and action |
| --- | --- |
| Existing role model had no distinct admin | Added an explicit verified admin role. All six approved invitees are selected for that role. Payload fields, tutorial choices, browser preview roles and a model's claim of authority do not assign it. |
| Ownership was associated with a visible job number | New creation ownership binds pinned sheet ID + permanent native row ID + generated job ID + immutable upstream user ID. Changing requester name/email does not transfer authority. Missing legacy proof is not guessed from customer email, current assignment or matching titles. |
| A replayed creation receipt could resolve a replacement row reusing the same job number | Creation receipts now retain the permanent created-row ID. Stale retries cannot bind ownership or requester snapshots to replacement rows. This was exercised with fictional out-of-band source replacement; it is not a claim of a demonstrated remote-only exploit against live Smartsheet. |
| Native-version-only polling cannot observe private deletion or an immediate role change | Polling also tracks the server-side principal/invite/write-policy snapshot and lifecycle event revision. It re-scopes data rather than returning an unchanged response after such a change. |
| Hiding only the card would leave alternate paths open | Deleted jobs are also rejected by native edits, uploads, references, AI routes, reporting/profile writes and optional requester tracking/uploads. Report exports revalidate source/metadata/lifecycle fingerprints. File release rechecks deletion after the download. |
| Admin access to selected copied jobs needed a bounded native writer | The exception is established only within an authenticated job-service write context for that approved copied row. It is cleared in `finally`; lower-level writes without that context stay denied. Source selection and role are rechecked before the native write. Non-admin copied-row protection remains in force. |
| Physical deletion remained unavailable | This remains intentional. HTTP DELETE and low-level native DELETE stay blocked. Recoverability is implemented by private state, not by silently adding a dangerous generic source proxy. |

## LLM and MCP trust boundaries

**Portal/browser path:** The backend resolves the actual signed-in person. It never accepts `role`, creator/user ID, a principal object, arbitrary sheet ID, arbitrary source URL or an unissued bearer grant as authority. AI drafts are schema-checked proposals; importing or reviewing one does not apply business fields, execute tools, send messages or approve deletion. Reference text and tool outputs are untrusted data. Existing injection, evidence, source/fingerprint, stale-context and cross-job checks remain relevant.

A browser agent is technically indistinguishable from the person operating that authenticated browser. A typed confirmation is a usability check, **not proof of a separate human approval**. Because all six users are admins, an agent authorized to operate one of their browser sessions can exercise that admin's portal permissions. Prompt instructions alone do not narrow that authority. The application cannot prevent the same agent from using other separately granted tools or credentials.

**Separate API/MCP:** The current capability response still advertises `agentApi=false` and `mcp=false`; the project issues no delegated agent bearer tokens, and exposes no MCP endpoint. `/api/v1` naming alone is not a separate agent authorization flow. The audit tested rejection of unissued bearer credentials and forged identity, not a working OAuth MCP client's delegation/revocation implementation. Do not copy browser cookies/CSRF values into an MCP configuration or expose the local single-user preview server as a multi-user gateway.

Before enabling MCP, require a separate verifier and user-created delegation whose effective rights are the intersection of current user role, current native access, permanent job identity, selected job allowlist, verb scopes, feature/write gates and expiry/revocation. Default grants should be read/context only. Draft submission, business edits, bulk exports and recoverable delete/restore need separate explicit scopes. Admin role must not automatically give every agent grant all admin operations. Keep native permanent deletion absent. Record grant/client/origin information from the verifier, not model input, and qualify a real independent client's full authorization/revocation flow.

**Direct Smartsheet connection:** A separate Smartsheet token or the vendor's general MCP server bypasses this portal's role, ownership, source-selection and recovery checks. Smartsheet's row deletion uses the `WRITE_SHEETS` scope; the general MCP tool catalog includes `delete_rows`. Native access rights also apply, but excluding `DELETE_SHEETS` does not prohibit row deletion. See [Smartsheet's row API](https://developers.smartsheet.com/api/smartsheet/openapi/rows/row), [OAuth scope/access rules](https://developers.smartsheet.com/api/smartsheet/guides/advanced-topics/oauth) and [MCP tool catalog](https://developers.smartsheet.com/ai-mcp/smartsheet/mcp-server-tools).

Use portal-mediated, separately scoped grants for these ownership rules. A direct native connection should not be represented as enforcing them. If ordinary staff must edit through the portal while being unable to edit/delete through native Smartsheet or self-issued native tokens, the current per-user native Editor access is insufficient isolation: IT must design a source-access/service-identity arrangement or another supported native permission boundary. Do not introduce a shared integration token or remove native privileges silently as part of this audit.

**Backend-host access:** An agent with shell/filesystem access as the account running the laptop backend can modify private config, code or SQLite directly. That account is an operational trust boundary; API checks cannot defend against its owner modifying the server. Production should isolate the backend/service account, secrets and state from ordinary client agents and expose only authenticated application interfaces. This audit does not test secret extraction or read process token memory.

## Credentials and production limits

An earlier shared Smartsheet API token was pasted in this chat and was reported to have broader sheet access. It was not reused or re-tested in this audit. Its owner should revoke/rotate it and review dependent connections; portal staff login has no dependency on a shared API-token fallback. The audit does not rotate someone else's credentials or change native sharing.

The private OAuth app secret remains in the existing Keychain-backed launcher; upstream staff tokens remain server-side/in memory. Native OAuth scope, six-account allowlist, pilot expiry, tunnel audience, Microsoft-intake enablement, AI job allowlist and 24-hour native-review rule are not broadened. No actual model provider, unattended worker, email, SCOUT or Dropbox operation is enabled here.

## Validation and rollout

Adversarial tests use fictional accounts, APIs, sources and identifiers. Cases include admin/non-admin ownership, assignee edit vs creator delete, selected copied-row admin edits, native viewer/global-pause denial, identity/role forgery, missing agent auth, wrong confirmations, stale source/state, idempotent replay, same-number replacement rows, changed role/source selection during preflight, hidden-job files/AI/reports, requester tracking/upload denial, and immediate polling scope changes. UI checks exercise typed confirmation, admin delete/restore, creator delete/restore and an assignee's Edit control without a Delete control. Native row count and write count remain unchanged by those private lifecycle transitions.

Migration **5** adds `job_ownership`, `job_lifecycle`, append-only lifecycle events and operation receipts. It preserves existing tables, native fields and files. Existing pre-migration creator rows are retained for history but are not automatically promoted into permanent-row ownership proof. Admins can manage those older jobs; verified ownership reconciliation for a future non-admin must be explicit. Back up config and SQLite before applying the migration; never point an older backend at the newer state file. Preserve a post-upgrade recovery copy before any rollback, which otherwise loses newer sidecar events.

Private fixture scripts, screenshots, scanner results and QA receipts stay ignored under `.local/` and `artifacts/`. The public repository contains fictional fixtures and implementation/documentation only. An independent production security assessment, real Microsoft activation and separate-agent MCP qualification remain open; local scans and tests do not establish the absence of every vulnerability.

Qualification on November 18: **151 Python tests and 15 JavaScript tests passed**, along with static/public-demo checks. Bandit reported zero medium/high findings (six low-severity patterns remain); the installed pilot dependency audit reported no known vulnerabilities. Fictional browser tests completed admin and creator delete/restore, rejected an incorrect confirmation, and showed an accepted non-creator assignee could edit but had no Delete control. All five fictional native rows remained; lifecycle operations added no native writes.

A fresh read-only native workflow review at **2026-11-18 17:50 UTC** found 20 DEV workflows: 19 Inactive and one Unable to run whose menu offered Activate. No native settings were changed. The private review timestamp can therefore be refreshed for the existing 24-hour native-write gate; every actual source write still independently validates automation state.

Pilot rollout verification: config and an online SQLite backup were saved privately before restart. Migration 5 loaded successfully, and all six named invitees validate as admins. After the user completed Smartsheet consent, the live session showed **Adam Malin · admin**; selected copied-job Edit and Move to Deleted controls, the typed-confirmation dialog, the empty Deleted area and Analytics & Reports all loaded without browser console errors. The live deletion dialog was canceled: **zero live job edits or lifecycle transitions** were performed as audit probes. Other invitees were verified in configuration, not impersonated or individually signed in. Implementation review: [draft PR 14](https://github.com/adammalin/ORNL-Graphics-Portal/pull/14).
