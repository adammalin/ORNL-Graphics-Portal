# Save confirmation and workspace refresh

The DEV workspace is assembled from the synthetic-row filter and a separate, explicitly selected copied-row read. A native save or concurrent edit can advance the sheet version between those reads. Previously, a version mismatch immediately failed the request, and a post-save read failure appeared as an unconfirmed save or an access problem.

## Consistent reads

`SmartsheetReader.projects()` makes up to three complete read attempts for a version mismatch or a temporary upstream failure (429, 500, 502, 503, 504, connection failure or timeout). It starts no further attempt after eight seconds have elapsed; an in-flight GET retains the existing 25-second timeout. These are bounded read retries, not a guaranteed eight-second total deadline.

Each attempt rechecks the native filter, DEV identity, marker, schema and selected source boundaries. Only a complete, internally consistent snapshot publishes a new row selection and cache. Different schema/access levels, bad filters, invalid sources, malformed JSON, and authorization errors are not treated as transient races. No values from different sheet versions are combined. Retries log only a fixed reason and attempt number, never tokens, URLs, row content or employee identities.

Temporary exhaustion returns 503 without resetting the user's sign-in. Permanent source/access failures retain the existing fail-closed behavior.

## Acknowledged saves

An acknowledged native create immediately stores a durable receipt with its permanent row ID before readback. Once available, the generated job number is bound to that same row. Creator ownership survives an unavailable readback, including delayed job-number generation. A completed older receipt cannot claim a replacement row with the same job number.

Edits and attachment uploads retain their existing durable completion receipts. When a subsequent workspace read fails, the authenticated browser API returns `saveConfirmed: true` and a clear saved-but-refresh-pending message. This flag is never returned for an uncertain native write.

The browser may resume that exact acknowledged receipt once, using identical request content and idempotency key. The native writer resolves the stored receipt before mutation, so recovery performs readback without a second native write or upload. Current session, DEV access and source boundaries are still revalidated. Unconfirmed outcomes and ordinary access failures are never automatically replayed.

If receipt recovery also fails, the portal shows a persistent saved/refresh-needed notice, closes stale edit controls and pauses further changes until fresh workspace data loads. Refresh DEV data remains available. Authorization denial during recovery preserves the denial and clears the displayed workspace. Pending attachments may need adding from the saved job after recovery.

## Scope and validation

No live-sheet access, schema migration, notification activation, invitation change, permission expansion or pilot-extension change is required. Every native DEV save still requires all native workflows disabled, the approved workflow review, native edit access, role/ownership permission and a current revision.

Regression tests cover a post-save version race, bounded retries, unchanged last-good cache/row selection on exhaustion, non-retryable source/access changes, confirmed edit/create/upload recovery with one native mutation, delayed generated IDs, creator ownership, replacement-row rejection, uncertain writes, and authorization denial. Browser tests of the error parser and receipt-recovery helper verify the retry boundary and stable request identity. Live DEV smoke testing should create one synthetic request, edit its fields and confirm persistence without a manual refresh or duplicate submission.
