# Comparing the live Graphics sheet with DEV

The live Graphics sheet is a read-only source for this process. The initial pass is a comparison, not synchronization: it performs no native row, attachment, formula, automation, sharing or dashboard writes in either sheet. Keep native exports and the report under ignored private local paths; never put real request data in the public repository or GitHub Pages.

Use fresh native Excel exports of the full live and DEV sheets. Confirm their names and include all rows; the portal's selected copied-job list is not a complete DEV-sheet export. Retain filenames, capture times and file hashes. Native source-to-copy row IDs differ, and the available old DEV snapshots are partial, so a job-number match is not proof of a complete three-way merge baseline.

`scripts/compare_smartsheet_exports.py` accepts JSON matrices extracted read-only from those exports. It has no network or native-write functions. For each export, use `{"source":{"filename":"...","sha256":"...","capturedAt":"..."},"sheets":[{"name":"...","rows":[["Graphics Req #","Description","..."],["JOB-1","Example","..."]]}]}`. Run it with `--live`, `--dev` and a private `--out` folder to create an escaped HTML review and JSON evidence.

The report distinguishes:

- Unique live jobs missing from DEV and DEV-only jobs to retain.
- Duplicate or ambiguous job numbers, which are never matched automatically.
- Live job numbers also used by synthetic DEV jobs. Cloned auto-number counters can produce this collision; these are different records, not matching jobs. Resolve the original-live-ID mapping before any import.
- DEV placeholders with a generated number but no project identity are also collision candidates, never automatic matches.
- Different populated values and live blanks that would clear a DEV value. Keep DEV pending explicit conflict review.
- Live values where DEV is blank. These are candidates, not automatically approved fills, because a DEV user may have intentionally cleared the field.
- DEV-only columns, links and calculated/system fields. Keep DEV calculations and native definitions; do not import exported formula results over them.

Native Excel exports omit attachment files and do not preserve Smartsheet formulas, native column types, permissions or cell history. Exported Comments tabs are compared by row reference, text, author and date, retaining duplicate occurrences. Unmapped references are surfaced. Native comment IDs/reply relationships and attachment metadata/files are not proven equivalent by this report. Preserve all DEV-only requests, recoverable deletion state, ownership, AI drafts, reporting metadata and portal links. An approved import needs explicit native-row mapping, fresh source revisions, add-only attachment receipts and a separate DEV-only write boundary; never point a writer at the live sheet.

Review the report before overwriting any differing DEV value. Missing rows may be planned separately, but do not import ambiguous identifiers or change DEV schema silently. A job stored in the DEV sheet but excluded by the portal's copied-row allowlist is a visibility issue, not a missing native row.
