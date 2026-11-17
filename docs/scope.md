# Scope and preservation

November 17, 2026. This repository is a separate custom-portal pitch. The user explicitly required preserving the current native Smartsheet dashboards and flows, and subsequently authorized connecting to the DEV sheet.

- Native dashboards, forms, formulas, reports, selectors, sharing and workflow definitions are not modified, migrated or replaced.
- The user authorized DEV editing and chose a local DEV server. Only existing synthetic DEV rows and newly created DEV requests can be written.
- No native source snapshots, credentials or private evidence are placed in this public repository. The Pages artifact includes only `web/` and remains a fictional demo.
- Read-only mode remains GET-only. The opt-in DEV editor permits bounded row creation, updates to whitelisted fields, offer/response actions, stage changes and new attachments. The backend has no arbitrary endpoint, row movement, schema editing or sharing path.
- The native DEV-only filter is verified before use and each row's DEV marker is checked independently. Explicit row-ID allowlists remain supported for narrower pilots.
- No row or attachment deletion, file replacement or version upload is exposed. Completed/archived records and all existing reference files are retained.
- Existing formulas and system fields stay under Smartsheet control. Assigned Designer is never manually set; the native formula derives it from the requested designer and explicit response.
- New requests preserve extra intake details as labeled sections in Additional Details. Requested and final due dates are separate. Edits send only changed, permitted cells.
- Each write requires unchanged schema/workflow definitions and no enabled DEV automations. The service stops saves instead of changing any workflow configuration.
- Submission keys, row revision checks, explicit save feedback and direct source readback protect the DEV test path. Unknown upstream outcomes are not automatically retried. Correct a test field by writing its previous value back; retain the request/files.
- Email remains archive-only with no deletion. Dropbox remains create-only with no delete, overwrite, move or rename. Neither connector is invoked by this portal.
- No AI, email, SCOUT, Dropbox, calendar, scheduled notification or copied workflow activation is introduced.
- Local test views are not employee identity or authorization. This service binds to loopback and cannot be deployed for team access without the production identity work described in architecture.md.
