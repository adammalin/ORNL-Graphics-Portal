# Prototype validation

November 17, 2026. These checks qualify a synthetic public demonstration and an isolated local read-only connection. They do not qualify production identity, live submission or multi-user authorization.

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

ORNL SSO and employee eligibility, actual requester/designer/coordinator authorization, live intake and uploads, Smartsheet writes and concurrent-edit handling, cross-device persistence of demo changes, real calendar availability, automated routing, AI, email notifications, SCOUT and Dropbox integration. A non-Graphics employee and separate real designer login still need an authenticated production-path test.

The local gateway is a loopback development tool, not the production backend. The existing native dashboards, forms, formulas, reports and workflows are outside the write scope of this prototype.
