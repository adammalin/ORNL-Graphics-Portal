# Non-active intake comparison demos

The existing tunneled pilot has two **staff-authenticated, browser-only** comparison pages:

- `/intake-demos/classic#/new` reuses the original client request form renderer from employee intake, with forced demo configuration and a fictional client. It has no staff sidebar, role selector, project board or assignment controls.
- `/intake-demos/guided` reuses the five-step guided renderer, including conditional supporting services, printing quantities, a two-business-day minimum and a clearly labeled sample closure calendar.

Both pages require the existing invited staff Smartsheet session. There is no Microsoft requester identity impersonation, shared-token fallback or expanded invite list. The configuration contains fictional requester information and no session/CSRF tokens. The demo calendar is separate from operational configuration; its sample November 26/27 closures are not approval of an ORNL holiday schedule.

The demo documents enforce `connect-src 'none'` and `form-action 'none'`. The guided demo has no API/upload adapter. Classic uses the same customer form markup as employee intake with a separate browser-only completion handler. The live staff workspace continues to load its original application entry. Completing either form only renders a result in the tab; no Smartsheet row, attachment, email, notification, ownership receipt or My Requests record is created. Selected file names can appear in the local preview, but files are not uploaded. Refresh resets entries.

A comparison link appears in the signed-in workspace; each demo links to the other and back to the workspace. The existing active staff intake at `/#/new` is retained with its original save behavior. Neither Microsoft employee intake nor the approved-calendar gate is enabled by hosting these demos.

Qualification: 226 Python tests and 27 JavaScript tests passed. Added checks cover anonymous denial, both pages for read-only staff, forced demo configuration, blocked submission methods, no network/upload adapter and unchanged active pilot/Microsoft configuration. Browser checks completed both local demonstrations and rejected insufficient notice in Guided.

Deployment uses the same authenticated tunnel, source scope, private config and SQLite database. A backend restart loads the routes and clears memory-only sessions: staff may need to reconnect with Smartsheet. Before switching code, retain the current source commit, private config and online SQLite backup. Rollback is a controlled restart on that retained commit, leaving the persistent state intact; do not restore the database over later legitimate work.
