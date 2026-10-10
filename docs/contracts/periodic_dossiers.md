# Periodic cumulative dossier

`claimstone scheduler periodic-dossier PROJECT SCHEDULE_ID` and
`GET /api/v1/projects/{project}/periodic-dossiers/{schedule_id}` recompute the
same read-only JSON. `periodic-finalize` and a local mandate on a scheduled
child flow can persist a final snapshot. Neither path makes a network or model
call and neither decides a scientific verdict.

The live report has `state`, `blockers`, `audit`, `profiles`,
`human_decisions`, `snapshot_sha256`, `finalized_dossier_id`, `finalized_at`,
`snapshot_stale`, `needs_finalization`, `history_count` and `verdict: null`.
`audit` is exactly `periodic.audit`: schedule and query states, ancestor and
dated-round acquisition, and whole-corpus acquisition. `profiles` are the
current whole-store stage-6 previews, with their exact evidence and profile
hashes; they are empty when the cumulative floor fails. `human_decisions`
contains recorded signatures with their live `stale` status, including
historical signatures when the current floor blocks profiles. A missing
signature is `null`, never a sixth verdict. An operational question remains
`LITERATURE_VERDICT_NOT_APPLICABLE` and cannot receive a verdict.

| `state` | Meaning |
|---|---|
| `INSUFFICIENT_ACQUISITION` | The cumulative floor or a class floor failed; no current profile is supplied. |
| `WAITING_FOR_SCHEDULE` | A query, ancestor round, binding, or dated round is unfinished. Current profiles may be shown, but cannot be finalized. |
| `WAITING_FOR_EVIDENCE` | The schedule is ready, but extraction, review, or another profile obligation remains. |
| `READY_FOR_HUMAN_READING` | Every gate passed; still no automatic verdict. |

`periodic-finalize` holds the project writer lock. Only in
`READY_FOR_HUMAN_READING` may it append the current whole-store profiles to
`profiles.jsonl`. It does so only when a stored hash differs. It then appends
one row to `periodic_dossiers.jsonl` when the content address changed. The row
has `version: 1`, `schedule_id`, `dossier_id`, `snapshot`, `at`. `snapshot`
hashes the schedule audit, protocol and registry identities and every current
question profile hash; `dossier_id` is its canonical JSON SHA-256. A second
pass with identical evidence writes nothing. A later change keeps the earlier
row and yields a new ID. Signatures are outside the snapshot: a person may
sign the same evidence without changing its evidence identity. A signature
on an older profile is displayed as stale by the existing verdict contract.

The live report is a generated export of current evidence. Its
`finalized_dossier_id` points to the latest persisted snapshot, while
`snapshot_stale` says whether that snapshot still represents current evidence.
The ordinary flow export can carry the append-only dossier ledger in its
verifiable byte snapshot; the report itself can be saved as JSON through the
CLI or API. No stored dossier row is rewritten.
