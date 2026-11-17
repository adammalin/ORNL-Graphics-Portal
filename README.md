# ORNL Graphics Portal

A separate custom-portal proposal alongside the existing native Smartsheet dashboards. The visual system follows the Team App Library: Mulish, ORNL Green / Hale Navy, square components, a restrained Energy accent and clear project navigation. Design draft; not an approved production service. No ORNL logo is reproduced.

## Separate public and local modes

| Mode | Data | Changes |
| --- | --- | --- |
| Public GitHub Pages demo | Fictional projects and people bundled in `web/demo-data.js` | In this browser tab only; reset on reload |
| Local DEV read-only | Explicit synthetic row IDs, or the verified native DEV-only filter | GET only |
| Local DEV editor | Approved synthetic DEV rows plus new DEV intake | Saves intake, selected job fields, offers/responses, stages and new attachments |
| Invited OAuth pilot | Approved synthetic DEV jobs, filtered by verified identity and server role | Per-user Smartsheet permissions; no shared-token fallback; no deletion |

The GitHub Pages deployment uploads **only `web/`**. It does not deploy a backend, include API credentials or publish DEV-sheet contents. No mode edits native dashboards, form definitions, formulas, reports, sharing or automations. DEV editing changes approved synthetic job cells and adds new rows/files; existing attachments are retained.

## Try the prototype

- Employee intake: `#/new`. No Graphics membership is required to try the synthetic demo. Live employee submission still needs ORNL-approved authentication and a secure submission endpoint.
- Designer offers: preview Alex Rivera, open the sample seminar poster, and accept it. It then appears in My Work.
- Kanban / list: search, filter and drag your assigned cards, or use the job's keyboard-accessible stage selector.
- Job details: `#/projects/DEMO-1046`. Each job has its own URL, description, tasks/deliverables, metadata, reference files and links. No shared dashboard selection log is used.
- Reference previews and downloads: bundled synthetic layout and notes. Demo uploads are memory-only and disappear on reload.
- Team workload: accepted active assignments and pending offers are counted separately; completed/archived jobs are excluded. Sample planning thresholds are not actual availability.
- Completion / archiving: retain records. The demo stamps a completion date locally; it does not retrofit native sheet automation.

Demo role switching is a presentation tool, **not authentication or a security boundary**. All public examples are fictional. AI, email notifications, production intake/writes, calendar access, SCOUT and Dropbox are not connected. A separate [invited OAuth pilot](docs/pilot.md) adds server-enforced identity and roles behind an authenticated HTTPS tunnel. Live multi-user qualification remains distinct from its automated tests.

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

`--check --dev ...` performs two GET reads, compares the sheet version and prints only counts and request types. It does not print project contents. Both the row allowlist and DEV marker are required in this narrow mode.

For **DEV saves**, run `./start-dev.command` using the private `.local/dev-config.json`. The editor defaults to port 4174 and discovers synthetic requests through the existing, validated DEV-only filter. See [local DEV setup, field mapping and safeguards](docs/local-dev.md). The public Pages configuration remains demo-only.

## AI and agent implementation plan

The [detailed implementation specification](docs/ai-agent-implementation-spec.md) starts with users' existing Codex/browser agents, followed by scoped API/MCP tools. Smartsheet AI and a central model API key are not prerequisites for that agent-assisted path. It defines shared authorization, job context, reviewable briefs and field proposals, reference coverage, contracts, acceptance tests and a separate later phase for unattended processing. The linked schema, fictional example and prompt are design artifacts; they do not enable these features.

[Stage 0 implementation and validation](docs/ai-stage-0-validation.md) extracts the shared job service, adds immutable principal snapshots, private-state migrations and a browser-authenticated capability endpoint. AI analysis, draft UI, agent bearer authentication and MCP remain disabled.

## GitHub Pages

Set Settings → Pages → Source to **GitHub Actions**. Merging into `main` runs checks and deploys the static `web/` folder. Relative asset URLs and hash routes work under `/ORNL-Graphics-Portal/` without a rewrite service.

## Before live service

See [architecture and access](docs/architecture.md), [scope and preservation](docs/scope.md) and [brand / content inventory](docs/design.md). Production employee authentication, role authorization, hosted credential storage and production write qualification still require implementation and validation. No present demo role or client-side filter establishes production access control.
