# Copied-project preview validation

November 17, 2026. This feature reads a selected sample from the existing DEV copy; it does not activate a production source or edit native Smartsheet assets.

## Automated and isolated browser checks

The full suite passes: **6 JavaScript + 96 Python tests = 102 tests**. Syntax, public configuration, brand/credential scans and diff whitespace checks pass.

The copied-project regressions cover read-only coordinator access, designer visibility, denied edit/stage/offer/response/upload operations, default-off and bounded row selection, removal/revocation, hidden source-designer names outside a user's permitted records, display-only historical designers, same-job-number ambiguity, changed source snapshots, selected attachment reads and AI denial even with a misconfigured AI allowlist. A configured copy remains protected if its DEV checkbox is checked or an in-memory writer set is accidentally enlarged.

An isolated loopback browser fixture used only fictional rows and credentials. Verified the source filter limits the board to the selected copied record, the card has no draggable attribute, copied details contain no edit/upload/AI controls, and a test job retains its edit control. The test-only sign-in bootstrap was confined to an ignored local script; that fixture was stopped afterward.

## Live DEV preparation

Eight copied rows were selected by reading permanent IDs from native Smartsheet Row Properties. The native sheet view was restored to its original DEV filter. No native row, filter definition, formula, workflow, dashboard, form or sharing definition was edited. Private config and an online SQLite backup were retained before adding the read-only selection.

The owner saved the App secret in macOS Keychain and restarted the pilot successfully. The first live copied-project board/detail verification is pending the user's Smartsheet consent and source readback. No live copied-project write is attempted as a test; actual mutation denial is covered by automated transports, while live qualification checks the read-only UI and source content.

The AI allowlist remains confined to its existing synthetic jobs. Notifications, SCOUT, Dropbox, unattended actions and native AI remain disabled. The public Pages demo contains fictional content only; actual selections, copied source content, screenshots and credentials remain outside Git.
