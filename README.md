# Claimstone

**English** · [Italiano](README.it.md)

**A reading machine that refuses to overstate what it read.**

You give it a set of topics and a frozen list of questions. It finds the literature, obtains legally what
it can, reads every source, and returns — per question — the evidence it found, bound to verbatim quotes,
with the coverage that evidence rests on.

It is built around one failure it will not commit: **reporting "we found no evidence" as "there is no
effect."** Everything unusual about the design follows from that.

## Why it works this way

**A claim without a verified quote is discarded, not softened.** Every claim carries a quote that is
checked *in code* to be an exact substring of the source text, and every number and inequality in the claim
must appear in that quote too. What fails goes to a rejection ledger, which is the denominator — you cannot
read the acceptance rate without seeing what it rejected.

**A corpus that did not obtain what it found produces nothing.** If a round obtained less than its declared
floor, it reports `INSUFFICIENT_ACQUISITION` and writes no conclusions at all. There is no flag to override
this. A corpus read at 42% that certifies itself complete is worse than no corpus, and that is the real
situation this project was built to stop.

**No verdict is automatic.** The engine produces an *evidence profile* — the results, the direction count
labelled as a count, the coverage, the rejections, and what a second reader refused to pass. A person reads
it and signs, against the hash of what they were shown. If the evidence later changes, the signature is
marked stale rather than quietly kept.

**Every figure is quoted with the instrument that produced it.** Parsers, gates and thresholds carry
version numbers, a tool refuses to pass when one changes without being recorded, and the design record
holds the *measurement* that decided each choice rather than the reasoning that sounded good.

## The six stages

| | what it does | writes |
|---|---|---|
| **1 discover** | two independent channels — keyword search and citations — find candidates | `candidates.jsonl` |
| **2 acquire** | obtains the best legal copy, recording every attempt and why it failed | `acquisitions.jsonl`, `raw/` |
| **3 normalize** | PDFs and HTML into one document shape, then into chunks | `documents.jsonl`, `chunks.jsonl` |
| **4 extract** | a model proposes claims; a gate verifies each against its quote | `claims.jsonl`, `rejections.jsonl` |
| **5 review** | a **different** model reads each claim against its whole passage | `reviews.jsonl` |
| **6 synthesize** | an evidence profile per question. No model, no network, no statistics | `profiles.jsonl` |
| *adjudicate* | *a person records the verdict and signs it* | `adjudications.jsonl` |

Stages talk to each other through append-only JSONL files. Nothing holds state in memory between them, a
crash is resumable, and every figure is greppable.

## Running it

```bash
.venv/bin/pytest -q                                    # 1026 passing
.venv/bin/claimstone validate --all-projects           # the contract check
.venv/bin/claimstone report projects/<name>            # the acquisition rate and its losses
.venv/bin/claimstone verdicts projects/<name>          # the profiles, and any signature
```

For the local Docker Compose trial of the portal, GROBID and the authorized-work
scheduler, see [the trial runbook](docs/LOCAL_COMPOSE_TRIAL.md).

`normalize` needs the document parser, which runs in a container: use `./claimstone.sh normalize
projects/<name>` for that one. Scholarly APIs require a contact address and the code refuses to guess one,
so `.env` must hold `CLAIMSTONE_CONTACT_EMAIL`.

## Where to read more

- **[docs/README.md](docs/README.md)** — the documentation map: which file answers which question.
- **[docs/GUIDE.md](docs/GUIDE.md)** — a walkthrough of a whole round, stage by stage, with what each
  number means. Start here if you want to run one.
- **[docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md)** — dated decisions, each with the measurement that
  decided it. Read the entry before arguing with the choice.
- **[docs/HANDOFF.md](docs/HANDOFF.md)** — what is running now, what is pending, and which decisions belong
  to a person rather than to the engine.
- **[CLAUDE.md](CLAUDE.md)** / **[AGENTS.md](AGENTS.md)** — the rules an agent working here must follow.

## Status

The scheduler has bounded operations for scoped stages, model calls, one
scholarly query and one candidate acquisition at a time. A local mandate can
advance authorized work through the research stages and propose network
batches. An operator can approve exact batches through the authenticated
control service or approve a finite, revocable schedule of already frozen
batches. A finite schedule can prepare dated research rounds; a separately
approved copy policy lets the worker acquire matching future candidates on
exact hosts under lifetime caps. See [the scheduler contract](docs/contracts/scheduler_operations.md)
for current limits.

For one flow, `scheduler auto-enable PROJECT FLOW_ID --extract-model MODEL_A
--review-model MODEL_B --max-total-local-calls N` records a bounded local-work
mandate. `scheduler auto-worker PROJECT MANDATE_ID` revisits that flow after new
data arrives; `auto-status`, `auto-once` and `auto-disable` inspect, run one pass
and stop it. The total local-call allowance survives worker restarts. Network
operations still need separate exact-plan authorization.
Optional `--discover-api`, `--discover-host` and `--acquire-host` settings let
that worker prepare the next bounded batches; `auto-status` shows those still
awaiting approval. Preparing a batch makes no network request.
The authenticated control API can list and authorize one frozen batch in a
single action; the worker remains responsible for execution.

All six stages are implemented and one round has run end to end on literature deposited in PubMed
Central: 37 of 40 sources confirmed against a floor of 0.80, 1,721 accepted annotations and 271 rejections.

**No verdict exists. Q04 is formally complete and ready for human reading; the other seven profiles
remain provisional.** D52 completes all 734 effect readings and 42 independent full-result Q04 reviews.
Four results from four of 37 examined sources remain in its current v5 profile. Human reading must
assess their scientific relevance and assigned stances; formal completeness does not certify those.
The remaining corpus workload is 24 unanswered readings and 1,679 independent-review calls.

D48 closes all fifteen software findings; D49 applies offline replay; D50/D51 prepare bounded cloud
continuation and preserve partial success. D52 records the completed Q04 run and its reading packet.
`docs/HANDOFF.md` holds the current hash, scope, budget and human decision still pending.

Two other corpora stand below their floor and correctly produce nothing. Read `docs/HANDOFF.md` for what
that means and what would change it — and note that what closed the first round was changing the
*population*, declared in advance, rather than lowering the bar.
