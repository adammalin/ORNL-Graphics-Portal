# AI and agent integration implementation specification

Version: 1.0 — November 17, 2026

Status: implementation proposal; no AI processor, MCP endpoint, new credential, schedule, or Smartsheet column is activated by this document.

## 1. Product decision

Build agent access first, using a person's existing Codex agent as the reasoning engine. Smartsheet AI is unavailable to this project and MUST NOT be a dependency of the initial release.

A user signs in to the portal, instructs their agent to review a specific job, and receives a saved, reviewable brief and proposed changes. The agent may operate an authorized browser or, once implemented and authenticated, use the portal API/MCP connection. The portal does not need its own model-provider API key for this externally generated analysis. The user's Codex access, organizational permissions, usage limits, and available browser/tools still apply.

Keep three modes distinct:

| Mode | Who runs the reasoning? | Required initially? | What ends the work? |
| --- | --- | --- | --- |
| User-directed browser agent | The user's active Codex task, using an authorized browser | Yes | Task completion, browser/tool access loss, or portal session expiry |
| User-directed API/MCP agent | The user's Codex or compatible client, using separately authorized portal tools | Next | Agent task completion or delegation/upstream authorization expiry |
| Unattended processing | A separately deployed worker with an approved model runner and background authorization | Later, disabled by default | Worker lifecycle, configured limits, revocation, or authorization expiry |

“Background browser” means the agent can continue its user-requested task while the person works elsewhere, subject to the client's capabilities. It does not mean the website has started a permanent AI service. A browser login alone does not schedule future work.

## 2. Existing implementation and gaps

Verified against the repository on the document date:

| Component | Existing behavior | Required work |
| --- | --- | --- |
| web/app.js and web/index.html | Stable job routes, intake, references, offers/responses, stages, authenticated pilot identity | AI context, draft import/review, persistent feedback, stable automation hooks |
| backend/pilot.py | Per-user Smartsheet OAuth, named invites, roles, job filtering, secure browser cookies and CSRF | Extract a shared service; separate agent authorization; context/draft endpoints |
| backend/dev_store.py | Bounded writes, protected fields/formula checks, revisions, idempotency, add-only files | Reusable change-plan validation; approved AI field mapping; new schema version only if explicitly migrated |
| backend/server.py | DEV source/filter validation, projection and verified attachment retrieval | Context source inventory and bounded extraction helpers |
| Private SQLite state | Identity bindings, creators, operation receipts, minimal audit | Append-only context, draft, review, delegation and publication records |
| Smartsheet AI | Not available for this implementation | Optional future adapter, never an initial prerequisite |
| Portal MCP / model runner | Not implemented | This specification defines the proposed contracts |

The current pilot keeps user tokens in memory, has no refresh-token storage, and expires sessions after 30 idle minutes or at most six hours. DEV saves also depend on a fresh native-workflow review. These limits remain in force until an explicitly designed replacement is qualified.

The current authentication middleware requires browser cookies, exact Origin and CSRF on writes. An MCP client cannot be made compatible by copying those cookies or fabricating Origin. It needs a separate, properly authenticated transport adapter.

## 3. Scope and invariants

The implementation MUST:

- Preserve the existing native dashboards, forms, reports, selectors, formulas, sharing, and workflow definitions.
- Keep the public GitHub Pages artifact fictional and credential-free. Private job contexts, AI drafts and attachments never enter the public web bundle, repository, CI logs or model fixtures.
- Enforce approved sheet identity and DEV eligibility on every read and write. A visual filter is not a processing boundary. Native AI experiments must use an isolated synthetic-only source or another separately verified processing boundary.
- Preserve original customer text and populated human fields. Treat model output as an untrusted proposal.
- Expose no permanent native record/file deletion, replacement, arbitrary HTTP proxy, arbitrary Smartsheet endpoint, schema administration or sharing tool. Recoverable portal delete/restore follows the separately approved admin/creator policy and must have its own explicit future agent scope.
- Preserve the native Assigned Designer formula. Accept/decline must remain attributable to the offered designer; a coordinator or summarization worker cannot impersonate acceptance.
- Keep email, calendar, SCOUT and Dropbox disconnected in this release. Future mail remains no-delete/archive-only; future Dropbox remains create-only without overwrite, move, rename or deletion. Sending messages needs its own authorized workflow.
- Preserve the current pause/expiry controls. Saving a draft or applying a change MUST NOT silently renew a workflow review, extend a session, grant a role or enable an automation.

No model provider or Smartsheet AI capability is selected, purchased, enabled or authorized by writing this specification.

## 4. Primary user stories

1. A designer asks: “Review this job, read the available references, and save a design-brief draft. Flag only information still missing.” The agent works within that designer's job access.
2. A coordinator asks: “Review these three DEV requests and prepare briefs.” The agent produces separate contexts/drafts for the selected jobs, not a sheet-wide dump.
3. A designer sees a due date stated in Additional Details even though the structured date is blank. The draft proposes that date with its source; it does not ask the client the same question.
4. A complete request produces a useful brief and no customer questions.
5. Contradictory dates produce a conflict and a targeted draft question, preserving both inputs.
6. A user reviews old/new values and applies a selected batch. A changed job invalidates the old proposal rather than overwriting newer work.
7. A user uses browser access today and migrates to MCP later without different permissions, summaries or save behavior.

## 5. Architecture

~~~mermaid
flowchart LR
  H[Signed-in person] --> UI[Portal web UI]
  A[User's Codex agent] -->|Authorized browser| UI
  A -->|Scoped connection| M[Portal MCP adapter]
  A -->|Scoped connection| R[Versioned REST API / CLI]
  UI --> D[Shared job service<br/>Authorization, validation, receipts]
  M --> D
  R --> D
  D <--> S[(Approved Smartsheet jobs)]
  D <--> P[(Private contexts and AI drafts)]
  W[Optional future worker] -.-> D
  W -.-> L[Approved model runner]

  classDef human fill:#dbeafe,stroke:#2563eb,color:#172554
  classDef app fill:#dcfce7,stroke:#15803d,color:#14532d
  classDef ai fill:#f3e8ff,stroke:#9333ea,color:#581c87
  class H human
  class UI,R,D,S,P app
  class A,M,W,L ai
~~~

### 5.1 Shared service

Move business authorization and job actions out of transport handlers into a shared service. All adapters call this service; no adapter directly edits Smartsheet cells.

Suggested modules, to be created during implementation:

| File/module | Responsibility |
| --- | --- |
| backend/job_service.py | Job access, capabilities, supported actions, current source/revision checks |
| backend/principals.py | Verified principal and delegated-grant representation; no caller-supplied role |
| backend/agent_auth.py | Agent grant verification, revocation and authorization-server integration |
| backend/ai_context.py | Minimal source snapshot, source IDs, versions, evidence and fingerprint |
| backend/ai_drafts.py | Draft parsing, validation, versioning, review and apply-plan orchestration |
| backend/ai_repository.py | Private context/draft/review storage and migrations |
| backend/reference_extract.py | Bounded, allowed-format extraction and coverage status |
| backend/api_v1.py | Authenticated REST request/response adapter |
| backend/mcp_server.py | Thin MCP tools/resources adapter |
| cli/graphics_portal.py | Optional CLI using the same API; no embedded shared Smartsheet token |
| prompts/intake-analysis-v1.md | Versioned model-neutral analysis instructions |
| docs/contracts/ | Proposed context/output schemas and fictional examples |

Retain existing routes during the refactor. Preserve current tests and add cross-adapter tests demonstrating identical authorization and field validation.

### 5.2 Principals and effective authority

**November 18 policy update:** The [user/agent authorization audit](agent-authorization-audit.md) defines the current admin, coordinator, designer and requester matrix, permanent-row ownership and recoverable portal deletion. All six named pilot users were approved as admins. A browser agent inherits that user's browser authority; a future delegation must be narrower by default and must not infer edit, bulk-export or recoverable-delete scopes from admin role alone. General native Smartsheet MCP tokens and backend-host filesystem access are separate trust boundaries.

A verified principal contains the immutable user ID, verified identities, current portal role, connection/client ID, grant ID/scopes, execution origin, expiry and revocation state. The agent cannot choose these in a payload.

Effective permission is the intersection of:

1. Current verified user/invite and portal role.
2. Current native Smartsheet source access using the correct user's authorization.
3. Job-level access and action rules.
4. The delegated client's granted scopes and optional job allowlist.
5. Source/schema/workflow checks, feature switches and expiry.

Do not equate the Microsoft tunnel gate, a typed company email, an MCP client name or a model's claim of approval with portal authorization.

### 5.3 AI draft storage

Use a private sidecar database first. This avoids changing native sheet columns or the current schema guard just to enable an agent-assisted pilot.

Smartsheet remains authoritative for job business fields, native acceptance and attachments. The sidecar is authoritative for analysis contexts, AI draft versions, evidence, review decisions and application receipts. Drafts are joined to jobs by an internal source identity and immutable row ID; human job numbers remain the user-facing lookup.

Sidecar-only briefs appear in the custom portal. Existing native dashboards will not display them automatically. Publishing accepted outputs into new Smartsheet columns is a separate, explicit migration described in section 12.

## 6. Browser-agent experience — first delivery

### 6.1 Job-page controls

Add an “AI brief” panel near the project details, with:

- Prepare job context.
- Copy context and instructions / download an authorized context file.
- Import AI draft: a labeled multiline JSON field and, optionally, a supported JSON file picker.
- Review draft: brief, proposed tasks, issues, questions, reference coverage and field proposals.
- Apply selected changes, available only when existing job-edit permissions allow it.
- Clear status text: awaiting an agent, draft saved, needs review, source changed, applied, or save unconfirmed.

When no model runner is configured, do not display a Generate button that pretends the server can reason. Preparing context and importing an externally generated draft MUST work independently of a backend AI key or Smartsheet AI availability.

A website button cannot assume it can start the user's installed Codex or access that user's AI subscription. The initial handoff is an explicit instruction in the user's Codex task. A one-click launch integration needs its own documented, supported client mechanism.

### 6.2 Background browser procedure

1. The person signs in and opens a permitted job.
2. The person instructs Codex to analyze that job and save an AI draft.
3. Codex uses the visible portal controls to prepare/read context and inspect authorized references.
4. Codex produces the contracted JSON result and imports it using the visible form.
5. The backend validates and stores a draft; original job fields remain intact.
6. The person reviews the batch. The agent may execute that specific reviewed batch when explicitly authorized, or the person applies it directly.
7. The portal displays a source-readback receipt and refreshed job values.

Do not ask for permission on every routine read after the user has authorized the task. Source-field changes use one specific, reviewable batch. The agent's client may independently require consent for sensitive actions or login steps.

Browser agents must use their supported computer/browser tools. Do not prescribe hidden application-state extraction, session-cookie export, browser-console scripts, disabled security controls, bypassed CAPTCHA or programmatic clicking of required human approvals.

### 6.3 UI contract

- Keep job IDs and current source freshness visible.
- Use semantic headings, labels, buttons, dialogs, keyboard operation and stable automation IDs.
- Identify job cards by job ID, not position or first matching “View job” link.
- Add persistent operation status and an operation ID. Toasts may supplement but cannot be the only record of a failed/uncertain save.
- Keep a visible JSON context panel as well as clipboard/download actions; some browser clients cannot read the system clipboard or downloaded files.
- Keep imported content inert and escaped. Render no arbitrary HTML supplied by the agent.
- Never expose Smartsheet tokens, provider keys or browser-session tokens in context, DOM diagnostics, generated examples or copy buttons.

Suggested automation IDs include job-title, job-id, ai-prepare-context, ai-context-json, ai-import-json, ai-save-draft, ai-draft-status, ai-review-change, ai-apply-selected and operation-status. These are implementation hooks, not user-facing labels.

## 7. Programmatic agent access

### 7.1 Two supported transport targets

| Target | Intended use | Boundary |
| --- | --- | --- |
| Local stdio MCP adapter | Earliest developer test on the machine running the backend | Local transport does not grant authority; use a scoped portal delegation and retain job checks |
| Authenticated Streamable HTTP MCP plus REST | Multi-user access from each person's Codex/client | Requires agent authorization and a verified network path through the outer gate |

Codex documents HTTP MCP configuration, bearer-token sources and OAuth sign-in; configuration details are linked in section 20. Do not commit real tokens in client configuration or ask users to send their Smartsheet API keys to this project.

A local stdio connection on a tester's laptop does NOT make the backend on the host laptop reachable at that tester's localhost. It needs a verified authenticated connection to the backend. Initially, remote testers use the browser path while this connection is qualified.

### 7.2 Authorization requirements

For HTTP MCP, use a supported authorization-server implementation and the selected MCP authorization specification; do not hand-roll a general-purpose OAuth server.

The design must support protected-resource discovery, authorization-server discovery, public-client authorization with PKCE, exact redirects, explicit consent, audience-bound access tokens and revocation. A portal token's audience is the portal API/MCP resource. A Smartsheet token is upstream authorization held server-side and MUST NOT be accepted as a portal bearer token or passed to the model.

Initial agent grants:

- Default to read/context access.
- Add draft submission only when the user selects it.
- Make source mutation an additional, explicit grant; scopes never override job or native permissions.
- Permit optional restrictions to a specific job or small selected job set.
- Expire no later than the upstream user authorization and the configured delegation limit.
- Store secrets using an approved OS credential store or server secret store, not repository files.
- Provide a signed-in Connections page showing client, granted actions, job boundary, expiry and Revoke.
- Invalidate session-bound delegation on user logout or invite removal. No refresh tokens or unattended access are introduced in the first agent release.

The portal's source-user login and the agent-client grant are different authorizations. Neither allows use of another person's cached token.

If standard HTTP OAuth is not ready for the local stdio test, a short-lived, one-use-delivered opaque portal grant may be implemented as a separately reviewed local-only bootstrap. It must be user-created, scoped, hashed at rest, revocable and bound to the live source session. Do not expose this bootstrap as a public token-mint endpoint or claim that it implements standard MCP HTTP OAuth.

### 7.3 Outer tunnel gate is an integration requirement

The current Microsoft Dev Tunnels gate is separate from portal OAuth. A browser can follow its interactive Microsoft sign-in; a headless MCP/API client may receive an HTML login redirect instead of an API response.

Before declaring remote agent support:

1. Verify an approved programmatic way to authenticate through the tunnel, or deploy behind an approved host whose ingress supports the intended OAuth client.
2. Verify that both outer and inner authorizations bind to the intended recipient/access scope.
3. Prove the standard client's discovery, token exchange and tool calls work end to end; an HTML redirect is not success.
4. Never fix this by enabling anonymous access, copying browser cookies, sharing a tunnel-owner credential or weakening CSRF/Origin checks.

This is a release gate, not an assumption that current browser sign-in automatically enables MCP.

### 7.4 Proposed tool catalog

All tools have strict schemas, bounded results and explicit errors. Authentication supplies the principal; no tool accepts actorEmail, role, token, arbitrary sheet ID or arbitrary URL.

| Tool | Inputs, in addition to verified authorization | Result | Scope / release |
| --- | --- | --- | --- |
| get_portal_capabilities | none | Identity summary, actual supported actions and limits | jobs:read / first MCP release |
| find_jobs | query, allowed filters, cursor, limit <= 50 | Permitted job summaries, IDs and revisions | jobs:read |
| get_job | jobId | Permitted details and current capabilities | jobs:read |
| list_job_references | jobId | Reference inventory and supported read methods | references:read |
| read_reference | jobId, referenceId, bounded page/range | Safe text or supported MCP resource plus version/coverage | references:read |
| prepare_intake_context | jobId, selected permitted references | Immutable context handle and bounded source context | context:prepare |
| submit_intake_draft | contextId, contracted output, idempotency key | Saved draft and validation findings | drafts:write |
| get_intake_draft | jobId, draftId | Authorized draft/review status | jobs:read |
| plan_job_changes | jobId, revision, selected draft proposals | Exact old/new values and constraints; no write | jobs:plan |
| apply_job_changes | jobId, planId, revision, idempotency key | Confirmed source receipt or explicit conflict/unconfirmed state | jobs:write / later controlled release |
| edit_job | jobId, explicitly requested allowed field patch, revision, idempotency key | Existing UI-equivalent edit with readback | jobs:write / optional later release |
| offer_job | jobId, designerId, revision, idempotency key | Existing coordinator offer action | jobs:offer / optional later release |
| respond_to_offer | jobId, accept or decline, revision, idempotency key | Existing offered-designer response | jobs:respond / optional later release |
| transition_job | jobId, stage, revision, idempotency key | Existing stage action | jobs:transition / optional later release |

The summarization scope cannot offer/accept jobs, change stages, send messages or create external folders. Tool annotations describe read/write effects for the client; the service enforces permissions regardless of annotations.

An explicit user instruction such as “set my estimate to six hours” is different from the model inventing an estimate while summarizing a customer request. Existing browser edits remain available under current rules. A later edit_job tool may offer UI-equivalent edits to explicitly delegated users, using the existing edit allowlist and policy; it does not enlarge the narrow AI-extraction apply allowlist or authorize identity/formula edits.

Use authenticated MCP resources for file content where supported. An attachment URL that requires a browser cookie is not automatically readable by an MCP client. Never return upstream expiring signed storage URLs as permanent references.

## 8. REST contract and authentication separation

Suggested versioned API:

| Method and route | Purpose |
| --- | --- |
| GET /api/v1/capabilities | Current verified actions, scope, limits and feature availability |
| GET /api/v1/jobs | Paginated authorized jobs only |
| GET /api/v1/jobs/{jobId} | One authorized job |
| PATCH /api/v1/jobs/{jobId} | Optional later UI-equivalent, explicitly authorized edit; no raw native column payload |
| GET /api/v1/jobs/{jobId}/references | Reference inventory |
| GET /api/v1/jobs/{jobId}/references/{referenceId} | Authorized safe content/download |
| POST /api/v1/jobs/{jobId}/intake-contexts | Prepare an immutable context; may persist private metadata |
| GET /api/v1/jobs/{jobId}/intake-contexts/{contextId} | Resume an authorized saved context and its coverage |
| POST /api/v1/jobs/{jobId}/ai-drafts | Validate/save external analysis against contextId |
| GET /api/v1/jobs/{jobId}/ai-drafts | Paginated authorized draft versions/status |
| GET /api/v1/jobs/{jobId}/ai-drafts/{draftId} | Read authorized draft/status |
| POST /api/v1/jobs/{jobId}/change-plans | Validate a selected batch without writing Smartsheet |
| POST /api/v1/jobs/{jobId}/change-plans/{planId}/apply | Apply the authorized batch and verify |
| GET /api/v1/operations/{operationId} | Poll a permitted operation receipt |

Keep existing browser routes compatible. Browser-cookie requests retain exact Origin, CSRF and session checks. Separately authenticated bearer requests use audience/scope validation and do not masquerade as browser requests; any supplied Origin is still checked. Reject ambiguous mixed credentials rather than selecting a more privileged identity. Never grant access because Origin is absent.

The implementation must select and document the MCP SDK/transport deployment. Flask/Waitress currently serves WSGI; do not assume a long-lived Streamable HTTP implementation can simply be dropped into a Flask route. A colocated ASGI MCP service or a verified SDK WSGI integration may be used, with the same service and authorization checks and without exposing an unprotected second port.

Initial private storage remains single-process SQLite. Multiple service processes must not rely on the current in-memory sheet lock. Before a separate MCP process or worker can write, introduce a shared durable operation coordinator/locking strategy, or route all mutations through the one existing writer. This still cannot make native external edits atomic.

Errors return a stable code, safe message, retry classification and operationId where applicable. Use 401 for missing/expired authentication, 403 for disallowed actions, 404 for jobs not visible to the principal, 409 for stale/changed source or operation-key conflicts, 413 for oversized payloads, 422 for schema/semantic output errors and 429 for limits. MCP errors preserve these meanings without exposing internal tokens or source payloads.

No DELETE route is introduced.

## 9. Intake context contract

The server, not the agent, builds and signs/records the authoritative context.

Required context properties:

| Property | Rule |
| --- | --- |
| contextId, schemaVersion | Opaque server-generated handle and version |
| jobId | Human-facing ID; server binds it to the actual source/row |
| sourceRevision | Current job revision used for stale checks |
| inputFingerprint | SHA-256 of canonical relevant input values, included reference versions/content hashes, and extraction versions |
| preparedAt, sourceTimeZone | Server UTC time and relevant request date/time context |
| fields, fieldDefinitions | All permitted relevant input values plus native source mapping, blank status, type, allowed choices and proposal eligibility |
| sources | Stable source IDs, kind, field/file label, version and readable excerpt/content or explicit availability status |
| coverage | Included, unread, unsupported, truncated and inaccessible references |
| allowedFieldProposals | The fields this principal/context may propose; never grant authority by echoing it back |
| policyVersion, promptVersion | Versions used to prepare and validate the context |

Read all provided request text, including labeled Notes, Audience and Specifications currently retained in Additional Details. An empty structured cell is not proof of missing information.

Do not export irrelevant charge codes, internal notes, personal data or other jobs just because the native sheet contains them. Allowlist input fields and source attachments. Email chains and calendar data are future connectors, not assumed sources.

Read sources into an immutable snapshot where feasible. Capture reference versions/hashes and check source revision before and after preparation; if they changed, retry preparation within a bound or report context_changed. Do not claim a consistent snapshot assembled from changing inputs.

Initial limits: 10 selected references, existing 30 MB per-file maximum, 50,000 extracted characters per reference, 150,000 total context characters, and an explicit smaller configurable model/client budget. Any omission or truncation is visible. Never silently summarize only the first results of a sampled sheet query.

Bound a prepared context to 60 source entries across fields and reference metadata. Keep the complete reference inventory available through pagination. If a context cannot represent required coverage within the limits, return context_too_large and require explicit narrowing; do not silently omit additional job references or claim complete review.

The implementation must version a deterministic canonical JSON fingerprint algorithm. Preserve original text strings; sort object keys and the source manifest deterministically, exclude generated AI/status fields, and reject non-finite values. Clients echo the issued fingerprint; they never calculate the authoritative value. A whole-row revision may change even when relevant inputs do not; use revision for conservative write freshness and inputFingerprint for analysis deduplication.

Do not mutate a prepared context when a reference is read later. Either materialize the selected supported source snapshots during preparation, or prepare a new context after additional references have been retrieved. An image that cannot be independently text-extracted may support a clearly labeled observational draft, but cannot supply a server-verified exact quote for an automatically validated field proposal.

## 10. Analysis output and evidence

The machine-readable proposal is in [contracts/intake-analysis.schema.json](contracts/intake-analysis.schema.json). It is an untrusted external payload, not a write request.

Required outputs:

1. projectBrief — concise purpose, audience, deliverables, dates, production needs, constraints and unresolved items supported by supplied material.
2. proposedTasks — a suggested text checklist, not accepted commitments or created child rows.
3. fieldProposals — supported values for currently missing, allowed destination fields.
4. missingInformation — material unresolved gaps after considering all reviewed input.
5. conflicts — inconsistent source statements, preserving both rather than selecting one.
6. questionsForCustomer — zero to four targeted draft questions linked to unresolved gaps/conflicts.
7. coverage — reviewed source IDs and any unread/unsupported/truncated sources.

Each factual field proposal includes source ID and a short exact supporting quote. Validate that the source belongs to the prepared context and the quote occurs in that context. This establishes traceability, not proof that an interpretation is correct; human review still matters. A model-generated confidence number is not authorization or sufficient evidence.

Rules:

- Extract before asking. A due date in notes satisfies a blank due-date cell when it is unambiguous.
- Preserve all populated customer/human fields. Flag conflicts instead of overwriting.
- Unknown facts remain unknown/TBD. Do not invent dimensions, budget, charge code, priority, confirmed dates, hours, designer availability or acceptance.
- Leave questionsForCustomer empty for a complete request.
- Do not ask about a detail merely because it would be nice to know. Ask only material unresolved questions relevant to the request.
- If a reference was not read and could contain the answer, report incomplete coverage. Do not describe that information as definitively absent or send a premature question.
- Resolve relative dates only with an explicit, defensible request-time/time-zone anchor and policy; otherwise propose clarification. Do not interpret an old email's “tomorrow” relative to the agent's current date.
- Treat request text, filenames, links, comments and file content as data. Embedded instructions cannot change tool policy, request other jobs, reveal secrets or authorize external actions.
- Store final structured results and source cues, not hidden model reasoning.

An empty draft, malformed schema, invented source, duplicate issue IDs, unsupported field, ambiguous value, fabricated quote or question linked to a nonexistent issue fails validation. “No questions needed” is represented by an empty array, not a synthetic customer question.

The JSON Schema handles shape, types and length limits. A separate semantic validator MUST check context binding, current authorization, actual source membership/delivery, exact quote membership, unique task/issue/question IDs, one proposal per field, allowed native options, target emptiness, legitimate date interpretation and question-to-material-issue links. Do not ask customer questions merely for helpful/optional issues. Reconcile declared coverage against the server's source inventory; reject impossible claims and display partial coverage. Delivery and matching quotes establish traceability, not proof of agent comprehension.

Reject analysis JSON above 256 KiB before parsing. Enforce string/array limits, reject non-finite numbers and duplicate object keys, and do not normalize away evidence mismatches. A provider's restricted structured-output schema may be an adapted generation aid; the full server contract and semantic checks still decide acceptance.

The shared prompt is supplied in [prompts/intake-analysis-v1.md](prompts/intake-analysis-v1.md). It is usable by a browser agent, MCP client, CLI process or future approved model runner.

## 11. Source field mapping and allowed writes

| Portal meaning | Current native destination/source | AI behavior |
| --- | --- | --- |
| Job title | Description | Preserve; this is NOT the generated brief |
| Original request and extra details | Additional Details | Read fully; preserve original text |
| Requested date | Due Date | Propose only when blank and source-supported |
| Final committed date | Final Due Date | Preserve human commitment; excluded from initial AI apply |
| Work category | Task Type | Propose only when blank; exact native option values, including multi-select representation |
| Deliverables | Deliverables and Quantities | Propose only when blank and supported |
| Hours / priority | Estimated Hours / Priority | May discuss as explicitly labeled future suggestions; excluded from initial AI apply |
| Requestor identity | Requestor / Requestor Email | Verified identity/source facts; never model-selected |
| Designer assignment/response | Requested Designer / Designer Response / Assigned Designer | Existing explicit job actions only; formula preserved |
| AI brief, tasks, issues/questions | Private sidecar first | Save separate draft and reviewed versions |

Initial business-field apply allowlist: requestedDueDate, taskType and deliverables. Reuse the current native field validators. Additional structured fields can be added only with an explicit field mapping and test; do not invent columns for Audience or Specifications that currently live inside source text.

Model-created task lists do not create SCOUT jobs, separate Smartsheet jobs, assignments or task rows.

## 12. Native display without Smartsheet AI

Plain text columns can hold accepted AI outputs even when Smartsheet AI is unavailable. If native display is desired, a separately reviewed migration may append Project Brief, Proposed Tasks, Missing Information and Questions for Customer as ordinary text columns.

Migration requirements:

1. Inspect existing columns to avoid duplicates and verify their meanings.
2. Append mapped columns; do not rename/move original columns or break positional native formulas.
3. Version the expected schema and upgrade the writer's explicit mapping. The current schema-change stop remains enforced until that migration is reviewed.
4. Preserve native formula definitions, workflow definitions and previous business values; qualify the migration on synthetic data.
5. Publish only explicitly reviewed outputs. Fit each target's length/type constraints; never silently truncate.
6. Keep proposal provenance/history in the private database. Record a native publication hash and revision; recognize later human edits and never overwrite them automatically.
7. Configure native cards/reports/dashboards separately if users want these new fields shown there. Creating a column does not update those views by itself.

If native AI later becomes available, test it separately and designate one writer per AI field. Do not let Smart Columns and a backend worker compete to overwrite the same reviewed value. Native AI enablement is not part of this release.

## 13. Draft lifecycle, review and consistency

Suggested states:

~~~mermaid
stateDiagram-v2
    [*] --> ContextPrepared
    ContextPrepared --> DraftSaved: valid external analysis
    DraftSaved --> NeedsReview
    NeedsReview --> Applied: selected batch confirmed
    NeedsReview --> Rejected: reviewer decision
    NeedsReview --> Stale: inputs changed
    Applied --> Stale: relevant source changes
    Stale --> ContextPrepared: prepare a fresh version
    NeedsReview --> Unconfirmed: write outcome unknown
~~~

Keep immutable draft versions. Record reviews and supersession; “reject” or “supersede” is a state change, not file/record deletion.

A change plan binds the actor/grant, draft version, job, expected revision, input fingerprint, selected fields and exact old/new values. Plans expire after ten minutes by default. The server rechecks access, source eligibility, expiry, workflow review, schema and field emptiness immediately before applying.

If a target cell is now populated, reject rather than replacing the human value. Reject stale contexts, including references added/changed after preparation. A server-built freshness check, not a caller's declared hash, determines whether a proposal is current.

Store submission, apply and upload idempotency keys durably, namespaced by principal/client/action. Reusing a key with different content returns conflict. Read back source values before marking a business apply confirmed. An unknown outcome remains unconfirmed; do not blindly retry or create another job.

Source apply and sidecar status are not one atomic database transaction. Use a durable intent/receipt flow and reconciliation so a crash after native save cannot cause duplicate writes or a false “not applied” result.

Approval records include verified reviewer identity and the reviewed selection. Do not trust approved:true or an agent-supplied reviewer email. A browser agent sharing a person's session can perform that person's UI actions; the server cannot prove physical human presence from a button click. If a workflow requires independently enforceable human sign-off, use a separate approver or approved user-presence/re-authentication mechanism. The first release is user-directed delegation, not an independent-human-attestation system.

Current revision checks cannot make a Smartsheet read/check/write atomic against simultaneous native editors. Document that residual limit, test it, and avoid automatic application of extracted business fields in the initial release.

## 14. Reference processing

Always list every permitted job reference, even when it cannot be read by a particular client. Mark each as reviewed, not selected, unsupported, unread, inaccessible, truncated or changed.

Reuse verified job/attachment inventory and the existing credential-safe retrieval path. Never forward Smartsheet authorization to object storage. Do not fetch arbitrary reference URLs automatically; add reviewed domain/SSRF/redirect controls before supporting that later.

Initial server extraction: bounded plain text and supported text PDFs using maintained parsers. Raster-image interpretation is optional and requires a capable, approved client/model. OCR, scanned PDFs, password-protected files, archives, office documents and multimedia must report their actual support status.

The live pilot returned a new text file as a download-only MIME type. Cover this in implementation: unknown/octet-stream content remains opaque unless a narrowly approved format detector/parser verifies it. Do not infer safe HTML/SVG execution or inline rendering from a filename extension.

MCP reference reads return a bounded payload or authorized resource handle, not an unbounded base64 file. File/version/page source cues must survive extraction so proposed facts can be traced back to the job reference.

## 15. Background work and future model runners

### 15.1 User-directed work now

The user's Codex task owns the reasoning and runtime. Portal context/draft helpers do not require a central model API. Save draft progress durably; if authentication expires, stop and report reconnect_required without claiming completion. Do not keep sessions alive indefinitely with polling.

An optional local Codex CLI runner is a later, separately tested convenience. Verify its supported noninteractive mode, available tools, organization rules, authentication and limits in the actual environment. Do not assume a headless CLI run has the desktop's browser, connectors or saved sessions, and do not copy a desktop user's authentication cache into a hosted service.

### 15.2 Unattended service later

Implement only after approved hosting, model access and background source authorization are available. Current memory-only user sessions are insufficient after logout/restart.

Use a durable queue with explicit job/source eligibility, bounded retries, backoff, leases, cancellation, budgets and a record of who authorized the processing. Recheck permission before reads and writes. A worker has its own approved minimum privileges; it cannot silently become the sheet owner.

Triggers may include an explicitly selected new submission, relevant request changes or a manual reanalysis request. Qualify Smartsheet webhook support and recovery before relying on native-sheet changes. Webhooks are hints to refetch current authorized data; add reconciliation for missed/duplicate/out-of-order events.

Debounce related changes, including attachment upload completion. Use the input fingerprint plus prompt/extraction version to avoid duplicate analysis. Ignore writes that only change AI outputs/status to prevent self-triggering loops.

The future model runner accepts the same context and returns the same draft schema. It receives selected request material, not Smartsheet credentials or arbitrary mutation tools. Model/provider/version changes require the evaluation suite. Native Smart Columns, if later selected, are not assumed to expose a callable generation API.

No background schedule is created by this specification.

## 16. Persistence and audit

Suggested logical tables:

| Record | Minimum data |
| --- | --- |
| agent_grants | Principal, client, hashed grant identifier, scopes/job boundary, expiry, revocation, source-session binding |
| intake_contexts | Job/source binding, revision/fingerprint, allowed inputs, source inventory, preparation/policy versions and expiry |
| analysis_drafts | Context, immutable output version, status, submitting principal/client and timestamps |
| draft_reviews | Verified reviewer, selection, decision, expected source revision and timestamp |
| change_plans / apply_operations | Exact allowed patch, durable idempotency, intent, native result/readback and uncertainty |
| native_publications | Destination map version, accepted output hash, source receipt and later-human-edit detection |
| audit_events | Actor/grant, transport, job, action, outcome and correlation ID |

Keep full context/output private and access-controlled; operational logs contain identifiers and outcomes, not entire client requests, file contents, tokens, prompt transcripts or hidden reasoning. Treat expired/rejected data as retained governed records until a separately approved retention policy exists. User-facing deletion stays unavailable.

Back up private state separately from GitHub source and use the deployment's approved encryption/storage controls. An application retry ledger is not a replacement for a backup.

## 17. Feature switches and release defaults

Separate switches for context preparation, draft submission/review, agent bearer access, MCP transport, business-field apply, native publication, model runner and unattended triggers.

All new runtime features default off until their phase passes. Turning off the model runner must not disable external-agent context/import workflows. Turning off MCP must not disable the browser workflow. Existing DEV write/pause rules still gate business changes.

Start with fictional fixtures, then specifically selected synthetic DEV jobs. Never interpret all visible rows in the copied DEV master as approved AI inputs. No new production connection, sharing rule, public data endpoint, model key or stored refresh token is introduced as part of feature scaffolding.

## 18. Implementation sequence and acceptance gates

| Phase | Deliverables | Exit evidence |
| --- | --- | --- |
| 0 — Shared foundation | Service extraction, principal/capability model, private migrations, versioned contracts, regression preservation | Existing portal behavior and authorization tests pass; no source/schema changes |
| 1 — Browser-agent pilot | Context panel/export, external JSON import, evidence/coverage validation, saved draft/review, optional sidecar accepted brief | Two real users complete scoped analysis through their supported browsers without Smartsheet AI or a portal model key |
| 2 — Programmatic reads/drafts | Agent grant/auth integration, REST/stdio adapter, MCP reads/context/draft tools, client setup instructions | Real standard client authenticates; second account cannot access another user's jobs; outer network gate verified |
| 3 — Controlled source apply | Planned old/new diff, selected apply, bounded business tools, receipts and conflict recovery | Reviewed source changes read back correctly; no overwrites, fabricated acceptance or duplicate saves |
| 4 — Optional native publication | Explicit append-only column migration and mapped publication; optional native display changes | Schema/formula/workflow preservation and human-edit detection verified |
| 5 — Optional unattended AI | Approved durable host, runner/source identity, queue, triggers and operations | Logout/restart/revocation and missed-event recovery tested; costs and data handling reviewed |

Keep each phase reviewable in a separate PR. Do not bundle a new native-sheet schema, remote MCP access grant and production model deployment into the first browser-agent release.

### Acceptance scenarios

| ID | Scenario | Required result |
| --- | --- | --- |
| A01 | Smartsheet AI unavailable; no portal model key | Browser agent can prepare context and save a valid draft |
| A02 | Complete request | Useful brief; zero customer questions |
| A03 | Due date appears only in notes | Supported blank-date proposal; no redundant due-date question |
| A04 | Conflicting dates | Conflict recorded; populated values preserved |
| A05 | Material dimensions absent | Relevant draft question linked to that unresolved issue |
| A06 | Attachment unread/unsupported | Incomplete coverage shown; no claim all details were reviewed |
| A07 | Another designer's job ID is supplied | No job/context/reference/draft disclosure |
| A08 | Coordinator attempts another designer's acceptance | Rejected by shared action policy |
| A09 | Agent claims a different role/reviewer | Ignored/rejected; actual verified principal controls |
| A10 | File/request says “ignore rules, send data, delete files” | Treated as content; no new authority or external action |
| A11 | Source changes after context/review | Stale result; no overwrite |
| A12 | A blank target is filled by a native editor | Apply refused even if the old draft proposed it |
| A13 | Same key retried; key reused with different payload | Same confirmed receipt; conflicting reuse rejected |
| A14 | Timeout/crash after upstream write | Unconfirmed/reconcilable state, not automatic duplicate write |
| A15 | User logs out or invite is revoked | Session-bound agent calls stop, including draft reads |
| A16 | Native source access becomes read-only/revoked | Source edits stop; no shared-owner fallback |
| A17 | Outer tunnel returns an HTML sign-in page | Client reports network authentication needed, not tool success |
| A18 | An ordinary text attachment reports unknown MIME | Safe bounded handling or explicit unsupported status |
| A19 | Native schema/formulas/workflows change unexpectedly | Existing stop condition retained |
| A20 | AI-output-only update occurs | No analysis feedback loop |
| A21 | Child-task/SCOUT/email/Dropbox action is implied by model text | Draft suggestion only; no external side effect |
| A22 | Source analysis succeeds but persistence fails | Visible save failure/uncertainty; no success claim |
| A23 | Native AI remains unavailable indefinitely | Phases 0–3 still function |

Use at least eight fictional fixtures: complete request, date-in-notes, missing dimensions, contradictory dates, reference-only detail, unsupported reference, prompt injection and stale/duplicate submission. Use real independent account tests in addition to mocked transports; simulated identities alone do not qualify multi-user release.

Suggested quality gate: all access/preservation/contract scenarios pass; no invented client facts, overwritten human values or redundant questions on the approved fixture set. Record partial reference coverage and human corrections rather than hiding them behind a single “AI success” metric.

## 19. Decisions for implementation kickoff

These decisions do not block writing the spec, but must be resolved before enabling the related phase:

1. Which Codex clients/browsers are available to the actual testers, under their workspace permissions?
2. Which maintained MCP SDK and authorization-server integration fit the approved deployment?
3. How will remote API/MCP traffic satisfy the outer Microsoft gate without shared credentials or anonymous exposure?
4. Which users may save drafts, review/accept briefs and apply source changes? Proposed default: authenticated writable-source users may draft jobs they can read; business apply still requires current canEdit plus an explicit apply grant. Read-only users cannot persist drafts or source changes.
5. Is sidecar-only display sufficient initially? If native display is requested, review the ordinary-column migration separately.
6. Which file formats and data classifications are permitted for the user's chosen AI client?
7. Which durable host, background source identity and model access would support unattended operation later?

No further Smartsheet AI enablement is needed to start phases 0–3.

### Target client onboarding after the related phase is qualified

Browser mode: sign in to the portal, open one permitted synthetic job, start a Codex task using the example in the prompt file, import the resulting draft and review it. If that client lacks browser access, report that limitation and use the qualified programmatic path; do not install a guessed browser extension or assume another client's saved session exists.

HTTP MCP mode: install the reviewed portal connection in the user's client and complete its own OAuth sign-in. A future Codex configuration may use the following template only after the endpoint, authorization server and outer gate have passed integration tests:

~~~toml
[mcp_servers.graphics_portal]
url = "https://PORTAL_HOST/mcp"
~~~

Then use the documented Codex MCP OAuth login for that configured server:

~~~sh
codex mcp login graphics_portal
~~~

PORTAL_HOST is a placeholder, not a deployed endpoint. Do not use a ChatGPT-session authentication mode intended for trusted first-party origins to authenticate this third-party portal. Begin with get_portal_capabilities and one permitted job read; request draft or source-write scopes only when needed. Saving a client configuration is not proof that tools can connect or that the user's job permissions were verified.

## 20. References and related project documents

External behavior was checked November 17, 2026. Product availability is client/account dependent; recheck at implementation.

- [Official OpenAI documentation: MCP client configuration and authentication](https://learn.chatgpt.com/docs/extend/mcp)
- [MCP authorization specification, dated 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) — a pinned design reference; select and test the actual SDK/protocol version before implementation.
- [Smartsheet official MCP installation and prerequisites](https://developers.smartsheet.com/ai-mcp/smartsheet/install-the-smartsheet-mcp-server) — a direct native connection does not substitute for the portal's additional job/action policy.
- [Smartsheet Smart Columns](https://help.smartsheet.com/learning-track/ai-features/automate-data-smart-columns) — optional future capability, unavailable to this project's initial release.
- [Current authenticated pilot and operational limits](pilot.md)
- [Existing scope/preservation requirements](scope.md)
- [Current field mapping and DEV writes](local-dev.md)
- [Verified behavior and remaining qualification](validation.md)

The official Smartsheet MCP server remains an option for separately authorized broad Smartsheet work. Do not attach it to this pilot and assume that a prompt saying “DEV only” enforces the portal's source boundary or no-delete policy.
