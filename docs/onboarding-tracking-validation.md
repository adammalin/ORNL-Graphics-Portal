# Onboarding and requester tracking validation

November 17, 2026. These are separate capabilities: staff tutorials can run with Smartsheet OAuth alone; requester tracking depends on the still-disabled Microsoft integration.

## Automated qualification

The complete suite passes: **8 JavaScript + 110 Python tests = 118 tests**. GitHub validation run [44181939793](https://github.com/adammalin/ORNL-Graphics-Portal/actions/runs/44181939793) passed for the implementation commit; deployment was skipped. JavaScript syntax, public configuration, ORNL style/credential scans and diff whitespace checks pass. Tests cover first-show concurrency and persistence; per-identity preferences; origin/CSRF/size/role validation; immutable original-request snapshots; permanent row binding; same-email/different-object ownership denial; source revocation; copied-row exclusion; paused-write tracking reads; file content changes; staff grants/revocation and unchanged native-write counts.

## Isolated browser qualification

A private loopback fixture used fictional Microsoft/Smartsheet actors, jobs and files only. The fixture was stopped after qualification and was never tunneled. First-login tutorials opened for a coordinator, separate designer and requester. Designer and Coordinator lessons, role selection, chapter navigation, acceptance/refusal, details, references, edits, stages/archive, AI example, sharing example and workload practice were exercised. Exit/reload did not replay the tutorial; Help replay and saved-chapter resume worked. Escape returned focus to Help. Requester practice and its first-show preference remained separate from staff preferences.

The actual requester pages showed only owned requests, current status, accepted designer, original notes, requested/confirmed dates and permitted files. Internal notes/files were absent. Staff explicitly shared a fictional internal file; the requester saw it. Staff stopped sharing it; it disappeared. Fixture native-write count stayed **zero** throughout these tutorial/tracking/sharing checks. This is simulated integration qualification, not a real Microsoft tenant login or independent human acceptance test.

Desktop and 390-pixel layouts were visually inspected. Two defects found in browser QA were corrected: requester tutorial JSON serialization and a narrow-screen navigation/header overlap. The final role picker places Start/Skip above its chapter preview. Original reference URLs use escaped, credential-free HTTP(S) links.

## Live pilot rollout

The existing private configuration and SQLite database were backed up using SQLite online backup before restart. Migration 3 added four tables and its migration record. All pre-existing business-table counts were preserved. The configuration was byte-identical afterward: Microsoft intake remains disabled, eight copied projects remain selected read-only, and source/AI selection and expiry are unchanged. The existing launcher retrieved the Smartsheet secret from macOS Keychain automatically. The original tunnel was preserved.

Live staff sign-in and tutorial smoke verification are pending the owner's Smartsheet consent after restart. No native source write, notification, SCOUT, Dropbox, calendar or model operation was performed during this rollout. Microsoft tracking remains unavailable in this running pilot until IT registration, approved integration access and real two-requester ownership/eligibility tests are completed.

The public static demo remains fictional. Private source selections, identities, credentials, screenshots and fixture scripts are ignored by Git. This release does not certify staff training, qualify a second designer's own account, enable native Smartsheet AI or advance the separate API/MCP deployment stage.
