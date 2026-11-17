# Scope and preservation

November 17, 2026. This repository is a separate custom-portal pitch. The user explicitly required preserving the current native Smartsheet dashboards and flows, and subsequently authorized connecting to the DEV sheet.

- Existing native assets are not modified, migrated or replaced.
- No copies of native source snapshots, credentials or private evidence are placed in this public repository.
- Initial live access is GET-only, restricted to one server-configured DEV sheet and explicit synthetic row IDs. Non-DEV and unlisted rows are excluded even if returned by the upstream API.
- The local gateway cannot send POST, PUT, PATCH or DELETE requests to Smartsheet. Incoming write requests return 405.
- Live intake and editing are disabled in connected mode. They must first be tested against a separate writable sandbox or explicitly approved isolated fields and events.
- Never delete email; future cleanup is archive-only.
- Dropbox stays create-only: no delete, overwrite, move or rename, including for agent-created items. This prototype does not connect to Dropbox.
- No email, AI, SCOUT, Dropbox, notifications, schedules, sharing changes or copied workflow activation are introduced here.
- Public Pages is an interactive synthetic demo. It is not an ORNL-authenticated service and is not a place to submit real requests.

Before any future write adapter, agree on source ownership, field mapping, acceptance evidence, duplicate prevention, audit history, a rollback procedure that does not delete files, and tests proving existing native formulas and workflows stay intact.
