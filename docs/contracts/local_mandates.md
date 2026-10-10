# Local mandate ledger

`store/<project>/local_mandates.jsonl` is append-only. Versions 1 and 2 have two events:
`enabled`, followed at most once by `disabled`. The first event stores a
`mandate` object; `mandate_id` is its canonical JSON SHA-256. Its fields are
`project`, `flow_id`, `protocol_sha256`, `code_sha256`, `extract_model`,
`review_model`, `max_total_local_calls`, `authorized_by` (OS UID and login),
`created_ns` and `version`. Both events carry `version`, `mandate_id`, `event`
and UTC `at`. The disabled event also carries `by` (OS UID and login).

Version 2 adds `proposal_policy` with exact `discover_apis`,
`discover_hosts`, `acquire_hosts`, `max_units`, `max_requests_each` and
`per_query`. Empty API/host lists mean no proposal of that stage. The worker
passes these values to the existing bounded batch planner after its local
pass. The resulting `operation_batches.jsonl` and `operations.jsonl` rows are
only **planned**. Their exact units, hosts, request caps and skipped items
remain reviewable; `authorize-batch` is still a separate operator action.
Version 1 mandates remain readable, with no network proposals.

At most one mandate is active for a flow. A new mandate after disabling the
old one is a new dated authorization, not an edit. An active mandate permits
local stage plans for that flow and the execution of external plans authorized
elsewhere. It cannot approve any new external request, paid model call,
purchase, scientific admission or verdict.

`auto-status.pending_batches` lists batches in the flow with at least one
operation still awaiting authorization. This list can include batches planned
manually; it is a view of pending decisions, not proof that the mandate
authorized them. Repeated worker passes reuse an unchanged batch ID and do
not append a duplicate plan.

`operations.jsonl` remains the accounting source for model calls. Each local
drain authorized through a mandate has `identity.mandate_id` on its
`authorized` event and the mandate ID as `plan.run_label`, preventing reuse of
an authorization from another mandate or a manual pass. Sum
`plan.max_model_calls` over those authorized drain
plans to obtain the consumed allowance, including interrupted and failed
plans. The project writer lock spans checking this sum, planning,
authorization and the local drive. No worker restart can reset the cap.
