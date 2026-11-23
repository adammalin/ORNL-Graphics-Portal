# Portal-owned assignment and status transitions

The portal owns assignment changes for its authenticated DEV actions. Native DEV workflows stay disabled. Neither live-sheet values nor native workflow/dashboard/form definitions are changed. This does not activate notification delivery or legacy response-log copying.

## Native fields

Each assignment change uses one row write for the requested designer, designer response, Project Stage, routing Status and Update Status. Assigned Designer remains the existing native formula; the portal never overwrites it.

| Action / state | Project Stage | Status (routing) | Designer Response | Update Status |
|---|---|---|---|---|
| New request without assignment | New | New | Empty | Empty |
| Offer / reoffer | Assigned | Designer Requested | Empty | Pending |
| Accept / claim / create and self-accept | Accepted | Designer Accepted | Yes | Responded |
| Decline | New | New | No | Responded |
| Reassign an accepted active job | Assigned | Designer Requested | Empty | Pending |
| Production progress after acceptance | In Progress / In Review | Designer Accepted | Yes | Responded |
| Complete accepted work | Completed | Designer Accepted | Yes | Responded |

The native Status list describes request routing and has no Completed/Archived choices. Project Stage remains the production lifecycle, and Completed Date records completion. Archives retain the recorded response, with the corresponding routing status; an unanswered archived offer is no longer Pending. Completion/reminder logic must inspect Project Stage, not infer active/completed work from routing Status alone. Archiving unfinished work does not invent a completion date. Stage-only changes preserve nonstandard legacy technical-edit/cancel/closed Status values instead of rewriting them.

Req Assigned / Closed is filled only on an explicit acceptance/self-acceptance when blank. An existing date is retained. Its historical meaning is overloaded, so it is not used as the current offer or acceptance timestamp. Existing records are not bulk repaired or backdated. Unrelated detail edits and uploads preserve responses, routing values and assignment times.

## Permissions and transition rules

- Only the offered, authenticated designer may accept or decline a current offer. Coordinators/admins cannot accept on someone else's behalf.
- Assign to me and accept during creation derives the designer from the signed-in account. Claiming a visible, editable, unassigned New request uses the same identity rule. No caller-supplied claim designer is accepted; visibility/ownership policy is unchanged.
- Coordinators/admins can explicitly reassign an active accepted job to a different invited designer, with a reason and `confirmReset: true`. This clears prior acceptance and requires the new designer to accept. Details, files, first native assignment date and history remain.
- New/Assigned stage shortcuts cannot clear or manufacture acceptance. Production progress and completion require acceptance. Completed jobs can be archived; archived jobs stay archived. Reassignment of closed work is unavailable; reopening is a separate future policy.
- Duplicate offers to the same pending designer do not reset the offer time. Native revision checks reject stale responses, including an old offer to the same person after intervening reoffers. Durable receipt replay performs no second native mutation or history event.
- During native formula recalculation, the current Requested Designer and explicit Yes/No response take precedence over an old cached Assigned Designer value. A stale formula contact cannot hide a pending reassignment or override a decline.

## History and dates

Private schema migration 6 adds `portal_assignment_events`; native columns are unchanged. Assignment intent is recorded before the native request and confirmed alongside the durable operation receipt only after native acknowledgement. Uncertain outcomes remain explicitly unconfirmed. Readback failures retain the confirmed event and use the existing safe receipt recovery.

Each new offer/self-acceptance/claim/reassignment gets a new generation ID. A generation keeps its original offer time; acceptance and response get their own UTC timestamps. Stage events retain those times. The first recorded completion gets its own timestamp. Creator and actor identity come from the verified session. No timestamps or history entries are accepted as editable client fields.

The details panel shows routing status, response, current offered/accepted times and the latest 100 history events, including actor, stage, recipient and reassignment reason. All events remain stored privately. Prior native assignments have no inferred timestamps. An observed native assignment change outside portal history is shown as untracked until a new portal transition; old history remains available. Access to history follows the job's existing read permission.

This history is a portal journal, not proof that a separate native Graphics Response Log was updated. It contains no email sender, scheduled reminders, Graph/MCP enablement or model execution. Those remain separate work.

## Verification

Use fictional accounts for every state transition, unauthorized acceptance/reassignment, claim spoofing, duplicate/stale offers, self-acceptance, safe receipt replay, uncertain writes, native formula lag, preserved legacy statuses and unchanged dates after unrelated edits. Check private migration preserves old state. Live DEV QA should use new labeled synthetic jobs only, leaving copied projects untouched; native writes must still pass all existing source/protection/automation checks. No notifications need enabling to test any of these paths.
