# Coordinator analytics and reports

The private DEV portal includes **Analytics & Reports** at `/#/reports`. Sign in with an invited coordinator or admin account. Designers and Microsoft requesters do not gain reporting access by choosing the coordinator tutorial. The public GitHub Pages demo has no private reporting connection.

## Use the reporting workspace

1. Open **Analytics & Reports** in the sidebar.
2. Choose a period, source, designer, work type, directorate, impact level or current stage. Select **Apply filters / refresh**. Clicking a chart category applies that filter immediately.
3. Review the monthly activity, work types, current stages, directorates, designer completions and workload. The monthly table provides the chart's underlying values. Small screens can scroll the monthly chart and data tables horizontally.
4. Use **Classify a project** to add reporting details to an editable test job. Selected copied projects remain read-only for non-admins; admins may edit them when native checks pass. A high/strategic classification needs a justification. Record intended benefits separately from observed outcomes and link supporting evidence when available.
5. Choose **Executive overview**, **Operations review** or **Impact briefing**. Include/exclude sections and use the arrow buttons to arrange them. Data coverage and definitions are always included.
6. Download a PDF, editable Word document, editable PowerPoint, summary CSV or project CSV. Refresh the report after source changes or a snapshot-expiry message.

Help → Tutorials → Coordinator includes a reporting chapter. Practice content is fictional and does not generate a download or change a real project. Completing this feature does not force existing users through first-login onboarding again.

## Metric definitions

| Measure | Calculation and scope |
| --- | --- |
| Period jobs | Distinct jobs received **or verified completed** within the inclusive date range. A job meeting both criteria is counted once. This is an activity cohort, not all jobs that ever existed before the end date. |
| Received | Valid native `Req Received` date in the period. No date is inferred from title, notes or current time. |
| Verified completions | Current stage Completed with a valid completion date in the period. Archived records also need an explicit Completed reporting outcome or legacy Completed/Closed status. Cancelled/Canceled work is excluded. |
| Average completed/month | Verified completions divided by the calendar months touched by the range. Zero-completion months are included. Partial first/last months are identified; this is not an annualized or prorated rate. |
| Current active | Current stages other than Completed/Archived, across **all dates** within the other filters. This is today's selected backlog, not reconstructed historical backlog. |
| Current estimated hours | Known estimates on accepted active work, across all dates within the other filters. Unknown estimates contribute no invented hours. This is not actual effort or a capacity/utilization percentage. |
| Designer activity | Verified completions for each requested/assigned designer; accepted current active work, pending offers and estimates are shown separately. Unassigned completions can contribute to the overall total without appearing under a named designer. |
| Turnaround | Calendar days from valid received date to completion date, excluding missing/reversed date pairs. The usable sample count is reported. |
| On time | Completion date on/before the **confirmed final due date**, among verified completions with a valid confirmed date. Requested delivery alone is insufficient. The denominator is reported. |
| Work types | Each distinct category on a job contributes once; multi-category sums may exceed distinct jobs. |
| Directorates served | Distinct nonempty coordinator-confirmed directorate tags among period jobs. Unknowns remain Unclassified. Department free text is retained in job CSV; it is not automatically interpreted as a directorate. |
| High/strategic impact | Period jobs explicitly classified High/Strategic with a nonempty justification. This counts classifications, not measured scientific/organizational outcomes. |

Current stages are a current snapshot. The source does not provide a complete transition history; reports cannot claim historical work-in-progress, actual labor, staffing availability, customer satisfaction or demonstrated impact from these fields alone. Reopened work uses its current stage. A reversed date pair remains excluded from turnaround even if the row otherwise satisfies completion rules.

All views/downloads identify the **DEV sample**: permitted test jobs plus explicitly selected copied projects. It is not a Graphics-wide staffing or production total. Missing received dates, missing completion dates, unverified archives, unclassified directorates and sample sizes remain visible. No AI writes classifications or impact statements.

## Reporting fields and persistence

Directorate, division/program, impact level/category, justification, impact statement, intended outcome, observed outcome, evidence URL and reporting disposition are stored in private SQLite sidecar tables keyed by sheet ID and permanent native row ID. The original Smartsheet fields, formulas, attachments, native dashboards, workflows, sharing and schema are not changed. Labels are manually entered; coordinators should use consistent names to avoid split categories.

Only coordinators/admins with current access to the source and current permission to edit the job can change these reporting fields. Existing write-enable, access-level and configured workflow-review safeguards still apply. Only admins may annotate selected copied rows; ordinary staff/coordinators retain copied-row protection. Source revisions and metadata versions prevent stale updates. An existing reporting tag is not automatically synchronized into a native Smartsheet column. Back up the private SQLite database to retain it.

## Download behavior

- **Summary CSV:** normalized section/record/metric/value rows plus scope, applied filters, timestamp, source version and definitions. Section selection/order applies.
- **Project CSV:** one row per matching period job with management fields, reporting tags, source class, dates, fixed portal job URL, filters, generation timestamp and source version. Each job row also carries scope, coverage counts and definitions. It includes all matching period jobs, independent of presentation section selection; an empty result has headers only, so use summary CSV for its coverage details.
- **PDF:** flowing Letter layout with report content on page one, embedded approved Aptos fonts, proportional charts and full category tables; up to 200 register rows. Long register titles are shortened with an explicit note; CSV retains full values.
- **Word:** editable text/tables, chart images, flowing Letter layout, Aptos, fixed table/cell column widths, repeating headers and numbered footers. Short summary/coverage tables stay together. Up to 200 register rows.
- **PowerPoint:** the privately installed official ORNL 16:9 template with its native Title | Standard opening and populated title/date/report placeholders, editable native charts/tables/text, continuation slides and speaker-note definitions. Chart labels and register values can be shortened for legibility; full values remain in CSV. Up to 48 register rows. Designer workload accompanies completion charts.
- Impact spotlights show up to eight jobs in documents/slides. The job CSV contains all matching impact records. Chart images show up to eight categorical entries; PDF/Word tables include all categories. PowerPoint charts continue across slides.
- Scope, filter labels, generation time and source version travel with the documents. Document/summary definitions are retained even when the user omits the quality section in a crafted request. This is a generated report, not an independently approved management statement.

Each snapshot belongs to the immutable signed-in Smartsheet user ID and pinned sheet, expires after 30 minutes (or earlier with session expiry), and is checked against fresh source/version/selection/reporting metadata before and after rendering. Changed/revoked access blocks release. There is no anonymous download URL, shared-token fallback, stored public report file or browser-side export credential. Downloads are `no-store` authenticated POST responses with Origin/CSRF checks. CSV cells that could be interpreted as spreadsheet formulas are escaped, including chart workbook category labels.

Pilot limits: five-year date range within 1900–2100, 5,000 approved source projects, 8 MiB snapshot payload, 30 active snapshots per user, one document renderer at a time per process. Expired generated snapshots are removed during new snapshot creation; source jobs and files are never deleted. Downloads already saved by an authorized user cannot be recalled by changing portal access.

## IT provisioning and rollout

Install `requirements-pilot.txt` in the private backend environment. Provision these approved assets **privately**, outside public static hosting:

```
.local/report-assets/Aptos.ttf
.local/report-assets/Aptos-Bold.ttf
.local/report-assets/ornl-template.potx
```

The template is the approved ORNL 16:9 presentation template, retaining its original logo, master layouts, theme and artwork. Do not place the template or licensed fonts into the public repository or Pages site. Missing assets produce an explicit 503 download error. CSV requires no brand-asset installation. PDF fonts are embedded; Word/PowerPoint recipients need Aptos for faithful editing. The ORNL logo is preserved from the presentation master and is not recreated in PDF/Word. Administrators should confirm the current approved assets and licenses when deploying.

Schema migration **4** adds only `reporting_profiles` and `reporting_snapshots` to the existing private portal database. Stop the backend and take an online SQLite backup plus a config backup before deployment; preserve the existing pilot expiry, invites and write-review state. Source permissions/OAuth scopes are unchanged. Read-only reporting does not require native write operations.

For rollback, stop the backend, retain the current database as a recovery copy, and restore the matched pre-migration database/config and previous code. A schema-3 backend should not be pointed at a schema-4 state file. Restoring the old database loses later portal-side records since that backup; retain the recovery copy for reconciliation. It does not undo native source changes made by other workflows.

Production remains a separate IT deployment decision. This feature does not enable Microsoft requester intake, AI providers, notification delivery, SCOUT, Dropbox, tenant-wide sharing or a public report endpoint.

Recoverable deletion is governed by [the current authorization policy](agent-authorization-audit.md). Deleted jobs are excluded from reports; delete/restore changes invalidate previous snapshots even when the native sheet version is unchanged. Admin copied-job access supersedes the earlier universal read-only-copy rule. Private state is now migration 5; retain a matched backup and use compatible code on rollback.
