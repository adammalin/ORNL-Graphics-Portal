# Stage 1 browser-agent pilot qualification

November 17, 2026. Implementation and qualification are separate from enabling unattended AI or native field updates.

## Implemented

- Selected-job context preparation with original request fields, complete reference inventory, strict reference selection, snapshot revisions, deterministic fingerprints and private persistence.
- Bounded UTF-8 text and text-PDF extraction, including checked octet-stream `.txt` handling. Unsupported/unread/inaccessible/truncated sources remain explicit; external URLs are not fetched.
- Visible context/instructions/schema panel, clipboard/download handoff and JSON import in the authenticated job details page.
- JSON Schema plus semantic evidence/coverage/blank-field/date/question validation. Imported content renders as inert escaped text.
- Immutable draft versions, append-only reviews, accepted-brief display, stale-source detection and paginated history. No native business-field apply.
- Per-user/action operation receipts; exact session/source/job authorization shared with existing job behavior; configuration defaults off and requires explicit synthetic job IDs.
- Additive private migration 2. The supported isolated Python 3.12/OpenSSL environment leaves the old running environment intact until restart.

## Automated and isolated browser evidence

Full suite: **5 JavaScript + 76 Python tests = 81 tests passed**. Syntax, public demo configuration, ORNL palette/credential scans, launcher shell syntax and diff whitespace checks passed.

The 21 Stage 1 tests cover complete request/date in notes, material missing dimensions, conflicting dates, octet-stream text, unsupported image and truncation, changed reference bytes without changed metadata, fabricated evidence/source IDs, duplicate issues, populated-field preservation, unsupported fields, relative dates, malicious source instructions, sidecar review/idempotency, stale import/acceptance, cross-user and cross-job reads, viewer/offered-designer restrictions, expiry during preflight, strict raw JSON/size/Origin/CSRF/method checks, persistence failure rollback, text/blank/invalid PDFs and complete-inventory pagination/limits.

Isolated browser testing used only fictional API transports on loopback port 4186. Verified selecting/extracting a text reference, preparing/readable context, importing an agent-written complete-request draft, displaying proposed date/deliverables with exact quotes, zero unnecessary questions, separate accepted-brief review, persistence after reload and unchanged native date/deliverables. The test-only sign-in bootstrap was confined to an ignored local fixture and the fixture was stopped afterward.

Matching quotes and coverage declarations establish traceability; they do not prove comprehension or factual interpretation. The UI labels analysis and task lists as proposals, field values as not applied, and acceptance as a session-bound review rather than independent human attestation.

## Live DEV qualification status

The existing authenticated laptop pilot was reached as the coordinator. Two new, explicitly synthetic DEV requests were created through its existing intake UI: a complete flyer request with a requested date only in notes, and a poster with missing printed dimensions plus an uploaded synthetic text reference. The second request's title, combined notes and attachment were read back through its live job page.

The private config/state were backed up before preparing AI settings. Only those two job IDs are selected in private configuration. Microsoft intake remains off. The original backend process requires a controlled restart and local app-secret entry to load Stage 1. No secret was read from process/browser memory or copied into source.

**Pending:** live Stage 1 context/extraction/import/readback after restart; actual fresh-session behavior; a second real user's permitted/denied analysis journey. The Stage 1 exit gate is not complete until two real users have completed the scoped browser workflow. Automated roles are not counted as real users.

No native dashboard/report/form/column/formula/workflow/sharing definitions were edited. AI outputs remain in the portal's private state, not new Smartsheet fields. MCP, bearer grants, source apply, native publication, model runner, unattended scheduling, messages, SCOUT and Dropbox remain disabled.

## Rollback

Disable the AI feature flag and retain private records. Migration 2 requires compatible code; do not delete/replace the state file or lose native save receipts to downgrade. See [Stage 1 setup and operating boundaries](ai-stage-1-browser-pilot.md).
