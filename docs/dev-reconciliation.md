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

Never erase receipts, start a second ledger for the same import, or expand an approved report to bypass a conflict. A changed source version or newly changed DEV value requires inspection. Preserve partial results and receipts, and reconcile actual native state before resuming.

The tool supports only DEV row add/update and add-only discussions/comments. It cannot delete rows, modify columns, upload files, change sharing or send messages. It does not reconcile attachment files or native original creation dates, and it does not enable automations.
