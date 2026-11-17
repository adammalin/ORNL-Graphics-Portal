# Onboarding and requester tracking

These are separate features sharing the existing authenticated portal. Microsoft intake remains disabled in the laptop configuration until IT registration, eligibility and the approved integration identity are ready. No permission, scope, native Smartsheet asset, copied-project allowlist or notification setting is changed by this implementation.

## First-login walkthrough

The staff portal automatically claims a first showing after a successful authenticated workspace load. A transaction with a unique verified principal key ensures two tabs cannot both claim it. The first-show record is permanent across refreshes, new sessions and server restarts. Exiting, skipping, completing, or changing tutorial content does not schedule another automatic run. Help > Tutorials opens it manually, with an option to resume the saved chapter.

The first step selects Designer or Coordinator. This changes only the curriculum; it does not change the signed-in person's authority. Microsoft requesters receive their own Requester walkthrough. Public fictional previews offer manual training and do not claim to be authenticated first logins.

Each chapter identifies its location in the real interface, explains the workflow and supplies fictional practice controls. Practice state belongs to the tutorial module; no live job, file, model or messaging operation is passed into it. Its only backend calls save tutorial preferences. Controls use their own event namespace rather than the live app's action dispatcher.

- Designer: workspace and offers; acceptance/refusal; details and dates; references; editing; stages and completion/archive; eligible AI draft review; optional requester file visibility; finding retained work.
- Coordinator: incoming requests; full-request review; references; designer offers and responses; workload; plans and dates; eligible AI briefs; optional customer-visible files; completed/archived records.
- Requester: submitting a clear request; files and additional details; own-request status and date interpretation.

AI and staff customer-file lessons are omitted when those features are unavailable. Full curricula have ten designer chapters, eleven coordinator chapters and four requester chapters, including completion. The UI provides Back, Next, chapter navigation, Skip/Exit, saved progress, keyboard focus handling and narrow-screen layouts. Tutorial completion is a user/session preference, not a training certification or independent human-attestation record.

Staff preferences use `/api/onboarding`; requester preferences use `/api/intake/onboarding`. Both provide GET and POST (claim/progress/dismiss/complete), derive the principal on the server and enforce existing same-origin/CSRF rules. No role, identity or source ID comes from the browser. Keys are provider-specific immutable user IDs; cross-provider account linking is not inferred by email.

## Read-only My Requests

The existing Microsoft create-only intake supplies verified tenant/object IDs. New successful submissions now retain an immutable original-input snapshot and permanent source row ID alongside their owned receipt. Tracking lists only receipts belonging to that verified identity and approved sheet. A matching email, job number, URL or Smartsheet staff session does not establish ownership.

`/my-requests` lists owned requests with twenty-item pagination. Its detail view exposes the original submitted title/description/notes/specifications/references, current customer-facing state, accepted designer name, requested versus confirmed dates and explicitly permitted files. It does not expose live Additional Details, internal notes, estimates, charge fields, AI drafts, the whole sheet, or other people's jobs. Original snapshots prevent later internal additions from leaking as customer text.

Current states map to Submitted, Being assigned, Accepted, In progress, In review and Completed. Archived is displayed as Completed. The tracker represents the current state; it does not invent a historical date for each milestone. Status loads on open or Refresh status. Tracking GETs remain available when native writes or workflow review are paused, provided authentication and the source read remain valid.

Earlier receipts without a permanent-row snapshot show tracking unavailable rather than guessing an association. Copied read-only rows are excluded even if an ownership record is misbound. Retrofitting older requests needs a separate verified ownership process; this release does not perform one.

Endpoints under `/api/intake`:

| Route | Behavior |
| --- | --- |
| `GET /my-requests?offset=0` | Owner-only list and pagination |
| `GET /my-requests/{receipt}` | Customer-safe current status and immutable original inputs |
| `GET /my-requests/{receipt}/attachments/{id}` | Owner plus explicit file binding and content-hash check |

These routes expose no PATCH/PUT/DELETE or job-edit POST. Creating a new request and finishing its initial reference upload remain separate existing intake operations; My Requests has no job-edit or upload controls. Staff retain personal Smartsheet OAuth; the employee integration identity never substitutes for a failed staff authorization.

## Customer file visibility

New initial uploads bind the exact returned native attachment ID and uploaded-content hash to the owned receipt. Historical upload receipts without IDs remain filename-only; filenames are never used to guess a download grant.

For eligible Microsoft-submitted jobs, authorized staff can choose Requester access on a file, then explicitly Share with requester or Stop sharing. `GET/POST /api/v1/jobs/{job}/requester-resources` uses the staff session, existing job visibility/edit permissions, current source access, DEV write/review gates, row binding, attachment inventory, source revision and CSRF checks. A source change requires refresh before sharing. The customer never receives the staff API or integration credential.

Sharing reads the selected current version through the staff connection and stores its hash. Download checks ownership, live source/row/file inventory, the hash, current session and a still-active grant before returning bytes. Changed contents are withheld until shared again. Revocation withdraws portal access and appends an audit event; it does not delete or replace the Smartsheet attachment. Files originally submitted by that requester remain their submitted references. Native sheet sharing and email are untouched.

The integration identity must be approved for the source reads required by tracking, not described as a network-level write-only credential. Its employee-facing operations remain narrow. Real Microsoft identity/eligibility and two-account cross-owner testing remain activation prerequisites.

## Private state, rollout and rollback

Migration 3 adds tutorial preferences, immutable submission snapshots, file-visibility metadata and append-only visibility events. It retains all existing bindings, operation receipts, AI contexts, drafts and review history. New upload receipts retain the returned attachment ID; legacy upload receipts remain supported without guessing IDs.

Back up private configuration and use SQLite's online backup API before rollout. Start one compatible backend using the existing Keychain launcher. A restart ends in-memory login sessions; it does not reset tutorial preferences or ownership records. Do not change pilot or tunnel expiry to deploy this feature.

An older schema-2 build deliberately refuses schema 3. Keep a compatible build for rollback and retain the state database; never erase receipts or restore an older database merely to hide the tutorial. Disabling Microsoft intake disables tracking and requester file-sharing routes without removing their records. Native dashboards, forms, filters, workflows, columns, formulas and sharing definitions are preserved.
