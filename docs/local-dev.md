# Local DEV editor

The local editor reads and saves to the configured **DEV Graphics Assignments** sheet. The public GitHub Pages site remains an independent fictional demo.

## Start on this Mac

Double-click `start-dev.command`, or run it from this checkout:

```sh
./start-dev.command
```

Enter the approved DEV API token at the hidden prompt. Open the printed `http://127.0.0.1:4174` URL. Keep that terminal open; Ctrl+C stops the local service. The token stays in memory and must be re-entered on restart. It is never stored in the browser, launcher, local configuration, Git or Pages.

This checkout has a private, ignored `.local/dev-config.json`. For another checkout, create it using the exact approved DEV source identifiers; never add the token:

```json
{
  "sheetId": "YOUR_APPROVED_DEV_SHEET_ID",
  "rowIds": [],
  "filterId": "EXISTING_DEV_DEMO_PROJECTS_FILTER_ID"
}
```

The existing filter must be named **DEV - Demo projects** and contain exactly one AND criterion: **DEV Test Record IS_CHECKED**, without parent inclusion. Its definition is read and verified, never changed. The API independently excludes rows without the DEV marker. Newly submitted native DEV requests and portal requests appear after **Refresh DEV data** or a page reload. A configured explicit `rowIds` list can be used instead of the filter for a narrower pilot.

Keep `.local/dev-state.sqlite3` when restarting: it records newly created row IDs and submission keys, without storing the API token. No new local state file or evidence belongs in the public repo.

## Use

1. Create a synthetic request with the intake form. The server adds `[DEV PORTAL]` to its title, marks it DEV and saves it in New. The native auto-number column supplies the job ID; native column formulas supply the native job link.
2. Add reference URLs and/or files. Intake uploads and later uploads are stored on that row. Raster images and text can preview in the portal; other allowed files download. No file deletion, replacement or version-upload operation exists.
3. In the **Graphics coordinator · Local test** view, offer the request to a designer. In that designer's local test view, accept or decline. These controls are test views, not real employee identities. The native Assigned Designer formula derives the assignment from Requested Designer + Designer Response.
4. Edit the job or move its card / stage control. Confirm the saved status. Refreshing reads the persisted Smartsheet values. Completed/archived jobs retain files and leave active counts; the first close sets Completed Date in America/New_York.
5. Use **Refresh DEV data** for changes made directly in Smartsheet. The backend checks the row's revision before an update. If another edit has arrived, refresh and review it before retrying.

No email, routing, calendar lookup, AI, SCOUT or Dropbox integration runs from these actions. The editor stops saves if any DEV automation is active or if the native schema/workflow definition has changed since startup. It does not disable or edit workflows.

## Field mapping and preservation

| Portal | Existing native destination |
| --- | --- |
| Job title | Description |
| Project details | Additional Details |
| Notes, audience, specifications, requestor group | Appended as labeled sections to Additional Details during intake |
| Task type(s) | Task Type, using MULTI_PICKLIST object values at API level 2 |
| Requested due date | Due Date |
| Final due date | Final Due Date |
| Estimate, priority, deliverables | Estimated Hours; Priority; Deliverables and Quantities |
| Requestor name and email | Requestor; Requestor Email |
| Reference URLs | Reference link 1; Reference link 2 |
| Offer / response | Requested Designer; Designer Response |
| Assigned designer | Read-only native column formula; never overwritten |
| Stage and first close date | Project Stage; Completed Date |
| Reference files | New attachments on the selected DEV row |

Existing notes and other intake information stay together in **Project details & notes**. Editing that section updates the existing Additional Details cell; no schema changes are introduced. A combined value over 4,000 characters is rejected before the save, avoiding silent truncation. Computed/system cells, locked rows/cells and existing cell hyperlinks cannot be overwritten through these edit operations.

Submission keys are saved before the create/upload request and reused for duplicate delivery. An uncertain upstream result is not automatically repeated. If a request was saved but a file failed, open that saved job and inspect its files before retrying that file; do not resubmit intake. A known rejected request can be started again with a fresh form.

The revision check serializes this local server's saves and rejects already-stale rows. It is not an atomic lock against someone editing in Smartsheet at the exact instant between the final GET and PUT. Only explicitly changed cells are sent.

## Scope

This is a loopback-only development service, not an externally reachable or authenticated team service. The role picker does not provide authorization. Production organizational identity and role checks must be implemented before shared hosting. GitHub Pages cannot run this Python backend.

No arbitrary Smartsheet endpoint, schema change, sharing operation, native selection-log update, row movement, row deletion or attachment deletion is exposed. Archive changes status and retains the record. For a test correction, save the previous value back into the same editable DEV field; retain test requests and files.

## API references

- [Complex column types and compatibility](https://developers.smartsheet.com/api/smartsheet/guides/advanced-topics/complex-column-types-and-compatibility)
- [Add rows](https://developers.smartsheet.com/api/smartsheet/openapi/rows/rows-addtosheet)
- [Update rows](https://developers.smartsheet.com/api/smartsheet/openapi/rows/update-rows)
- [Attach a file to a row](https://developers.smartsheet.com/api/smartsheet/openapi/attachments/row-attachments-attachfile)
