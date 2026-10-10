# `journey` — the guided research page, computed on the server

`journey_version 2` (`claimstone/journey.py`, D111, D116). A block of `GET …/flows/{id}/overview` and
`GET …/unbound/{slug}/overview`. It is computed from the overview's own `Computed` object and inbox
cards; the browser renders it as received.

```
journey: { journey_version, topics[{id,label,terms}], questions{total,literature,operational},
           steps[{n,key,title,actor,status,summary,figures}], blocks[{key,title,status,figure}], selection{…},
           needs_you{required,optional,ready_to_sign,note}, running[...]|null, running_note }
```

- `actor`: `you` or `claimstone`. `status`: `done`, `partial`, `running`, `waits_for_you`, `blocked`,
  `not_started`, `not_applicable`.
- `figures` holds the numbers the summary quotes. Unknown is `null` in `figures` and "—" in the
  sentence, never 0. A summary is a fixed template chosen by status; no wording varies by result.
- "Literature question" means any question whose `kind` is not `operational`.
- `running` lists this flow's operations whose last event is `authorized`, `started`,
  `call_started` or `unit_completed` (the scheduler's "continuing" set), each with its `state`.
  Stages are mapped as follows: `discover`, `acquire` and `normalize` to themselves;
  `extract-build|drain|harvest` to extract; `review-build|drain|harvest` to review; `synthesize` to
  itself.
- "Running for S" is stricter: an operation of stage S whose `state` is `RUNNING_OR_LOCK_HELD`, the
  scheduler's own word for work in flight with a writer holding the project lock. An authorized
  operation no worker has started, and an interrupted one, stay listed but do not make a step
  `running`, because no recorded event supports that claim (review of J1, 2026-10-08).

## The steps as built

| n | key | actor | status rule (first match) | figures |
|---|---|---|---|---|
| 1 | protocol | you | legacy selector: `not_applicable`; binding `CURRENT`: `done`; else `blocked` (names `binding_state.differences`) | registry_version, questions_total/literature/operational, bound_at (flow row `created_at`), drifted_parts |
| 2 | search | claimstone | running; stage discover outputs none/0: `not_started`; admission unreadable or `awaiting_discovery` blocking: `partial`; else `done` | candidates, per_class (admission `by_class[*].found`), note (stage detail verbatim) |
| 3 | copies | claimstone | running; found none/0: `not_started`; `final` and status `OK`: `done`; `final` and `INSUFFICIENT_ACQUISITION`: `blocked`; else `partial` | confirmed, found, obtained, rate, floor, status, not_obtained (found − obtained), not_a_document |
| 4 | documents | claimstone | running; normalize outputs none/0: `not_started`; admission unreadable or `awaiting_normalize` blocking: `partial`; else `done` | documents, rejected |
| 5 | annotate | claimstone | running; extract progress none: `not_started`; done == total: `done`; else `partial` | readings_answered, readings_expected, annotations_kept, rejected |
| 6 | review | claimstone | running; progress none: `not_started`; done == total: `done`; done > 0: `partial`; else `not_started` | reviewed, accepted |
| 7 | profiles | claimstone | `unavailable` set: `blocked` (summary is that text verbatim); running; synthesize outputs none/0: `not_started`; a literature question provisional or without a profile: `partial`; else `done` | profiles, provisional, final (literature questions) |
| 8 | sign | you | no literature question: `not_applicable`; ready_to_sign > 0: `waits_for_you`; all signed (non-stale verdict): `done`; some: `partial`; else `not_started` | ready_to_sign (ADJUDICATION cards), signed, literature_total, operational |

## Readings chosen where the table was ambiguous

Each is the one that never claims more progress than the ledgers show.

- Step 2 and 4: when admission could not be read (`admitted` is null), the step is `partial`, never
  `done`.
- Step 4: no prepared document is `not_started` even when copies were obtained (the table named only
  "acquire outputs 0").
- Step 7: a literature question with no profile counts as not final. Profile counts exclude
  operational questions, which receive no verdict.
- Step 7 is `blocked` before the running check: a corpus that refuses profiles is not producing them.
- `rejected` is null where the stage records none (its ledger convention is none-or-unknown), shown
  as "—".

## `needs_you` and `running`

- `ready_to_sign` is the number of `ADJUDICATION` inbox cards.
- `required` and `optional` are `decisions.open_items` split on `required`. A legacy selector gives
  `null` and `note: "decisions belong to a bound flow"`; a damaged decisions ledger gives `null` and a
  named note.
- `running` is `[]` for a legacy selector. A damaged operations ledger gives `running: null` and a
  `running_note`; steps then show no `running` status.

## The six blocks (D116)

`blocks` is the flow page's strip, in this order: `protocol`, `pipeline`, `selection`, `intake`,
`execution`, `reading`. Each tile has a `status`, a short `figure` (a fixed template over numbers;
unknown is "—") and the block's `title`. Statuses are the journey's, plus `idle` (the ledger reads and
nothing is waiting), `advisory`, `not_declared` and `unavailable`.

| block | status rule | figure |
|---|---|---|
| protocol | step 1's status; `not_applicable` for a legacy selector | `{questions_total} questions · floor {floor}`, or `protocol not verified` |
| pipeline | from steps 2-7: `done` if all `done`; else `blocked` if any; else `running` if any; else `not_started` if all; else `partial` | `{done} of {total} steps done` (a count of steps, never a percentage), plus ` · {n} candidates in {k} other round(s)` when the tile is `not_started` and the store holds candidates in other rounds |
| selection | `not_declared` when nothing is declared; `unavailable` (declaration unreadable, or any scope in a named error); otherwise `advisory`. **Never `done`.** | `{screened_count} seen · {unobserved_count} unseen` for one scope, `{n} scopes` for several; `no scope for this flow`, `declaration unreadable` or `{n} scope(s) unreadable` otherwise |
| intake | `waits_for_you` if `needs_you.required` > 0; `idle` if 0; `unavailable` if null; `not_applicable` for a legacy selector | `{required} required · {optional} optional` |
| execution | `running` if an operation is running in the strict sense above; else `idle` (also for a legacy selector, whose `running` is `[]` by contract); `unavailable` if `running` is null | `{live} running · {listed} listed` |
| reading | step 8's status | `{ready_to_sign} to sign · {signed} of {literature_total} signed` |

The Protocol tile's figure is read from the live project, so for a flow whose binding is `DRIFTED` it
describes the drifted protocol, not the bound one (its status is `blocked`).

The page opens on the first block, in this order, whose status is `waits_for_you` or `blocked`;
otherwise on `pipeline`. The selection lives in the URL as `?block=`.

`selection` carries the advisory source-selection read of `claimstone/selection_view.py`; see
`source_selection.md`. It is present for every selector; `state` is `NO_SCOPE_DECLARED` when nothing is
declared for the round.
