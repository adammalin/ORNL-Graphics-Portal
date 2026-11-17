# macOS demo launcher validation

November 17, 2026. This change stores only the app-level Smartsheet OAuth secret in the local macOS Keychain. It does not persist user access/refresh tokens, change session lifetimes, expand access, extend pilot/tunnel expiry or restart the existing demo process.

- The native Security framework bridge passed create/read/update checks against an isolated temporary keychain containing only synthetic values. The test keychain was removed afterward; real app credentials were not accessed.
- Tests cover configured and first-entry client IDs, private atomic config persistence, Keychain retrieval without echo, explicit first-save behavior, access-denial fail-closed behavior, no plaintext fallback, unavailable hidden input, automatic macOS startup with a mocked saved secret and stopping before credential access when the port is occupied.
- The complete project suite passes: 5 JavaScript and 86 Python tests (91 total). Syntax, public configuration/brand checks, launcher shell syntax and diff whitespace checks pass.
- The four-page private PDF was regenerated from the laptop's non-secret configuration settings, reopened for text/link checks, rendered and visually reviewed on all four pages. It includes the live link and app client ID, but no App secret. PDF output and render intermediates are excluded from Git.
- During the later copied-project preview qualification, the owner completed the one-time hidden App-secret entry, reported successful Keychain storage and startup, and the restarted portal completed real Smartsheet authorization and DEV reads. A further cold restart using an already-existing saved item has not been separately exercised live; the isolated native round trip and mocked saved-item startup tests cover that path. The original launcher work did not read the owner's secret or interrupt its then-running demo.

The bridge uses macOS Security framework generic-password APIs for this local laptop utility. No secret is passed through a shell command, child-process argument, environment variable, frontend file or log. Keychain can request local unlock/access approval. There is no fallback to saving plaintext.
