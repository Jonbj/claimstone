# Finite network schedules

`store/<project>/network_schedules.jsonl` records `planned`, `authorized`, and
optional `revoked` events. A schedule names 1–32 **existing** network batches.
Each entry freezes its batch ID, flow, stage, exact operation IDs and units,
including query/candidate, hosts and per-unit physical request ceiling. It
also fixes a UTC `not_before` and `expires_at`; windows end within 366 days
of planning. The schedule's lifetime request ceiling must equal the sum of
its batch ceilings. Its SHA-256 ID hashes this entire immutable plan.

`schedule-plan` writes only the planned event. `schedule-authorize` is the
operator's one explicit approval of those listed campaigns, recorded on
each operation. An authorized operation cannot start before its window, after
expiry, or after `schedule-revoke`. Both the polling worker and a direct
`scheduler run` check the window before the bounded operation starts. A worker
restart does not extend it. The operation holds the project writer lock while
it runs, so a started unit may finish after its window closes and revocation
takes effect once that unit finishes. Existing physical request ceilings, robots,
host budgets, frozen input and code checks still apply.

The command takes an entries JSON file, for example:

```json
[{"batch_id":"<frozen batch ID>","not_before":"2026-10-12T08:00:00Z","expires_at":"2026-10-12T09:00:00Z"}]
```

Run `claimstone scheduler schedule-plan PROJECT --entries-file FILE
--max-total-requests N`, inspect its output and the cited batch plans, then
run `claimstone scheduler schedule-authorize PROJECT SCHEDULE_ID`. Use
`schedule-status` and `schedule-revoke` for inspection and stopping future
work. The operator must explicitly approve the concrete schedule; a local
mandate or a generic request to run automatically is not an approval.

`periodic-plan` can create finite future rounds and freeze their exact query
batches before constructing this same schedule. Its input lists new round
names, titles and ordered nonoverlapping windows; all topic-term/API queries
must fit the per-round unit cap. Repeating the same plan is idempotent while
the rounds have no candidates. It does not authorize the schedule.
`periodic-audit` reports per-round query outcomes, ancestor admission and
whole-store admission, without writing a judgement. These commands cannot preapprove
unknown candidates, invent search terms or renew a protocol. Acquisition,
purchase and verdicts keep their existing gates.

Discovery plans hash the complete frozen population ledger. Planning creates
all dated flows before the batches so its own later rounds do not invalidate
earlier inputs. A later, unrelated population write or a code/protocol change
can still invalidate a pending operation; inspect and replan under fresh
authorization rather than executing stale work.
