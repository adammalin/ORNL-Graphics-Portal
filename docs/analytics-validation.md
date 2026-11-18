# Analytics validation — 2026-11-18

This is DEV validation, not approval for production or a penetration-test certification.

## Verified

- 136 Python regression tests and 15 JavaScript tests pass locally, including 12 reporting tests.
- Reporting arithmetic: received/completed cohort deduplication, zero-count months, partial months, multiple work types, explicit cancellation/archive rules, unknown/reversed dates and confirmed-deadline denominators.
- Access: coordinator-only API, designer denial in the UI, Origin/CSRF, owner-scoped snapshots, expiry, source access revocation, source/metadata conflicts and revalidation after rendering. Crafted invalid export requests fail closed.
- Source protection: reporting profile saves use private sidecar tables, preserve all synthetic API source rows, and perform only native GETs. Copied rows reject annotation. Version checks reject stale saves. No native reporting-field/schema/workflow changes.
- Actual CSV, project CSV, PDF, DOCX and PPTX packages generated and reopened. Long/empty content tested. Spreadsheet formula-like strings are escaped, including native-chart category workbook strings. Missing brand assets fail with a clear error.
- Browser: fictional coordinator classification (including required justification), copied-record viewing, chart filter drill-down, preset changes, section ordering, and all five downloads. Designer direct navigation shows an access message without reporting data or a reporting sidebar link.
- Live DEV: coordinator reporting navigation appeared after sign-in; all five formats downloaded successfully. The inspected snapshot contained 28 period jobs, eight selected copied rows, and source version 187. No live classification changes were saved. These are selected DEV sample counts, not production measurements.
- Responsive layout: narrow 390px viewport (375px content area), no page-wide overflow. Monthly chart and wide tables retain local horizontal scrolling. Desktop view also inspected. No browser console errors observed in the reporting checks.
- PDF/Word/PowerPoint renders inspected using the bundled PDF and LibreOffice runtimes. Rendering configured with the same approved Aptos fonts as the private application. Official presentation logo/artwork remains in the original master; editable native charts and tables reopen. Word/PDF charts are rendered images, with editable Word tables/text and complete category tables.
- `npm run check`: public-demo configuration, palette/font/geometry and secret scans pass. Runtime advisory audit reports no known vulnerabilities. Bandit reports no medium/high findings.

## Evidence and limits

Private generated exports, downloaded live reports, screenshots, render contact sheets, source/version checks and a QA receipt remain under ignored `artifacts/2026-11-18/analytics/`. Licensed report fonts/template remain under ignored `.local/report-assets/`; none are committed to the public repository. A private online SQLite/config backup was taken before migration 4.

The report guide documents scope, calculations, export/register limits, user-owned snapshot lifetime, private assets, migration and rollback. Tests do not enable Microsoft requester intake, AI, email notifications, SCOUT, Dropbox or production sharing. The native Smartsheet dashboards/workflows were not modified. Cross-account authorization was tested with fictional API fixtures, not by impersonating the other invited staff.

PowerPoint and Word packages were reopened programmatically and rendered in LibreOffice. Microsoft Office desktop-specific behavior and recipient font availability remain a demo acceptance check. No claims are made about unavailable native timeline/history, actual hours, full-team utilization, or measured organizational impact.
