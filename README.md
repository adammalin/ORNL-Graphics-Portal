# ORNL Graphics Portal

A separate custom-portal proposal alongside the existing native Smartsheet dashboards. The visual system follows the Team App Library: Mulish, ORNL Green / Hale Navy, square components, a restrained Energy accent and clear project navigation. Design draft; not an approved production service. No ORNL logo is reproduced.

## Two deliberately separate modes

| Mode | Data | Changes |
| --- | --- | --- |
| Public GitHub Pages demo | Fictional projects and people bundled in `web/demo-data.js` | In this browser tab only; reset on reload |
| Local DEV connection | Explicitly allowlisted synthetic rows on the approved DEV sheet | Read-only. No Smartsheet write method exists in the gateway |

The GitHub Pages deployment uploads **only `web/`**. It does not deploy a backend, include API credentials or publish DEV-sheet contents. Neither mode edits existing native dashboards, forms, formulas, reports, attachments, sharing or automations.

## Try the prototype

- Employee intake: `#/new`. No Graphics membership is required to try the synthetic demo. Live employee submission still needs ORNL-approved authentication and a secure submission endpoint.
- Designer offers: preview Alex Rivera, open the sample seminar poster, and accept it. It then appears in My Work.
- Kanban / list: search, filter and drag your assigned cards, or use the job's keyboard-accessible stage selector.
- Job details: `#/projects/DEMO-1046`. Each job has its own URL, description, tasks/deliverables, metadata, reference files and links. No shared dashboard selection log is used.
- Reference previews and downloads: bundled synthetic layout and notes. Demo uploads are memory-only and disappear on reload.
- Team workload: accepted active assignments and pending offers are counted separately; completed/archived jobs are excluded. Sample planning thresholds are not actual availability.
- Completion / archiving: retain records. The demo stamps a completion date locally; it does not retrofit native sheet automation.

Demo role switching is a presentation tool, **not authentication or a security boundary**. All public examples are fictional. AI, email notifications, live submission, production writes, calendar access, SCOUT and Dropbox are not connected.

## Run locally

Requires Node.js 22+ for checks and Python 3.10+ for the local server. No npm installation is needed.

```sh
npm test
npm run check
npm run dev
```

Open the printed `http://127.0.0.1:4173` URL.

For a live **read-only** DEV preview, provide the approved source ID and an explicit allowlist of synthetic test row IDs:

```sh
python3 backend/server.py --dev --sheet-id YOUR_APPROVED_DEV_SHEET_ID --row-ids COMMA_SEPARATED_SYNTHETIC_ROW_IDS
```

Enter the token at the hidden prompt. It stays in process memory, is never written to a file, and is never sent to the browser. Do not add it to a command, URL, GitHub secret used by Pages, frontend configuration or repository. The gateway binds only to loopback and is not a deployable public identity service. Stop it with Ctrl+C when finished.

`--check --dev ...` performs two GET reads, compares the sheet version and prints only counts and request types. It does not print project contents. Both the row allowlist and DEV marker are required. A DEV flag alone is not the pilot's data boundary.

## GitHub Pages

Set Settings → Pages → Source to **GitHub Actions**. Merging into `main` runs checks and deploys the static `web/` folder. Relative asset URLs and hash routes work under `/ORNL-Graphics-Portal/` without a rewrite service.

## Before live service

See [architecture and access](docs/architecture.md), [scope and preservation](docs/scope.md) and [brand / content inventory](docs/design.md). Production employee authentication, role authorization, credential storage and write operations require their own implementation and validation. No present demo role or client-side filter establishes production access control.
