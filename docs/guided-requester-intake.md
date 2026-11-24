# Guided employee request and My Requests integration

Opt-in integration in the existing portal application, not a second intake system. Existing Microsoft tenant/member/app-role checks, requester receipt ownership, CSRF, integration account, native schema guards and staff Smartsheet permissions remain in force. No real Microsoft registration, pilot configuration, tenant permission, native automation or mail workflow is enabled by this change.

## Try the integrated workflow locally

Run with the already installed pilot Python environment:

```sh
python scripts/qualify-guided-intake.py --synthetic
```

Open **http://localhost:18771/qa**. The simulator role links open:

- `/qa/requester` → `/request`: guided employee request using an injected fictional Microsoft identity.
- `/qa/staff` → `/#/projects`: coordinator workspace using the existing application and fictional Smartsheet transport.
- `/qa/designer` → `/#/my-work`: separate fictional designer session; open the offered job and accept it.
- `/qa/my-requests` → `/my-requests`: the original requester's owned requests and current status.
- `/qa/other-requester`: another immutable identity, deliberately sharing the sample email; it cannot see the first employee's requests.

Use a fictional request and test files. Submit, review it as coordinator, offer Test Designer, accept as designer, move it through stages, then refresh My Requests. Sample holidays/closures are November 26/27, 2026. They are **not an approved ORNL schedule**. The launcher uses only existing test fixtures and a private temporary SQLite database. No Microsoft, Smartsheet or email service is called. Stopping the launcher clears that test state. Never tunnel this simulator or deploy it as the pilot.

## Real pilot activation

The stable route paths remain `/request` and `/my-requests` under the configured HTTPS pilot origin. Local inspection on November 24 found `microsoftIntake.enabled` false. The new feature does not turn it on. The Microsoft registration, approved integration identity, real two-user access tests and existing workflow review are still required; see `microsoft-requester-intake.md`.

After those prerequisites, the owner can opt into the guided form with a private configuration entry like this:

```json
{
  "guidedIntake": {
    "enabled": true,
    "calendar": {
      "approved": true,
      "label": "Owner-verified ORNL holidays and closures",
      "validThrough": "2027-09-30",
      "closedDates": ["REPLACE WITH VERIFIED YYYY-MM-DD DATES"]
    }
  }
}
```

This is a shape example, not a ready-to-activate calendar. The placeholder is intentionally invalid. `approved` is an owner attestation, not an approval performed by the application. Missing, unapproved, invalid or expired calendar coverage pauses guided submissions. A validThrough date must cover both the current minimum and the selected delivery. Do not use sample calendar dates for real requests.

When the feature is absent or disabled, the earlier form stays available with its prior behavior. The staff-created job form is unchanged. No request date is changed retroactively. The current form is for Graphics requests with supporting services; it does not introduce a standalone non-Graphics service intake.

## Rules and saved data

- Five steps: Purpose → Services → Details → Timing → Review. Verified contact details, native searchable task types and organization choices are retained.
- Two business days, starting tomorrow in America/New_York, excluding weekends and configured closures. Requested delivery must itself be open and within reviewed coverage. The optional event date can be a weekend. No afternoon cutoff is assumed.
- Browser calendar and backend independently reject invalid dates. Backend validation happens before a new operation is reserved or a row is written. Replays retain the original operation key and payload fingerprint; a later date does not create duplicates or allow the key to create a changed request.
- Supporting services are Photography, Video Production, Web, Reproduction and Poster printing. Printing and posters combine into one Reproduction group. Uncertain services go to Graphics coordination. Disabling additional support excludes its retained draft values from the submitted payload.
- Service choices, quantities and event date are stored in the immutable requester snapshot and serialized into the existing native Additional Details cell for staff. No new native columns, formulas or workflows are required. The existing combined 4,000-character native detail limit still applies; service notes are limited to 500 characters each.
- Routing is explicitly a preview, not email delivery or service-team acceptance. Real recipient lists and notification processing remain a separate reviewed integration.
- Existing attachment limits and per-file retry keys remain: ten PNG/JPEG/WebP/PDF/plain-text files, up to 30 MB each. A failed upload retries the existing saved request rather than creating another.
- My Requests uses the existing permanent-row and verified-owner binding. Additional services are projected from the original snapshot, never from later internal staff notes. Confirmed dates and accepted designer remain separate from requested dates and pending offers. Current stage loads on open or Refresh status.

## Verification and rollback

The inherited portal baseline is commit `0302324d1a841fb68afedd02a6ddb5ad20071178`. The feature is isolated on `codex/guided-requester-intake`; disabling guidedIntake restores the earlier form, with prior request snapshots still readable. There are no destructive state migrations. Before any actual pilot rollout, retain its current code/config/SQLite backup and follow the controlled restart procedure.

Automated qualification: 215 Python tests and 25 JavaScript tests passed, including the new guided date/service rules and a complete synthetic request → coordinator offer → designer acceptance → progress/review/completion → owner-only tracking flow. Existing negative ownership, staff/requester isolation, attachment and visibility tests remain included. Syntax and repository brand/secret checks passed.

Browser qualification used the actual portal pages and synthetic transport: completed all five steps; rejected insufficient notice; saved 40 handouts and 2 posters with one Reproduction routing group; observed the new request in staff All projects; offered and accepted as a different staff identity; updated In Progress and Completed; refreshed the employee tracker and saw both changes. No real tenant sign-in, Smartsheet write, service email or production holiday validation was claimed. Screenshots are retained locally under `artifacts/guided-intake/`.
