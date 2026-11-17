# Design and content inventory

November 17, 2026. Balanced ORNL expression, matching the Team App Library source and the supplied Team Apps reference. Green-led hero, Hale Navy type and structure, restrained Energy actions, generous white space and square modular components. No scientific imagery or texture is needed for this task-oriented interface.

- Primary source: the existing Team App Library header, typography, gradient, content cards and action patterns.
- Brand authority consulted: May 2026 Branding Toolkit core elements; packaged full palette / accessibility reference and ORNL brand-system operating guidance.
- CSS tokens copied from the ORNL brand skill. Tints are explicit CSS color-mixes derived from those tokens, as used by Team Apps; no undocumented near-match colors are introduced.
- Font: self-hosted Mulish Latin variable font reused from the Team Apps build, with its SIL Open Font License; Aptos / Arial fallbacks from the packaged token stack.
- Icons: consistent regular-stroke functional outline icons and a square application grid symbol. The grid is an application icon, not an ORNL logo or leaf.
- Logo state: OMIT. No approved production logo file was supplied.
- Geometry: zero radius for panels, cards, buttons, fields and labels; circular person indicators only.
- Accent meaning: Energy for primary demo entry/offer attention, Forge for pending/highlight notices, Pulsar for future AI and review states. Accents are subordinate to green and neutral fields.

## Closed content inventory

Allowed text: ORNL Graphics Portal product name; functional request/project/designer/workload/reference labels; supplied workflow concepts; clear prototype, synthetic-data and unconnected-feature qualifications; the fictional demo records explicitly listed in `web/demo-data.js`; form labels and validation messages for those same concepts.

Allowed visuals: structural grids, lines, buttons, functional icons, computed counts/charts from the current dataset, and the bundled synthetic reference wireframe. No fabricated research findings, facilities, staff identities or official adoption/performance claims.

Must preserve: the native Smartsheet system, original request information, explicit acceptance requirement, retained completed/archived records, create-only Dropbox policy, archive-only mail policy, and the distinction between demo, local read-only connection and future live service.

Forbidden: production branding approval claims, invented ORNL legal text/slogans, private sheet contents/IDs in the public bundle, API credentials, fake sign-in or live submission confirmations, implied running AI/email/SCOUT/Dropbox integrations.

`npm run check` audits every literal web color against the packaged tokens, checks container radii and verifies demo-only public configuration. Browser QA covers desktop/mobile, request→job details, independent URL navigation, designer acceptance, lifecycle, references and workload. Formal ORNL review and production accessibility certification are not claimed.
