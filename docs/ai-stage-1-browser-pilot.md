# Stage 1: browser-agent AI briefs

Stage 0's shared job service is complete. Stage 1 implements job context preparation, external-agent JSON import and separate brief review. It works without Smartsheet AI, a portal model key, Microsoft employee intake, MCP or scheduled triggers.

The first release is deliberately agent-assisted: the user asks Codex to analyze a selected job using the authenticated browser. Preparing context does not call a model. Imported analysis is validated and saved in the private portal database; no business fields, native columns, tasks, assignment, email or files are changed by that save.

## Enable for selected synthetic jobs only

All features default off. In the existing private `.local/pilot-config.json`, use:

```json
{
  "ai": {
    "browserPilotEnabled": true,
    "jobIds": ["SYNTHETIC_JOB_ID_1", "SYNTHETIC_JOB_ID_2"]
  }
}
```

Only those exact job IDs are eligible, in addition to the existing approved sheet/filter, native DEV marker, signed-in user's source access and job visibility policy. Do not enable analysis of the whole copied master. Named invites and Smartsheet rights remain authoritative; no shared credential is added to staff sessions. Microsoft intake can remain disabled.

Use Python 3.12/OpenSSL and `requirements-pilot.txt`. For the laptop, `.local/pilot-stage1-venv` is an isolated prepared environment; `start-pilot.command` prefers it when available and otherwise uses the original pilot environment. The running process must be restarted to load new backend routes. On macOS, the launcher retrieves the App secret from Keychain after explicit one-time setup; see the [demo startup guide](demo-startup.md). Leave the existing authenticated tunnel on the same origin. Restarting clears memory sessions, so reconnect to Smartsheet afterward if prompted.

Before startup, back up private config and use SQLite's backup API for the state file. Never copy source data or private evidence into the public repository. Startup applies private schema migration 2, adding only the AI operation ledger and indexes; existing identity bindings, native save receipts, contexts, drafts and review history are retained.

## Browser workflow

1. Sign in to the private pilot with the invited Smartsheet account and open the correct job by job ID.
2. In **AI project brief**, choose references and click **Prepare job context**. All allowlisted request fields are included, including labeled notes in Additional Details.
3. Read the visible JSON context, or use Copy/Download. It includes server-issued context ID, revision/fingerprint, instructions and output schema. Never invent those identifiers or send private context to a public site.
4. Ask your existing Codex agent: “Analyze this selected DEV job and its delivered references. Save a draft brief, proposed tasks and any necessary follow-up questions. Preserve original inputs and do not apply business-field changes.”
5. The agent reads the supplied context and imports only the schema-conforming analysis object in **AI analysis JSON**, then selects **Validate and save draft**.
6. Inspect the brief, proposed checklist, issues/conflicts, draft questions, coverage and evidence-backed field proposals. An authorized editor can **Accept brief in portal** or reject it with a note. Acceptance updates only private review history and the portal's accepted-brief display.
7. Reload to verify persistence. A changed source/reference marks prior analysis stale; prepare a fresh context before accepting it as current.

A browser agent sharing a user's session can exercise that user's visible controls. Recording a review does not independently attest physical human presence. No separate human-attestation mechanism or remote agent grant is claimed.

## Context and reference coverage

Input fields: job title, original request/notes, task categories, requested date, final committed date and deliverables. Contact email/name, charge fields, unrelated jobs and upstream credentials are excluded. AI may propose only allowed blank requested-date/category/deliverables destinations. A populated category such as Other remains populated and cannot be replaced by an AI proposal.

Every permitted row attachment and the two native reference links appear in the reference inventory. The inventory is paginated in batches of 50; context preparation refuses more than 60 combined field/reference entries rather than dropping extra files. A selection can include up to 10 references. Unselected/unsupported/inaccessible/truncated sources remain explicit.

Plain UTF-8 text is supported. An octet-stream `.txt` file is admitted only after strict UTF-8/control-character checks. Text PDFs use pinned pypdf in a separate process with bounded input, timeout/CPU limits, address-space limits where supported, at most 40 pages and 50,000 extracted characters per reference. Scans, encrypted/invalid PDFs, images, archives, Office files and other unsupported formats remain unread; no OCR, active rendering or arbitrary external-link fetch is attempted.

The browser-agent budget is 80,000 extracted characters across selected inputs (below the specification's 150,000 outer limit). It is a character budget, not a promise about a model's token window. Context snapshots include file hashes and extraction/policy versions. Native revision is checked before/after preparation; selected reference bytes are rechecked on import, acceptance and current-status reads. Historical contexts are never silently updated.

## Validation and authority

The backend enforces the published JSON Schema plus semantic checks:

- At most 256 KiB before parsing; reject duplicate JSON keys, invalid UTF-8, non-finite values and malformed shape.
- Issued job/context/fingerprint binding; current session, native source and object access; source freshness.
- Each source accounted for exactly once; a non-delivered/truncated source cannot be declared fully reviewed.
- Real cited source IDs and exact quotes; unique task/issue/question IDs and one proposal per allowed blank field.
- Native category options; dates need explicit ISO or unambiguous English absolute-date evidence. Relative dates have no request-time anchor and cannot be resolved against today.
- Customer questions must link to material issues/conflicts after complete source review. Helpful-only issues do not justify questions. Incomplete coverage prevents definitive missing-information claims/questions until references are reviewed.

Matching quotes establish traceability, not proof that an interpretation is correct. The server cannot verify an agent's comprehension of source material. Review is still necessary, and no imported brief automatically becomes a native field value.

Context preparation requires current job read access. Draft import also requires native write access; it does not write to Smartsheet. Accept/reject additionally requires current job edit permission, including existing DEV write/review gates. A declined/unaccepted offer is not acceptance of a job. Viewer and coordinator/designer restrictions stay enforced in the shared service.

Context, draft and review writes use a durable per-user/action idempotency ledger. Reusing a key for different content conflicts. Local SQLite transactions preserve operation and result together; a failed persistence attempt cannot report success. Draft bodies are immutable versions and reviews append records. Rejection does not delete anything.

## Browser-authenticated endpoints

All routes retain opaque browser-session authentication; mutation routes require exact Origin and CSRF. There is no bearer authentication, MCP transport or general API proxy in this stage.

| Route under `/api/v1/jobs/{jobId}` | Purpose |
| --- | --- |
| `GET /ai` | Current pilot access, recent draft/accepted brief and paginated draft history |
| `GET /reference-inventory` | Complete permitted reference inventory, paginated |
| `POST /intake-contexts` | Prepare selected reference snapshot; required idempotency key |
| `GET /intake-contexts/{contextId}` | Read a scoped historical context and freshness state |
| `POST /ai-drafts` | Validate/import raw analysis JSON; required idempotency key |
| `GET /ai-drafts/{draftId}` | Read a scoped immutable draft and latest review |
| `POST /ai-drafts/{draftId}/reviews` | Accept/reject the private brief; required idempotency key |

Draft/history and reference inventories support `offset` pagination. The UI offers older drafts and additional references explicitly. All context/draft responses are private and no-store.

## Qualification and boundaries

Automated fictional transports and an isolated loopback browser test are prerequisites, not substitutes for real DEV qualification. The Stage 1 exit gate remains **two real users** completing scoped browser analysis. Never impersonate a second designer or claim the gate passed from role-switching/test fixtures.

The live qualification should cover a complete request (zero questions), explicit date in notes, material missing dimensions, attachment facts, source/attachment changes, stale rejection and unchanged native fields/formulas/workflow definitions. Verify source readback and a second person's own sign-in and allowed/denied access. Record limitations and test evidence in the validation receipt.

Business-field apply remains Stage 3; MCP/agent grants remain Stage 2. Native publication, new sheet columns, model runner, unattended jobs, messages, SCOUT and Dropbox remain disabled. Sidecar briefs appear in the custom portal only; native dashboards do not acquire those outputs automatically.

## Pause or rollback

Set `ai.browserPilotEnabled` false to stop AI access while preserving private data and ordinary job behavior. Feature checks reload on requests; refresh the page to remove active controls. Do not erase the private database or restore an older sheet to roll back AI.

Migration 2 is deliberately rejected by older application code that knows only migration 1. The safest rollback is to keep the compatible Stage 1 build with AI disabled. A code downgrade requires a planned, compatible metadata migration/restore that preserves all native save receipts and identities; do not discard newer receipts or blindly reopen uncertain native writes.

## Second real tester checklist

Have an already invited designer use their own Microsoft tunnel session and Smartsheet account. Do not share credentials or count an agent switching fictional roles as this test.

1. The coordinator selects one of the explicitly allowlisted synthetic jobs and offers it to that tester through the existing job controls. This is a real DEV source change; it makes older AI contexts stale. No email is sent by the pilot.
2. The tester opens their offered job and prepares a fresh AI context. They can import a draft while an offer is pending, but cannot accept/reject the brief until existing job edit policy permits it.
3. The tester explicitly accepts the job if participating in this test, then prepares a fresh context after that source change. Have their Codex agent save a draft and verify the authorized brief-review step.
4. Try a known permitted-by-coordinator job belonging to another designer through a direct link; the tester must not receive its job, context, reference or draft payloads.
5. Verify persistence after reload, then sign out and confirm their session can no longer read the saved context/draft. Retain all synthetic jobs, files and analysis history.
6. Record the tester's own observed result and any blocked step. Keep personal details and private evidence outside the public repository.

Only after this and the coordinator's live pass should the two-real-user Stage 1 exit gate be marked complete. Stage 2 remains a separate reviewable implementation for authenticated programmatic/MCP access.
