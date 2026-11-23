# Portal-owned organization routing

New DEV requests now write organization values into their existing native columns and assign one coordinating manager in the same row creation. No native workflow needs to be enabled. This is coordinator routing; it does not select or accept a designer.

| Portal field | Native Smartsheet column | Input |
|---|---|---|
| Directorate | Owner Directorate | Searchable existing column choices; blank allowed for coordination |
| Division / office / facility | Owner Division/Office/Facility | Searchable existing column choices; blank allowed |
| Group / department | Owner Group | Existing permitted groups plus an explicit new entry |
| Coordinating manager | Assigning Manager | Server-selected contact from the private routing policy |

The staff form and Microsoft employee form use the same mapping. Microsoft intake remains disabled unless separately configured. Existing group values serialized into Additional Details remain readable; human-entered notes are preserved. Existing records are not bulk backfilled or reassigned.

The source supplies flat choice lists. The portal does not claim an authoritative directorate-to-division hierarchy or infer organization from prose, email, identity or AI output.

## One routing decision

The private pilot configuration may contain an `organizationRouting` policy:

```json
{
  "version": 1,
  "managers": {
    "research": {"email": "research@example.org", "name": "Research Coordinator"},
    "central": {"email": "central@example.org", "name": "Central Coordinator"}
  },
  "divisionOverrides": [{"values": ["Fictional Shared Facility"], "manager": "research"}],
  "directorates": [{"values": ["Fictional Science"], "manager": "research"}],
  "default": "central"
}
```

Specific division overrides take precedence over directorates. Unmapped or missing organization data goes to the single central coordinator for triage. Conditions within each dimension must be disjoint; duplicate values, unknown managers and contacts outside invited coordinator/admin accounts invalidate the policy. Actual contacts and organization rules stay in private configuration, outside the public repository and Pages demo.

Native organization choices are validated server-side. Callers cannot set Assigning Manager directly. Changing routing fields on an existing job requires coordinator/admin authority; the server updates organization and manager atomically, preserving the requested/accepted designer and project stage. Editing only a group, brief, estimate or other unrelated field preserves the manager. A routing-policy change during a save stops the write. Idempotent request replay returns the original saved job rather than rerouting it.

## Native workflows and source boundaries

Keep every DEV native automation disabled under the existing pilot write guard. In particular, the three legacy manager-assignment workflows are superseded for portal-created requests and must not later be enabled alongside portal routing. Their definitions are preserved for rollback and comparison. This change neither edits them nor sends email, creates a response-log row, or changes any native dashboard/form.

Live-sheet values, files and workflows remain outside the writer. The portal continues using only its pinned DEV sheet, existing row-selection restrictions, user ownership/roles, native field protection, source/schema validation and write-review expiry. No deletion or expanded account access is introduced.

Native Smartsheet intake does not gain portal routing merely because its rows exist in the same sheet. Native-only intake automation and notification migration remain separate future work; do not claim those paths work while all native automations are off.

## Verification

Use fictional tests for native field mapping, all routing outcomes, division overrides, unknown/missing choices, custom groups, legacy-note preservation, protected fields, creator/assignee permissions, self-acceptance, accepted-assignment edits, policy changes during writes, and active-automation rejection. Validate the actual private policy against the current DEV column choices, including the previously overlapping cases.

For live DEV QA, use a clearly labeled synthetic job. Confirm organization values and coordinating manager after a reload, then exercise a division override and fallback without changing designer acceptance. Verify old jobs and attachments remain intact and no native automation has become active. Back up the private config and SQLite state before deployment; normal startup continues using the existing Keychain-backed launcher.
