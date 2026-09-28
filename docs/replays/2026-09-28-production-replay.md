# Production offline replay — 2026-09-28

Applied after D48, at code revision `7e7b6d6`, using the operational tool added with this report.
The operator authorized production offline replay and measurement of the remaining work.
No publisher, model runner or API was called. No floor, parser, registry, chunk generation or
adjudication changed. Profiles were not rebuilt; their current preview remains provisional.

## Reproduce

```bash
# Read-only current workload; review queues exist only in temporary copies.
.venv/bin/python tools/replay_answers.py projects/pmc-screen-time
.venv/bin/python tools/replay_answers.py projects/alembic-s4 --manifest-only

# Apply every stored extraction/review batch to the project's append-only ledgers.
.venv/bin/python tools/replay_answers.py projects/pmc-screen-time --apply
.venv/bin/python tools/replay_answers.py projects/alembic-s4 --apply --manifest-only
```

`--round` and `--manifest-only` select the workload measurement, not the replay. Replay rejudges
all stored readers and batches, including historical probes, then runs both real harvesters.
The tool checks the registry and every ledger before writing; an incomplete tail or corruption
refuses the operation. It verifies the exact original prefix of every pre-existing store file,
permits additions only to the named result/gate/review/registry ledgers, and repeats the entire
operation to prove zero additional writes. Applying a replay does not refetch or normalize anything.

A content-addressed audit is retained locally under `store/<project>/audits/offline-replay/`.
It contains hashes, byte lengths, per-batch outcomes and the remaining workload, without rewriting
any earlier artifact. Missing response bytes are counted and left unresolved.

## What the actual replay returned

| corpus | extract/review batches | accepted/rejected before | accepted/rejected after | original claim ids retained | new claim ids | original review ids retained | usable full-annotation reviews |
|---|---:|---:|---:|---:|---:|---:|---:|
| PMC | 1 / 1 | 1,668 / 259 | 1,668 / 259 | 1,668 | 0 | 42 | 0 |
| alembic-s4 | 7 / 2 | 7,021 / 1,143 | 7,194 / 1,166 | 6,991 | 203 | 41 | 0 |

The current extraction sets match D48's complete temporary-store measurement. These are annotations,
not independent studies. First passes append 2,978 and 3,951 rejudgement rows respectively;
extraction harvest stamps 1,668/259 and 7,194/1,166 decisions. Legacy review harvest appends
42 and 74 rows: 33 previously unharvested Alembic reviews are recovered from stored responses.
The original 83 review ids are retained and there are now 116 historical review ids altogether.
All attest the old narrower task, so none certifies review v2. Alembic has 27 current results
without stored response bytes; PMC has zero. Replay does not invent an answer for them.

Every repeat reports zero rejudgements, acceptances, rejections and reviews, and the complete file
snapshot is unchanged. **All original bytes are preserved.** Derived ledgers grow only by appending.
Current scoped annotations are all stamped with claim gate v4; `unregated` and `unharvested` are zero.

## Remaining workload, with its population

| population | confirmed/found | acquisition status | active chunks | accepted annotations needing review | unique review calls | unanswered extraction readings |
|---|---:|---|---:|---:|---:|---:|
| PMC, whole declared corpus | 37 / 40 | OK, 0.925 ≥ 0.80 | 734 | 1,668 | 1,668 | 34 |
| Alembic, curated manifest | 14 / 25 | INSUFFICIENT_ACQUISITION, 0.56 < 0.80 | 406 | 6,188 | 6,183 | 28 |

Alembic's whole-store 7,194 accepted annotations are not the curated manifest's 6,188. Its missing
response count and per-batch unanswered-result figures are also not the selected population's
unanswered-reading count. They measure different obligations and must not be substituted.
Identical full-review prompts merge explicit targets, explaining five fewer manifest calls than
annotations. Reader independence is still checked per target; no reviewer was selected for this plan.

| kind | PMC unanswered | Alembic manifest unanswered |
|---|---:|---:|
| effect | 10 | 7 |
| heterogeneity | 4 | 10 |
| method | 15 | 11 |
| premise | 5 | 0 |

PMC's present review queue contains 12,884,176 prompt characters and a total output ceiling of
667,200 tokens (400 per call). Alembic's manifest contains 48,629,059 prompt characters and a
2,473,200-token output ceiling. These are actual character counts and configured caps, **not tokenizer
measurements, generated usage or a price**. Cost remains unknown until a reader and its pricing are
chosen. New annotations from the missing extraction readings would add review work.

Q04 has **42 current annotations to review** and shares **10 missing effect readings**. Its present
review calls contain 319,562 prompt characters and have a 16,800-token total output ceiling. This is the
smallest previously investigated PMC profile to resume, not a completed scientific result. All current
PMC annotations were extracted by `ollama-cloud/deepseek-v4.1-flash`; that reader cannot review them.
Alembic remains below its acquisition floor, so its review count is planning information and gives
no permission to sign or treat the corpus as complete.

The immediate paid-work decision is the backend/budget for finishing extraction and evaluating an
independent reviewer on the **complete v2 task**, preferably on the bounded Q04 work first. Agreement
with the original 83 narrower-task verdicts cannot certify fields those reviews never saw.
After successful new readings, harvest and review the new annotations, then rebuild and read profiles
v5. A person alone chooses and signs a verdict. Europe PMC/JATS and prompt experiments remain separate.

Three operational regression tests verify preserved original bytes, repeated replay, refusal before
writing a torn ledger and read-only queue measurement. Required checks: 881 tests pass, 7 are skipped;
six project configurations validate; all 16 instrument versions are acknowledged.
