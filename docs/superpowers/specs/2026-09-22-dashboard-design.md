# Dashboard — design

Date: 2026-09-22 · Scope: a read-only local view over a round · Status: approved, not implemented

Companion to `2026-09-22-stage2-acquire-design.md`, which covers stage 2 and defers the
dashboard to this document.

## 1. Purpose

A round takes time. Acquisition over 26 sources with timeouts and multi-step cascades takes
minutes; extraction at the measured local-model rate takes days (D4). The person waiting
needs to see three things: what is being asked, what has been learned so far, and what the
machine is doing right now.

The dashboard is a **derived view** (D9). It reads the JSONL ledgers and computes; it never
writes, never triggers work, and holds no state of its own. Deleting it loses nothing.

## 2. Sequencing

**It is built last**, after a thin vertical slice has carried the 26-source manifest through
stages 3-6 to real verdicts. Revised 2026-09-22; the original plan was to build it first.

Two things changed that. D13 removed the throughput ceiling, so extraction of the manifest is
hours rather than weeks — the waiting the dashboard was meant to make bearable shrank by an
order of magnitude, and a thin slice through every stage became affordable. And the dashboard
is the one component whose value is proportional to having data in **every** stage, and whose
own spec depends on every other stage's schema. Built first, it is the most exposed thing in
the repository to changes upstream of it; built last, every section has real rows behind it and
the honesty rules of §8 become checkable against real cases instead of invented examples.

It is still structured around all six stages, and a stage that is not implemented **declares
itself unimplemented** rather than rendering zero — the precedent set by `cli.py`, which exits
with a message instead of pretending. What that does *not* license is speculative readers: see
§5.

## 3. Module boundaries

```
round_state.py  (new)  reads every JSONL and computes the state of a round.
                       Pure, testable, no HTTP. Consumed by both `report` and the dashboard.
dashboard.py    (new)  transport only: routing, template, polling.
```

The separation is the point. "How far along are we" must not live inside an HTTP handler, or
it becomes untestable and unavailable to the CLI.

## 4. The round state model

`round_state.state(project, store) -> RoundState`

```python
@dataclass(frozen=True)
class StageState:
    name: str              # discover | acquire | normalize | extract | review | synthesize
    implemented: bool
    inputs: int | None     # None means "not knowable", never 0
    outputs: int | None
    rejected: int | None
    progress: Progress | None
    last_write: str | None # ISO timestamp of the newest row this stage wrote

@dataclass(frozen=True)
class Progress:
    done: int
    total: int | None      # None where no denominator exists — see §6
    label: str             # "acquired of candidates found"
```

`inputs`, `outputs` and `total` are `int | None`, never `0` as a stand-in for unknown. The
distinction between "nothing happened" and "we cannot know" is load-bearing throughout this
project and the type enforces it.

## 5. The question spine

The registry is the top of the page, all questions, in registry order. This is what the tool
is for: topics in, questions out.

Per question:

| field | source | denominator |
|---|---|---|
| sources speaking to it | distinct `source_id` across its claims | **sources examined** |
| claims | `claims.jsonl` | — a count, not a percentage |
| surviving review | stage 5 `SUPPORTED` | claims for that question |
| verdict | stage 6 | the four states |
| by source class | every claim carries one (invariant 6) | reported per class before aggregate |

### The denominator, explicitly

Coverage per question is **sources that speak to it, over sources examined**. The total
number of claims a question *could* receive does not exist, so any bar scaled to it would be
an invented denominator — the same error as a corpus read at 42% certifying itself complete.
Sources examined is a real, moving, honest denominator: `Q01 · 7 of 19 examined sources
speak to this question`.

**Examined** means precisely: an acquired source all of whose chunks have been through
`extract`. A source half-processed is not in the denominator, because a question it has not
reached yet would otherwise read as a question it failed to answer.

### Four states, shown as four

`NEVER_ASKED` (no claim ever cited it) and `UNANSWERED_IN_LITERATURE` (claims found, none
survived, or all null) get different colour and different wording. Rendering them alike is
the specific error D12 exists to prevent. `SUPPORTED` and `CONTRADICTED` are likewise
distinct, and `CONTRADICTED` is never styled as a failure state: concluding against a
question is a successful outcome.

### No speculative readers

The table above names fields in `claims.jsonl`, a file whose schema **stage 4 defines and which
does not exist yet**. Writing readers against it now would mean writing them against a guess.

So the rule: the six-stage *structure* exists from the first version, and a *reader* is added
when the stage that writes its ledger lands. A stage with no reader reports
`StageState(implemented=False)` from a declared stage registry — not from an attempted parse of
a file that is not there. The question spine itself reads `questions.yaml`, which does exist,
so from day one it shows every question with the state `waiting — extract not implemented`:
present, empty, and saying why it is empty.

Since §2 now places the dashboard after the vertical slice, in practice most readers will have
their schema settled before they are written. The rule holds anyway, for the stage that is not
finished on whatever day the dashboard is next touched.

## 6. The pipeline strip and progress

```
discover    128 candidates · 2 channels · estimated completeness 0.71 [0.58–0.84]
acquire      19 / 26   0.73   below floor 0.80   INSUFFICIENT_ACQUISITION
normalize     — not implemented
extract       — not implemented
review        — not implemented
synthesize    — not implemented
```

One progress rule per stage, because the stages differ in whether a denominator exists:

- **discover** — **no percentage, ever.** How many relevant works exist in the world is
  unknown. What is shown instead is the capture–recapture estimate from the two independent
  channels with its interval, labelled an estimate (D10). Until the citation channel exists
  (stage 3), it shows the candidate count and states that completeness is not yet estimable.
- **acquire / normalize / review** — real percentages, always written as a fraction with the
  denominator beside them, never as a bare percentage.
- **extract** — a real fraction, chunks done over chunks total, plus a finish estimate from
  the rate observed **in this run** rather than from any recorded constant. The rate now
  depends on which backend is serving the lane (D13), and those differ by orders of magnitude:
  the local server ran at ~5 calls/hour, a hosted endpoint completes the same queue in an
  afternoon. So the estimate is computed, labelled an extrapolation, given with its interval,
  and shown **beside the backend and model it was measured on** — an ETA that does not say
  which backend produced it is not interpretable.
- **synthesize** — no progress. It either runs or it does not.

### Rejections are shown, not hidden

Below the strip, the rejection ledger per gate: what was discarded and why. It is the
denominator, and a page showing only what passed tells half the story. Failures are broken
down by class and by host — the host column is what reveals a campaign being eaten by one
publisher.

## 7. The live activity log

The newest N rows from any ledger, newest first, with the stage that wrote them:

```
10:41:07  acquire  S07  sciencedirect.com 403 → unpaywall → acquired 412 KB  cc-by
10:40:58  acquire  S06  landing page rejected (2 840 chars, "purchase pdf")
10:40:31  acquire  S05  arxiv.org → acquired 1.2 MB
```

Cheap to build — the same JSONL rows, rendered readably — and it is what makes waiting
bearable.

`running` is inferred from ledger mtime within the last 30 seconds and is labelled as an
inference ("last write 4s ago"), never as a claim that a process is alive.

## 8. Honesty rules

Binding, not aesthetic. A violation of any of these is a defect, not a style note.

1. No percentage without its denominator beside it.
2. No absent value rendered as zero. "No attempts recorded" ≠ `0.00`.
3. Every estimate carries the word *estimate* and its interval.
4. An unimplemented stage says so.
5. The four verdict states are visually four.
6. Gate thresholds and `gate_version` are always visible beside the rate they produced.
7. Read-only: no route mutates anything, no button starts a fetch.

## 9. Transport

`claimstone serve <project> [--port 8787] [--host 127.0.0.1]`

stdlib `ThreadingHTTPServer`. No framework, consistent with the dependency rule.

| route | returns |
|---|---|
| `GET /` | the page: one self-contained HTML document |
| `GET /api/state` | `{ledger_mtimes, row_counts_per_ledger, running}` — cheap, for the poll |
| `GET /api/round` | the full `RoundState` as JSON |
| `GET /api/questions` | the spine: one entry per question |
| `GET /api/activity?limit=N` | the newest ledger rows across stages; `limit` defaults to 50, capped at 500 |

Anything that is not a routed `GET` answers 405.

The page polls `/api/state` every 2 seconds and refetches the heavier routes only when an
mtime changed. On this data size the guard is unnecessary; it exists so the pattern still
holds at a few thousand rows.

### Stateless per request

Every request re-reads the ledgers from disk and recomputes through `round_state`. No cache,
no in-memory model. This is what makes it safe to run while a stage is writing: the writer
appends, the reader re-reads, and append-only removes the need for a lock.

### Tolerating a torn tail

The final line may be half-written at the moment of reading. The dashboard's reader skips a
trailing line that does not parse and reports the row count it actually read. The pipeline
stages do **not** tolerate this: a line that fails to parse mid-file is an error there,
because a silently dropped row is a silently wrong denominator.

## 10. Privacy and binding

Binds `127.0.0.1`. A non-loopback `--host` is accepted only when passed explicitly, and
prints a warning naming the privacy rule: the ledgers carry the consuming system's reading
list, which is why `projects/` and `store/` are gitignored.

No authentication is implemented, because none would be meaningful on a loopback socket and
implementing a weak one would invite exposing the port.

## 11. Rendering

One self-contained HTML document from a module-level template. Inline CSS, inline JS, no
CDN, no web font, no chart library. It works offline and discloses nothing to a third party
— which matters given what the data is.

Bars and meters are CSS. Legible in light and dark, and readable at a narrow window: someone
watching a long round keeps this open beside a terminal, not full-screen.

Colour never carries meaning alone — every state also carries its word, so the four verdict
states survive a monochrome screen and a colour-blind reader.

## 12. Testing

| file | covers |
|---|---|
| `test_round_state.py` | per-stage counts from fixture ledgers; `None` vs `0` for unknown vs empty; unimplemented stages; question spine denominators; four-state assignment including the `NEVER_ASKED` / `UNANSWERED_IN_LITERATURE` split |
| `test_dashboard.py` | route functions against a temp store; 405 on POST; torn final line skipped; non-loopback bind requires an explicit flag; one real GET against a port-0 bind for wiring |

`round_state` is where the logic lives, so that is where the tests are. The HTTP layer is
tested for wiring and for the two refusals, not for content.

## 13. Out of scope

No control plane: no starting or stopping a stage from the page, now or later. A browser tab
that can launch fetches is a way to blow the per-domain budget by refreshing, and it would
make the dashboard a writer, which §1 forbids.

No history or round-over-round comparison in this version. The ledgers are append-only, so
it remains possible later; it is not specified here.

No multi-project view. One `serve` per project.
