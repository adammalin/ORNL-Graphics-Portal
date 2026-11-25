# Browser WebMCP page tools

The authenticated staff page registers five tools from `web/assets/intake/page-tools.js`: status, bounded search, selected-job read/edit and request creation. They reuse the existing same-origin browser API closure, session, CSRF, idempotency, revision, native source and role/workflow validation. Cookies, CSRF, access tokens and signed attachment URLs are not returned. No new server grant or permission is implied. Tool calls share the human session; Pause page tools gates calls, pagehide disposes registration and sign-out/session loss stops native access.

Feature detection prefers `document.modelContext` (current WebMCP draft), falling back to the older `navigator.modelContext` when provided by the browser. No polyfill or custom global registry is installed. Unsupported browsers keep the regular UI. The Codex in-app browser bridge supports page-tool discovery; the current Brave extension bridge does not. Browser capability and page registration must both be tested.

Writes require an idle page and stable operation ID. Updates require the currently open project, edit permission and exact readback revision. Creation requires the New request route and native creation permission, with override/self-accept default false. Native role/calendar/source/schema checks remain authoritative. No tool supports deletion, stage changes, offers, notifications or arbitrary network destinations. Attachment uploads use existing UI. Content returned from projects is untrusted evidence.

The unused stdio companion, loopback bootstrap/agent routes, Agent connections page, companion-only guards, SDK dependency and localMcp config were removed on 2026-11-25. Historical source/test receipts are retained privately for rollback; this did not remove other apps' MCP connections. Existing client/charge fixes are preserved. No data migration or SCOUT mutation accompanies retirement.

Specification: https://webmachinelearning.github.io/webmcp/ . It is a draft, so host compatibility is recorded separately from automated tests. See the private qualification receipt for actual live coverage.
