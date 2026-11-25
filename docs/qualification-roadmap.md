# Graphics Portal qualification roadmap

Agreed priorities — November 25, 2026. These are planned acceptance checks, not claims of completed qualification or production approval. Start with the complete staff workflow; employee sign-in tests depend on IT setup. Keep classic and guided client layouts available for comparison.

## Verified starting point

The current staff DEV pilot includes guided/classic intake rules, additional Creative Services fields, staff-only lead-time override, submission on behalf of a client with a separate verified submitter, charge capture marked pending validation, browser WebMCP page tools with UI fallback, and reference uploads/downloads. One synthetic request has persisted TXT, PNG and PDF attachments. The corrected PDF viewer rendered the one-page control in a new tab with zoom and page text; both download controls returned identical original bytes. The native-browser PDF candidate failed in Codex and was replaced by the self-hosted viewer.

The latest app regression run passed 45 JavaScript and 244 Python tests (289 total). These automated tests and targeted staff DEV observations do not establish the full lifecycle, cross-user isolation, notification delivery, complex PDF support or production readiness. Exact replay parameters, hashes, attempts, screenshots and unknown credit/USD costs are in the private AI Hub test library. Keep native records, credentials, client artifacts and plaintext browser exports out of this public repository.

## 1. Complete staff request lifecycle — next

**Goal:** prove one realistic request moves reliably from submission through completion and archive.

- Start with the existing authorized synthetic DEV request where practical; a fresh creation test needs its own stable operation ID and clearly fictional input. Do not reuse real client work for destructive or workflow-transition tests.
- Exercise submit, duplicate check, offer/assign, signed-in designer acceptance, permitted status updates, proof attachment, completion and archive.
- Reopen after each transition and use a fresh session where identity changes matter. Compare native-backed field readback, assignment history, timestamps, active workload and archive visibility with expected values.
- Verify assignment does not imply acceptance; only the actual designer records their response. Completion/archive retain the request and attachments. Portal archival is not deletion of native Smartsheet records.
- Pass when every transition persists once, permissions match each actor, and no unrelated row, file, formula or workflow changes. Record any lifecycle action or role not exercised as untested.

**Evidence:** transition matrix (actor, before, action, expected, observed, after), artifact hashes, screenshots, replay inputs and defects. Start here before another stakeholder demonstration.

## 2. Employee access and privacy — blocked on IT configuration

**Goal:** an ORNL employee can submit and track their own request without staff privileges.

- Enable only after the approved Microsoft tenant/app registration and integration connection are configured. Existing staff login is not evidence of employee sign-in readiness.
- Use two distinct employee identities and a staff identity. Test own request, another employee's request, guessed/direct URLs, attachment URLs, sign-out and expired sessions.
- Confirm client name/email and employee ownership remain server-bound. Staff submission on behalf of a client must not silently grant My Requests access.
- Confirm normal clients cannot see or invoke staff overrides, assignment, charge-edit controls, staff-only notes or unshared attachments. Check the server rejects crafted requests as well as hiding UI controls.
- Pass when authorized ownership and file-sharing policy hold for UI and direct endpoints, including after a staff client-identity edit.

**Evidence:** role/resource/action matrix with allow/deny results. Keep test identities and private access receipts outside the public repo.

## 3. Failure recovery and duplicate prevention

**Goal:** interruptions produce an accurate, recoverable state without duplicate requests or files.

- Test double Submit, replay with the same operation ID, changed payload using the same ID, network loss before/after save, stale revision conflicts, expired sign-in and interrupted/failed attachment upload.
- A confirmed saved request stays saved when a later refresh/upload fails. Show its job link and retry the file or refresh; never instruct users to create the request again.
- Preserve typed fields where safe, clear busy states, explain what succeeded and what remains, and prevent retry controls from bypassing permission checks.
- Pass when repeated/recovered operations have one intended effect, failures do not falsely report success, and unrelated changes are preserved.

**Evidence:** failure point, operation ID, response, persisted state, recovery action, retry outcome and duplicate counts. Do not include cookies/tokens.

## 4. Additional-service routing and notifications

**Goal:** photography, video, web, reproduction and poster-printing requests reach the agreed service owners once.

- Review the category-to-recipient mapping with Creative Services. Define the coordinator for mixed requests and an unsure/manual-review path.
- Preserve currently captured selections/details across classic, guided and staff forms. Routing preview is not notification delivery; this feature currently sends no service notifications.
- Prepare a dry-run recipient preview before enabling delivery. Use only explicitly authorized test recipients when testing actual email/workflow sends.
- Test one service, multiple services, overlapping recipient groups, edits, retries and uncertain routing. Define which later changes warrant a new notification.
- Pass when the approved recipients receive the intended notice once per defined event, duplicate recipients are suppressed, failures are visible and delivery evidence is retained.

**Evidence:** approved mapping, event/idempotency rules, dry-run output and authorized delivery receipts. Neither SCOUT nor production Smartsheet automation is changed by this roadmap.

## 5. Deadline and override policy

**Goal:** enforce two business days consistently with the official ORNL calendar and an auditable staff exception.

- Obtain/verify the official ORNL holiday and closure calendar, its owner and update process. A configurable/sample DEV calendar is not official-calendar verification.
- Define the counting rule and timezone explicitly; use the same policy in client UI and server validation.
- Test weekdays, weekends, consecutive holidays, closures, year boundaries, midnight/timezone boundaries and stale open tabs. The server must recalculate at submission.
- Confirm normal clients cannot override. Staff exceptions must preserve the original date, final requested date, actor, timestamp and reason. Decide explicitly whether closures remain prohibited even under override; do not silently change the current behavior.
- Pass when classic/guided/staff forms and backend agree for a frozen calendar/test clock, and allowed exceptions have the agreed audit evidence.

**Evidence:** versioned calendar/source, counting examples, fixed clock/timezone and boundary-case matrix.

## 6. PDF coverage and usability follow-up

**Goal:** qualify beyond the single-page control and make the form usable across input methods/devices.

- Test multipage navigation, first/last boundaries, page changes while rendering, image-only/scanned PDFs, embedded fonts, larger permitted files, malformed/unsupported/password PDFs and download fallback. Download the original for printing, forms and full PDF behavior.
- Test narrow/mobile viewports, overflow/zoom, keyboard order/focus, visible labels/error announcements and recovery without a mouse. Check both intake layouts and staff fields.
- Pass when supported PDFs render correctly, unsupported files fail clearly with original download intact, and critical form actions work with keyboard and narrow screens.

**Evidence:** versioned PDF fixtures, expected pages/content, screenshots, download hashes, device/browser sizes and accessibility findings. Employee attachment previews require their own access-policy qualification.

## Recording and release rules

For each live test, record the exact app commit/source hashes, plugin backend/release where relevant, browser/OS, actor role, fixed inputs, date/calendar settings, operation IDs, attempt count, first/corrected results, limitations and actual observable costs (unknown is not zero). Preserve failures and earlier baselines. Functional checks in an ongoing chat are distinct from fresh-session Test Lab author/reviewer batches; agree on batch scope/budget before launching those.

Record defects with reproduction steps and an expected outcome. Run relevant automated checks after a fix, then repeat only affected live scenarios. Review evidence before widening access. Keep rollback checkpoints and native test files in the dedicated private library; public source documentation must remain free of credentials/client artifacts.
