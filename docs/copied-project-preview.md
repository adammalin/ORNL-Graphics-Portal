# Read-only copied projects in the DEV portal

> Policy update: see [the current user/agent authorization audit](agent-authorization-audit.md) for explicit admin access to selected copied DEV jobs and recoverable portal deletion. Earlier no-delete/read-only-copy results below describe their original qualification scope.
Selected older projects from the existing DEV sheet can be shown alongside synthetic editable records. This does not connect to production or change any native sheet/report/dashboard/filter/workflow definition.

## Private selection

Add an optional `copiedRowIds` list to the existing private pilot configuration:

```json
{
  "copiedRowIds": ["SELECTED_COPIED_ROW_ID"]
}
```

The default is empty. Use at most twenty unique numeric row IDs from the exact approved DEV sheet. In native Smartsheet, open the desired row's **Row Actions > Properties** to find its permanent row ID. Do not rely on row numbers, which can change when rows are inserted. Store actual selections only in ignored private configuration.

The initial laptop selection is eight copied records. Their IDs were read through native row properties; the sheet view was returned to its existing DEV filter afterward. The private config and SQLite state were backed up before enabling the selection. The backend must be restarted once to load this implementation; later selection changes reload with requests without extending any source, invitation or session permission.

## Reading and editing stay separate

- Synthetic projects still come from the validated **DEV - Demo projects** filter and must carry the **DEV Test Record** marker.
- Copied projects use a second fixed-sheet GET with only the configured row IDs. Both snapshots must have matching source version, schema and access level. Unselected rows are not normalized or returned to the portal.
- Configured copied row IDs never join the writer's allowlist, even if someone later checks their DEV marker. Service permissions, low-level row resolution and direct update/upload guards independently reject them.
- Existing coordinator/designer/creator visibility rules still apply. This selection does not invite additional users or give designers other designers' job details. Native Smartsheet access is still required.
- Copied attachments can be read through the existing authenticated job-scoped download path. Upload, replacement and deletion remain unavailable for copied projects.
- AI context, reference inventory, draft and review routes reject copied jobs, including when a copied job ID is accidentally included in the separate AI allowlist. No copied job triggers notifications or downstream actions.

## User experience

Cards and list entries carry **Copied project - Read-only** labels. A source filter switches between all projects, copied projects and test projects. Copied details show source information with no edit, offer, response, upload, AI or drag control. Test jobs retain their existing permitted actions.

Original native **Project Stage** values are used when present. For older records with no Project Stage, the portal projects existing Status values into its lanes: Designer Requested to Assigned, Designer Accepted to Accepted, Completed/Closed to Completed, and Canceled/Cancelled to Archived. An existing Completed Date also places an otherwise unmapped record in Completed. Other unmapped records remain in New. These are display mappings only; the original Status is shown in details and no source cell or human acceptance is rewritten.

Copied designer names can appear as source information without becoming eligible recipients for new offers. Only existing invited users are offered work. Workload displays explicitly describe the data as a selected sample; it is not a complete live team capacity assessment. Historical pending requests are not counted as actionable portal offers.

## Rollback

Set `copiedRowIds` to an empty list and refresh. Copied projects disappear from the portal on the next source read. Do not remove rows, change DEV markers, modify the native filter or replace the private state database to roll this feature back.
