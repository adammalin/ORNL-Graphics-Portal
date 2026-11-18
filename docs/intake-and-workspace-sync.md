# Searchable intake, offers and workspace sync

November 18, 2026. This is an update to the existing laptop DEV portal. It does not activate Microsoft intake, change a source sheet, enable native workflows, alter native dashboards, or publish actual project data to the public demo.

## Intake choices

Type of work opens a dropdown with a search input above the options. Its categories come from the existing native Task Type options. Native multiple-choice columns use checkboxes, preserving selected values while searching another term, without requiring Ctrl/Command. Form submissions retain the same native select names and array/string format; server validation remains authoritative.

Group / department uses the same search pattern and allows an explicit Use action for a new typed value. Suggestions come from explicit matching native department picklist columns and, for staff, department values in jobs that their account can already see. The latter includes the exact department label serialized by this portal into Additional Details. No organization names are invented or inferred from request prose. Microsoft requesters retain their verified prefilled department and receive configured picklist options, not a list extracted from other employees’ request text. New values remain supported and are preserved with the original request details; no native column is added.

Dropdowns support labels, required-selection error focus, keyboard Escape, Down Arrow, search Enter, selection clearing for the optional department, outside-click dismissal, escaped source text and narrow-screen layout rules. Search inputs have no form field names. Native selects supply the existing payload without duplicate search/checkbox values.

## Offers and My Work

Overview starts with a prominent offers section, showing the signed-in person’s pending offers, count, job title, work type, requester, requested date and Review & respond links. Users still inspect and accept their own offers on the job page. Selecting another tutorial or preview role cannot grant authority.

My Work clears a carried-over source filter when entering that workspace, so a previous Copied projects filter does not hide accepted test jobs. A native recorded Yes response with a requested designer is recognized while the Assigned Designer formula is still calculating. A stage label alone does not manufacture acceptance. Existing assigned contacts remain supported for historical copied records. No assignment formula or cell is changed to implement this display fix.

## Sync behavior

Successful saves use the returned, confirmed workspace immediately. A save invalidates any older background response before it can repaint the UI. Other tabs receive an origin-local BroadcastChannel change hint; no project details, identities or credentials are broadcast.

While a staff tab is active, it checks approximately every fifteen seconds and when returning focus, reconnecting or navigating to a workspace. Unchanged data uses the official [Get sheet version](https://developers.smartsheet.com/api/smartsheet/openapi/sheets/get-sheetversion) endpoint, not a full sheet download. A changed version triggers a fresh scoped workspace read. Even when the version is unchanged, a full source refresh occurs at least once per sixty seconds of active polling, since not every authorization/filter change is represented by content version.

Version polling is only a change hint. It returns no new job contents unless the normal fresh source/filter/identity projection runs. Every write still performs a fresh source read and checks native access, job policy, source revision, schema/formulas, live automation state, workflow review expiry and the write switch. A full preflight result can be reused only inside that same locked service operation; it is never reused from a prior browser request. There is no shared-token fallback.

Sync has one request in flight per tab. Responses started before a save are ignored. Automatic repaint pauses for intake, dialogs, tutorial/dropdown interaction and unsaved reference/stage/offer/AI input, preserving typed work. Transient failures show Sync needs attention; authorization/source failures clear the stale workspace and require reconnection. The UI displays checking/saving/synced status. This is periodic synchronization, not real-time push or a scheduled unattended automation.

## Fewer upstream requests

The workspace response includes capabilities from its existing fresh authorization context. Initial rendering no longer waits for a separate capabilities read or optional AI import. Creation reuses its own confirmed permanent-row readback rather than loading the sheet a second time. It never shows a successful save based only on an optimistic browser update.

A repeatable fictional transport benchmark, with the same selected-copy setup before and after, measured:

| Operation | Before upstream GETs | After upstream GETs |
| --- | ---: | ---: |
| Initial workspace and capabilities | 6 | 3 |
| Create one request, including validation and readback | 13 | 7 |
| Poll unchanged workspace | Full reload required for updates | 1 lightweight version GET |

Both intake cases made exactly one native creation write. These are request-count measurements, not a measured wall-clock speedup or a Smartsheet latency guarantee. Native reads/network time and file uploads can still take time. Existing safety checks were retained.

## Validation and rollout

128 tests pass: 12 JavaScript and 116 Python. [GitHub validation](https://github.com/adammalin/ORNL-Graphics-Portal/actions/runs/44320601772) passed for the implementation commit; public deployment was skipped. New coverage includes stale response suppression across saves, pausing when editing begins during a pending read, unchanged/changed version behavior, periodic full validation, revocation and malformed-version failure, fresh preflight and confirmed creation readback counts, department extraction, exact recorded acceptance while a formula is delayed, and no assignment based solely on a stage label. Existing cross-user, copied-row, idempotency, uncertain-save, CSRF, source-revision and workflow tests also pass.

An isolated loopback browser fixture used fictional accounts, rows and departments. It verified filtering and retaining two work types, choosing an existing department, explicitly adding a new one, saving/readback of both fields, required-category error focus, the prominent offers section and acceptance propagating to a second My Work tab without a reload. The fixture was stopped; its script and screenshots remain ignored by Git. No real request was created or modified in those tests.

The owner’s reported synthetic job was confirmed Accepted and visible in My Work on a fresh live session before rollout. Private config and SQLite online backups were retained, the owned DEV backend was restarted with its existing Keychain credential, and the tunnel/expiry/config were preserved. After owner consent, live readback verified the prominent own-offer section and its correct review target, the accepted synthetic job in My Work, source-filter reset when entering My Work, searching/selecting two native work types, an existing department suggestion and an explicit new department value. Those form values were not submitted; no live job was created, accepted, edited or otherwise changed by this check. An active-tab sync timestamp advanced automatically without a manual refresh, confirming a successful background cycle. The browser was left on Overview. Microsoft customer intake remains disabled pending its existing IT requirements. The dedicated route is `/request`; the current Smartsheet-authenticated staff DEV form is `/#/new`.
