# Stage 0 — shared job service foundation

November 17, 2026. Implementation stage only; the next browser-agent stage is not enabled.

## Changes

- Extracted job reads, projections, visibility, action authorization, intake identity, writes, upload and attachment access into backend/job_service.py.
- The existing browser endpoints call that shared service. CSRF remains in the browser adapter and is not included in service responses.
- Added an immutable Principal snapshot from an actively validated private session. The service accepts an opaque issued session handle, not an actor/role supplied by a caller.
- Rechecks session, current role, source permissions and DEV-write conditions immediately before native mutation, including after native preflight reads. A pilot store cannot mutate through the normal writer outside the authenticated service.
- Retained the existing per-user idempotency-key namespace, receipt storage, assignment formula and source/write validators.
- Added versioned, transactional private SQLite migrations for empty future context/draft/review tables. Existing identity bindings and operation receipts are retained. Unknown versions stop startup; a failed migration rolls back.
- Added authenticated GET /api/v1/capabilities and its [versioned response contract](contracts/portal-capabilities.schema.json). All nine new AI/agent feature flags are false. Browser authentication is still required; no bearer-authentication or MCP endpoint is introduced.

## Verification

- Full suite: 5 JavaScript tests and 39 Python tests passed, including 14 new service-boundary and private-migration tests.
- Direct-service and browser responses agree, and direct service results contain no browser CSRF credential.
- The versioned capability JSON Schema was validated against actual coordinator, designer and viewer responses from the synthetic integration fixture.
- Successful direct service edits appear through the browser adapter; browser edits appear through the direct service. Duplicate saves preserve one native mutation.
- An unissued handle or a forged Principal is rejected. Other-designer job reads, writes, uploads and downloads are denied outside Flask as well as inside HTTP routes.
- Logout, role changes, expiry/demotion during file retrieval, and logout/demotion/workflow expiry during native preflight stop the corresponding protected operation.
- Private migration tests preserve legacy data and verify idempotency, file permissions, unknown-version rejection and atomic rollback on migration failure.
- Existing OAuth, alias handling, offered-designer acceptance, viewer restrictions, field protection, stale edits, no-delete, add-only attachment and native DEV-filter tests remain passing.
- Public demo configuration, brand and secret checks and git diff whitespace checks passed.

All data in these checks is synthetic. These tests do not repeat live Smartsheet OAuth, qualify a second real tester, prove atomicity against a concurrent native editor, or activate draft generation.

## Deployment and rollback

The running laptop pilot has not been restarted, and no live private database migration or Smartsheet operation was performed for this stage. Its existing process continues using the prior loaded code.

The new private migration runs on the next startup of this implementation. Before deploying, retain the private state/receipts and use the normal launcher with its hidden app-secret prompt. Repeat the authenticated smoke test after restarting; no new Smartsheet permission is required by this code change.

For rollback, restore the previous application release and retain the private database. The migration only adds new tables; it does not rewrite the previous release's identity/receipt tables. Do not discard or recreate the database to roll back a code change.

Stage 1 remains the context panel, externally generated draft import, evidence/coverage validation and review UI. No Smartsheet AI or central model key is needed for that user-agent path.
