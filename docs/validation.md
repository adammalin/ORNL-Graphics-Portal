# Prototype validation

November 17, 2026. These checks qualify a synthetic public demonstration and isolated local DEV connections. The later section covers opt-in DEV saves. They do not qualify production identity or multi-user authorization.

## Automated checks

- `npm run check`: JavaScript syntax, approved literal ORNL colors, square container radii, font license, credential patterns and demo-only public configuration passed.
- `npm test`: five JavaScript tests and four Python tests passed. Covered explicit acceptance, per-designer active filtering, exclusion of closed jobs from estimates/metrics, guarded stage changes, completion-date retention, escaping/URL validation, required intake fields, exact DEV source/row boundaries, attachment inventory, local session/Host/Origin restrictions and rejection of write methods.
- GitHub Pages uploads only the `web/` directory. Neither local evidence nor gateway code/configuration is part of the Pages artifact. Backend source is public but contains no credentials or configured private source IDs.

## Supervised browser checks

1. Desktop overview rendered with the Team App Library visual system, self-hosted Mulish and ORNL tokens.
2. A pending offer stayed unassigned, then acceptance assigned Alex Rivera and increased My Work from two to three projects.
3. A synthetic reference displayed inside the job's preview dialog. The downloaded SVG matched its bundled original by SHA-256.
4. Employee / requester preview opened the intake form without a Graphics role. Empty required fields produced specific validation errors. A fictional request with notes, deliverables and a reference URL created DEMO-1049 in browser memory and opened its own detail URL.
5. Original special-character notes displayed as text, preserving angle brackets, ampersands and quotation marks.
6. Opening a second job in another tab did not change the first tab's title or job URL. This verifies selection independence, not authenticated multi-user access.
7. Coordinator offered DEMO-1049 to Morgan Lee. Morgan accepted; the local job progressed In Progress → In Review → Completed → Archived, retained its details and left My Work.
8. Native drag/drop moved a demo card to another lane. The stage control provides a keyboard-accessible alternative.
9. Demo editing changed a job title and estimate; the workload view reflected the new estimate while excluding completed/archived work.
10. A 390 × 844 responsive check found an intrinsic-grid overflow. Fixed it, reloaded and confirmed the document no longer exceeded the viewport on the board and intake form. Mobile inputs use 16 px text. Temporary viewport override was reset.

Demo state is intentionally ephemeral. Reload resets examples; no browser check above created a Smartsheet row or sent a message.

## Live DEV read-only check

- Authorized two previously verified synthetic DEV rows through an explicit server-side row allowlist; the DEV marker was also required.
- The portal read matching native job details without using or changing the native dashboard selection log.
- The synthetic DEV PNG loaded inside the custom job preview at its original 800 × 450 resolution.
- PNG and text downloads through the gateway both matched the existing synthetic originals by SHA-256.
- POST, PUT, PATCH and DELETE requests to the gateway returned 405.
- A final read confirmed the source sheet version matched the gateway's initial read. All recorded upstream requests were GET.
- Credentials remained in process memory; no token, raw sheet payload, source identifier or live screenshot was added to the public repository. Local evidence is excluded under `artifacts/`.

## Still unqualified / not implemented

ORNL SSO and employee eligibility, actual requester/designer/coordinator authorization, hosted production intake/uploads/writes, atomic concurrent-edit handling, cross-device persistence of synthetic demo changes, real calendar availability, automated routing, AI, email notifications, SCOUT and Dropbox integration. A non-Graphics employee and separate real designer login still need an authenticated production-path test.

The local gateway is a loopback development tool, not the production backend. The existing native dashboards, forms, formulas, reports and workflows are outside the write scope of this prototype.

## Local DEV write qualification

November 17, 2026. The user authorized DEV saves and selected a local server. This is separate from production identity and public Pages.

- `npm test`: 5 JavaScript tests and 13 Python tests passed. Added coverage for bounded field updates, stale revisions, protected formulas, exact task-category object values, native DEV-filter discovery, acceptance and decline, completion retention, persistent creation keys, uncertain outcomes, add-only attachments and HTTP session/Origin/CSRF checks. DELETE and arbitrary PUT endpoints remain disabled.
- `npm run check`, Python compilation, launcher syntax and `git diff --check` passed.
- Created one synthetic request through the connected browser form. Smartsheet generated its job number. Intake preserved two task categories, original request details, notes with special characters, audience, specifications, group, requested date, reference URL and a file on the same row.
- Edited the title, six-hour estimate, priority, final date and details. Reload and independent direct Smartsheet GET confirmed the saved values, including distinct requested and final dates and both task categories.
- Recorded a designer offer, declined it, re-offered and accepted. The native assignment formula supplied the designer, and the job entered My Work only after acceptance. No direct Assigned Designer write occurred.
- Added a second reference through the job page. The source retained both files. A stored PNG preview loaded at 800 × 450. A browser download matched the original by SHA-256. Download links were corrected to use the current tab's download event.
- Saved In Progress → In Review → Completed → Archived. The record and its files remained, active assignment counts excluded it, and the first completion date was saved.
- Stopped and restarted the gateway with the same private registry; the saved job and files remained available. The verified native DEV-only filter discovered the source's marked synthetic jobs, while copied non-test rows stayed outside the API projection.
- A separate, credentialed Smartsheet GET confirmed the new row's actual saved values and generated native job link. Comparing with the pre-write snapshot showed unchanged source columns, unchanged preexisting test-row business values/formula definitions, and identical automation configuration. The gateway's own preservation endpoint agreed.

Private source receipts, source identifiers, snapshots, filenames/IDs and connected screenshots are kept under ignored `.local/` or `artifacts/`; none are deployed to Pages. The API token was entered at hidden prompts and was not saved.

The source's Task Type column required API level 2 and a MULTI_PICKLIST object, despite appearing as TEXT_NUMBER in the compatibility response. Initial invalid submissions were rejected by Smartsheet; the corrected browser submission was verified as exactly one new row.

Remaining qualification: real organizational sign-in and permissions, a shared hosted backend, real employee/designer sessions, exact simultaneous-edit behavior across independent writers, production uploads/intake, routing, calendar availability, AI, notifications, SCOUT and Dropbox. The local revision check cannot provide an atomic native-editor lock.

## Invited OAuth pilot qualification

November 17, 2026. Separate from the public fictional Pages demo and the local shared-token editor.

- CI passed 5 JavaScript tests and 25 Python tests, including 12 OAuth HTTP/authorization and launcher tests. Independent synthetic identities cover per-user tokens, role/row boundaries, spoofing, secure cookies and browser-bound one-use OAuth state, CSRF, expiry, invite removal, user-scoped retries, add-only references and blocked deletion. The launcher retries an empty secret without echoing it.
- Registered an unpublished OAuth app. The owner entered its secret at a hidden local prompt; no credential was committed or sent to the frontend. The actual browser completed Microsoft tunnel authentication, Smartsheet consent, current-user verification and DEV-source reads using the signed-in owner's OAuth token.
- The first write was rejected by the exact-origin check because Dev Tunnels rewrote Origin to localhost. Corrected the tunnel to preserve Host and Origin; the application check was retained. The corrected retry saved one synthetic intake job, including original request text, notes, intended audience, specifications, category, requested date, deliverables, a reference URL and uploaded reference file.
- Live browser editing saved an estimate. Offering the test job to the signed-in owner and accepting it populated the native assignment formula and added it to My Work. In Progress → Completed → Archived persisted through a full reload, retaining the completion date and reference links. The test record was retained.
- The uploaded text reference was listed and downloaded through the authenticated endpoint. SHA-256 matched the original synthetic file. Smartsheet's reported file type did not enable an inline text preview for this new file; this check qualifies download, not inline preview.
- Live anonymous HTTP checks returned 401 for projects, 405 for deletion and 404 for private configuration. The login page used no-store. Native UI review covered all 20 DEV workflows, including the disabled workflow labelled Unable to run; no workflow definitions were changed.
- Live sign-out returned the browser to the login page. The application audit recorded the session closing; the test job and references remained stored in the DEV sheet.
- After explicit user approval, the outer tunnel permits the configured Microsoft tenant to reach the login page for five days. The inner application still admits only the six private Smartsheet invites. No anonymous tunnel access or shared-token fallback was enabled.

Native Manage Access showed all six invitees already had editing access (owner, admin or editor with sharing). No sheet-sharing changes were made. This is a source-access check, not a completed login test for each person.

Still pending: a second real tester's independent login and API write access, exact concurrent edits with native/external writers, production hosting/employee intake and the integrations listed above. The laptop must remain running. App sessions, tunnel access and the daily native-workflow review expire independently; expiry is a real availability limit, not a production operations arrangement.

Screenshots, source job identifiers, invite emails, tunnel/configuration identifiers and private receipts stay under ignored local paths. The public Pages site remains demo-only.
