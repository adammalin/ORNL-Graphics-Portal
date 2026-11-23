# Reviewed live-to-DEV reconciliation

This host-only maintenance tool applies a separately reviewed export comparison to the pinned DEV sheet. It is disabled during normal startup. It adds no HTTP or agent endpoint and never exports an OAuth token. Source data, backups, plans and receipts belong in ignored private storage, never this public repository.

The operator must first compare saved native exports and obtain approval for the exact conflicting values, proposed blank fills, missing jobs and comment history. The live sheet remains GET-only. A source job number that already belongs to a DEV test or placeholder is imported as a new row with a new native DEV number. Its source number and row link are retained in Additional Details. Imported comments preserve original author, date and request number in their text; native creation metadata identifies the importing account. Native comments already present on the mapped DEV job with identical text, author and date are preserved without duplication, even if the export comparison missed them. Set `expectedExistingComments` to their verified count and reduce the planned new-comment count accordingly.

## Execution

1. Back up the private configuration and use SQLite's online backup API for portal state. Retain the approved comparison unchanged and hash its bytes.
2. Create a private plan with `sourceSheetId`, `targetSheetId`, immutable `ownerId`, `sourceName`, `sourcePermalink`, `reportPath`, `reportSha256`, `expiresAt` and exact `expectedCounts` (`fields`, `newJobs`, `comments`). Source and target must differ. The plan expires within four hours and within the pilot's existing expiry. Do not place secrets in it.
3. Restart the existing launcher with `--reconciliation-plan "/absolute/private/plan.json"`. The owner signs in through normal Smartsheet OAuth and reviews consent personally. Other admins cannot trigger this plan.
4. The worker captures complete native source/DEV snapshots and discussions, validates the current approved values and DEV destinations, and writes `prepared.json` plus a SHA-256 digest in `status.json`. No native mutation occurs during preparation.
5. Inspect the prepared operations and backups. To apply the already approved comparison, write the exact prepared digest into a host-local `APPLY` file beside the plan. Browser clients cannot arm the import.
6. Monitor `status.json` and durable `receipts.sqlite3`. Before each write, the worker rechecks the owner's current session, global write switch, native review expiry, DEV schema, automation state, native editing permissions and live source version. Locked destinations and protected cells stop the import.
7. On completion, inspect `source-to-dev-mapping.json`, before/after snapshots, discussion readback and `request-audit.json`. The tool verifies every requested native value and comment destination, retention of existing DEV rows, unrelated inputs, attachments and comments, unchanged columns, and identical source snapshots and discussions.
8. Archive the plan and remove the `APPLY` file. Normal future launches omit the flag. If imported copies should appear in the portal, explicitly extend the private copied-row allowlist within its configured cap; do not register copied source records as synthetic jobs or claim creator ownership.

## Interrupted operations

Receipts are recorded before requests. Updates can be recognized by exact native value readback. A new row is identified by its source provenance marker; a comment by its unique source-comment marker. An uncertain create is never blindly repeated. If readback cannot resolve it, the import pauses for inspection. Completed updates that subsequently changed are not replayed.

A specific filtered/copied-row version mismatch during read validation receives up to three brief read-only retries. All access, schema, automation and source-version checks still run, and upstream writes are never retried by this mechanism. Other validation errors pause immediately.

While a plan and its owner's session remain valid, a paused worker can resume without restarting the server: inspect its saved receipts and native readback, then write the canonical JSON SHA-256 digest of the unchanged plan to a host-local `RETRY` file beside it. The worker consumes that file, removes the old `APPLY` file and performs a fresh preflight. Inspect and arm the new prepared digest as usual. This is a host-only action, not a browser/API operation; it cannot renew an expired session, plan or pilot grant.

The host-only retry reloads the installed maintenance module, allowing a tested native-format correction without discarding the active OAuth session. It accepts no module path from a browser or plan. Normal startup has no worker. Native rejection details are retained only in private storage; definite HTTP 400 row-create failures are distinguished from uncertain timeouts. If a representation fix changes a receipt fingerprint, preserve its old fingerprint and the rejection evidence, verify native readback, and explicitly reconcile that failed receipt before retrying. Never alter a completed receipt to replay it.

Never erase receipts, start a second ledger for the same import, or expand an approved report to bypass a conflict. A changed source version or newly changed DEV value requires inspection. Preserve partial results and receipts, and reconcile actual native state before resuming.

The tool supports only DEV row add/update and add-only discussions/comments. It cannot delete rows, modify columns, upload files, change sharing or send messages. It does not reconcile attachment files or native original creation dates, and it does not enable automations.
