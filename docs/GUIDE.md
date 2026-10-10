# A round, end to end

What each stage does, what it writes, and what the numbers mean. *In italiano: [GUIDE.it.md](GUIDE.it.md).*

Worked against the round that closed on 2026-09-28 — `pmc-screen-time`, 40 sources — so every figure here is
one this repository actually produced.

## Before anything

A project is three input files under `projects/<name>/`, and the engine holds no domain knowledge about any
of them:

- **`topics.yaml`** — what to search for.
- **`questions.yaml`** — the frozen registry. Each question has an id, a text and a `kind` (`effect`,
  `heterogeneity`, `method`, `premise`, `operational`), and `kind` decides which rule judges it. Adding or
  changing a question is a **dated version bump**: the registry carries a digest of ids, texts and kinds, and
  every command that opens a store refuses to run if the digest moved under an unchanged version. Without
  that, every round-over-round comparison silently compares two different registries.
- **`sources.yaml`** — the admissible source classes, the acquisition floor with the date and reason it was
  set, the hosts never to route through, and any vocabulary this field needs (see stage 4).

```bash
.venv/bin/claimstone validate projects/<name>
```

This checks the contract and nothing else. It is cheap and it is the first thing to run after any edit.

## 1 · discover — candidates, from two independent channels

```bash
.venv/bin/claimstone discover projects/<name> --round <round-name>
.venv/bin/claimstone discover-report projects/<name>
```

Two channels: **keyword** (OpenAlex, Crossref, arXiv) and **citation** (the reference lists stage 3
extracted). Keep their results separate: citations can expose works keyword search missed. Neither
their overlap nor an acquisition percentage establishes literature completeness. D10 records why
capture-recapture assumptions fail here; `discover-report` deliberately gives no completeness percentage.

Every candidate records the query that found it and the channel it came through. A curated reading list
enters instead through `import-manifest`, which is how a corpus someone chose by hand becomes a round.

**Rounds matter.** The floor is judged per round, because a discovery sweep changes the denominator by
design: one citation sweep took a corpus from 14/25 = 0.56 to 14/75 = 0.19, and only the first compares like
with like.

If discovery needs a restricted metadata population, declare `population` in `sources.yaml` before
the first candidate of that round. It requires a positive `version`, ISO `declared_at`, `rationale`
and at least one of `hosts`, `source_apis` or `venues`. Host and venue matches are exact; there are
no domain wildcards. The predicates are alternatives and never depend on acquisition success.
The declared manifest seed remains included. Both accepted and excluded discovery observations
are preserved in `discovery_population.jsonl`; only accepted ones enter `candidates.jsonl`.
The policy is frozen in `populations.jsonl`: changing or removing it requires a new round (D54).

## 2 · acquire — the best legal copy, and every attempt recorded

```bash
.venv/bin/claimstone acquire projects/<name> --round <round-name> --campaign <why>
.venv/bin/claimstone report projects/<name>
```

For each candidate, the resolver builds a cascade of places a copy might legally live — Unpaywall's
locations, OpenAlex's, a PubMed Central address where one exists, the candidate's own URL last. Each is
tried in turn; the bytes are stored content-addressed; **every attempt is written down whether it worked or
not**, because a swallowed failure inflates the rate that decides whether this round may conclude anything.

The conduct rules are not optional: `robots.txt` is honoured, a host that returned 403 is not asked again
outside a **named campaign**, and no request is ever routed through a shadow library.

`report` is the figure that matters:

```
  ACA            37/40 confirmed  0.93   floor 0.80
  obtained       38/40  0.95
  confirmed      37/40  0.93  <- the figure
  floor          0.80 (v1, 2026-09-27)   OK   basis: confirmed
  failures       BOT_CHALLENGE 2
```

Read it in this order. **`confirmed` is the figure, not `obtained`** — a 200 response carrying a landing page
is not a document, and the difference between the two lines is how much of what arrived was real. The floor
line says `OK` or `INSUFFICIENT_ACQUISITION`, and in the second case no later stage will conclude anything.
`failures` is grouped by cause, and a cause that names *our* limitation (`BOT_CHALLENGE`) is deliberately
distinct from one that names the source's (`ABSTRACT_ONLY`): recording a CAPTCHA as "only an abstract exists"
would be an infrastructure failure written into the record as a fact about the literature.

`gate-audit` sweeps the thresholds that produced the rate, because a rate quoted without its thresholds
invites comparing two incomparable numbers.

## 3 · normalize — one document shape, then chunks

```bash
./claimstone.sh normalize projects/<name>          # needs the container: see below
```

PDFs go through GROBID; HTML through a parser in this repository. Both produce the *same* document shape, so
nothing downstream knows or cares which parsed it. Tables are extracted rather than flattened — a bare `4.2`
dropped next to unrelated prose is a number a model will attribute to whatever sentence precedes it.

Then a confirmation rule: a document is real if it has enough references, or is long enough to stand without
a reference list. What fails is `NOT_A_DOCUMENT` and leaves the corpus count honest.

**This is the one stage that needs the container**, because GROBID sits on an internal network with no
published port. `./claimstone.sh` builds the image first and then runs the same CLI inside it — the image
carries the code, and `compose.yaml` mounts only `store/` and `projects/`.

## 4 · extract — a model proposes, a gate verifies

```bash
.venv/bin/claimstone extract projects/<name> --batch <name>              # build the work units
.venv/bin/claimstone model-run projects/<name> extract --batch <name> \
    --backend ollama-cloud --model <model> --no-think --enforce-schema    # drain them
.venv/bin/claimstone extract projects/<name> --batch <name> --harvest     # gate the answers
.venv/bin/claimstone extract-report projects/<name> --show-rejected
```

Three separate commands on purpose. The work units are JSONL, the answers are JSONL, and the model never
sits inside a stage — so a batch is resumable by `call_id`, a backend is swappable, and the same units can be
sent to two backends and compared.

What the model is asked for depends on the question's `kind`: an `effect` question wants a study result with
its estimand, `heterogeneity` wants the contrast between subgroups and its uncertainty, `method` wants
whether the source endorses a practice or demonstrates its failure. The model reports figures **only as the
paper wrote them** — `2.4%`, `(0.008)`, `AOR=1.66` — and the engine converts. That way a value cannot be
wrong in a way its quote could not reveal.

Then the gate, which is invariant 1 made executable. It checks that the quote is an exact substring of the
chunk, that every numeral the claim asserts appears in the quote, that a comparative in the claim is in the
quote too, and that the claim is not reporting what some *other* paper found. What fails is written to
`rejections.jsonl` with the whole record, so a rejection is examinable rather than merely counted.

**A discipline's notation is project data.** `AOR`, `ß`, `Sharpe`, `95% CI` are declared in that project's
`extraction.value_labels`. They used to live in the engine, and a corpus in another field proved that was
wrong: the list shipped with `sharpe` and without `OR`, so the finance corpus parsed and the epidemiology
corpus refused 63 estimates.

## 5 · review — a different model, reading the whole passage

```bash
.venv/bin/claimstone review projects/<name> --batch <b> --question <Q> \
    --reviewer claude-cli/claude-opus-5
.venv/bin/claimstone model-run projects/<name> review --batch <b> --backend claude-cli --model …
.venv/bin/claimstone review projects/<name> --batch <b> --harvest
```

The reviewer gets the question, the complete original and converted annotation, **and the whole chunk** — and must be a different model
from the one that extracted, which is enforced rather than requested. A reader sharing the extractor's blind
spots is a second opinion from the same opinion.

Four verdicts: `SUPPORTED`, `OVERSTATED` (the quote is real and says less than the claim), `AMBIGUOUS`, and
`NOT_APPLICABLE` (the quote does not speak to the question cited). Only `SUPPORTED` claims reach a profile;
the rest are counted and shown, never deleted — an `OVERSTATED` row is the most informative row in the
ledger, because it is a case a mechanical check passed and a reader would not.

`--question` exists because a verdict is per question, and one adjudicable profile costs 43 review calls
rather than the whole ledger's 7,000.

**What this stage measures, which surprised us.** On two questions of two different kinds, the reviewer
marked 23 of 41 and 36 of 42 gate-passed claims `NOT_APPLICABLE` — they do not speak to the question they
cite, though all of them passed the gate's kind check. Every chunk is asked about every question of its kind
and the model answers rather than declining. So **coverage measured after extraction is a statement about
the extractor**, and honest coverage is post-review.

## 6 · synthesize — a profile, and never a verdict

```bash
.venv/bin/claimstone synthesize projects/<name>
.venv/bin/claimstone verdicts projects/<name> --question <Q>
```

Deterministic Python. No model, no network, **no statistics** — the verdict contract's rules are counting and
coverage rules, so a pooled estimate would be extra information and the basis of no verdict they define.

It refuses twice. A round below its floor gets **no profiles at all**, not a warning and not a partial run.
And a profile built while anything is still arriving is marked `provisional` and cannot be signed, because a
judgement recorded against evidence that was still changing is a judgement about something else.

A profile holds every verified result with its estimand, the same fields for results that **disagree**, the
direction count *labelled a count*, the coverage, what the gate rejected by reason, what the reviewer would
not pass, and the sample labels verbatim with linkage declared **unestablished** — no string comparison
establishes that two papers used different datasets.

Its one categorical output is `NO_VERIFIED_CLAIM`, which says nothing survived. That is **not**
`NEVER_ASKED`: an extraction miss, an all-rejected question and a genuinely unasked one look identical from
here, and only screening tells them apart.

D45 made completeness explicit: a terminal model failure is not a reading with zero claims, so the profile reports
`extraction.expected`, `unanswered`, `unharvested` and `unchunked_sources`. When D45 was written, 34 readings of the saved
round had no valid answer, 10 of them effect readings that kept Q04 provisional. D52 then completed all 734 Q04 effect
readings, and `verdicts` now shows 0 unanswered for Q04.

Use the same `--round` and `--manifest-only` on `synthesize`, `verdicts` and `adjudicate`; the scope is
hashed and its profiles and signatures are kept separate. `verdicts` recomputes in memory without
appending; if the saved profile differs, run `synthesize` and read the new hash before signing.

D46 adds `extraction.unregated` and `awaiting_regate`: annotations admitted by an older claim gate
cannot be signed under the current one until re-harvested. Gate revisions now supersede either outcome
across both ledgers. D47 repairs answer/annotation replay (R05/R09). A full offline replay can be measured with
`tools/measure_answer_replay.py <project>`. D48 repairs chunk generations and full-result review too. D49 applies that replay to the real ledgers, preserving every original byte; all old
reviews attest task v1 and cannot certify v2 complete annotations. Unanswered
readings and independent complete review precede rebuilding and reading a signable v5 profile.

## adjudicate — the only place a verdict comes from

```bash
.venv/bin/claimstone adjudicate projects/<name> <Q> \
    --verdict SUPPORTED|CONTRADICTED|CONTESTED_IN_LITERATURE|UNANSWERED_IN_LITERATURE|NEVER_ASKED \
    --rationale-file r.md --by "<who>" --profile-sha256 <hash>
```

A person reads the profile and signs. The signature records the hash of what they were shown, so if the
evidence changes the verdict is displayed as **stale** with both hashes rather than quietly kept — a
judgement made against different evidence is a judgement about a different question.

It refuses a provisional profile, refuses a rationale under 120 characters, and refuses a question of kind
`operational`, which receives a row saying no verdict applies rather than a sixth state.

**Five states, and none collapses into another.** `UNANSWERED_IN_LITERATURE` means the corpus was read and
does not settle it. `CONTESTED_IN_LITERATURE` means the literature speaks and disagrees. Reporting the second
as the first is the project's founding error one category over.

## Re-judging without the network

Four paths cost nothing and re-read what is already on disk. Use them instead of re-fetching:

| | re-reads |
|---|---|
| `regate --campaign <why>` | stored bytes under the current content gate |
| `normalize --force` | chunks, from what is already parsed |
| `extract --harvest` | stored answers under the current claim gate |
| `model-run --rejudge` | stored answers under the current rules, no call |

The ledgers are append-only, so a re-run appends and `latest_by` takes the last. Nothing is lost and nothing
is rewritten.

## The one rule about numbers

**Quote what a re-judgement returns, never what a sample suggests.** In one day, four predicted recoveries
from counting a defect's signature in a small sample were 45→1, 166→18, 6→1, and one hypothesis falsified
outright. Run the re-harvest and quote its output.


The reproducible operational command is `tools/replay_answers.py <project>` for read-only workload
measurement, or with `--apply` for stored-answer replay. Scope flags select the measurement; replay
always processes every stored batch. See [the production measurement](replays/2026-09-28-production-replay.md).

## Testing a prompt before adoption

For a prepared comparison plan, preview without network calls or writes:

```bash
.venv/bin/python tools/run_prompt_comparison.py --plan <comparison-plan.json>
```

With explicit calibration spending authorization, add `--execute` to run or resume. The comparison
uses a separate experimental store and the original cumulative budget, including earlier failed
calls with unknown costs. It keeps the production prompts and scientific ledgers unchanged.
It compares diagnostic reference cases, rereads the original sample with an experimental extraction
prompt, and independently reviews every newly accepted annotation. Successful calls are retained
on resume. BACKEND_ERROR stops after the attempted call and preserves its accounting reservation.

The paired diagnostic labels describe a provisional agent-authored development reference selected
after inspecting errors. They are not general accuracy, and positive controls must be examined
alongside problematic cases. Read new annotations and their supporting passages before deciding
whether to adopt a prompt. No variant is adopted automatically, and this tool produces no profile
or signed verdict.

For a prepared reviewer-only diagnostic plan, use:

```bash
.venv/bin/python tools/run_review_diagnostics.py --plan <diagnostic-plan.json>
```

Add `--execute` only within the existing spending authorization. This task holds annotations and
passages fixed and asks for separate applicability, fidelity and direction labels with reasons.
The queue is isolated and the cumulative budget includes both earlier experiments. It runs no
extraction and writes no production reviews. The report's summary label is experimental; its
uncertainty mapping does not change production review states. Expected reference axes left
unscored stay out of agreement denominators. Evaluate reasons and positive controls before adopting
any new scientific review task; successful JSON alone does not validate that task.

An invalid output shape remains SCHEMA_INVALID even if its prose looks useful. A format repair
uses an explicitly versioned prompt and new request ids rather than rewriting the failed response.
Its prepared plan freezes the previous diagnostic queue and carries every failed attempt forward
into the same cumulative budget. Use the repaired plan supplied by the operator workflow; a
terminal-invalid original answer cannot become complete merely by rerunning the original plan.

To compare an independent reviewer on a completed diagnostic task, use its prepared plan:

```bash
.venv/bin/python tools/compare_reviewers.py --plan <reviewer-comparison-plan.json>
```

Adding `--execute` runs only the second reviewer in another isolated store. Requests are byte-identical
to the completed baseline, including prompts, annotations, passages, schema, output caps and merged
annotation targets. The baseline answers and development reference are never sent to the new reader.
Earlier priced attempts and unknown-cost reservations retain their original readers' rates and
context bounds. Each next call must fit inside the original cumulative budget before contact.
The report pairs both readers' checks and reasons with the provisional reference, separating positive
controls from challenge cases. Inter-reader agreement and reference agreement are different measures;
neither certifies scientific accuracy. This comparison cannot adopt a task or write production reviews.

## A first supervised use

A curated passage plan can produce a consultative reading dossier without model calls:

```bash
.venv/bin/python tools/build_consultative_dossier.py --plan <curated-passage-plan.json>
```

Preview is read-only. `--write` creates content-addressed JSON and Markdown under the source store's
`audits/consultative/`, retaining all original files. The plan pins the registry, current passage text
and normalized document hashes. Every curated record must pass the existing claim gate; the source
class remains attached. The acquisition floor still blocks publication, and incomplete admission is
reported even above the floor. These documents are selected reading notes, not scientific profiles:
they neither harvest claims/reviews nor sign a verdict or certify semantic accuracy. Interactive
curation is named explicitly and must not be reported as a batch backend's extraction measurement.
The selection and missing coverage must accompany the interpretation. Cases already inspected for
this dossier are development material, not unseen validation of a tuned prompt.

## Search coverage and updates

An acquisition rate measures documents confirmed out of candidates found, not the share of the
literature discovered. Completing a finite search protocol also does not establish universal recall.
Record the question, admissible population, search terms, APIs, result limits and search dates before
searching. `tools/audit_research_search.py --plan <search-plan.json>` compares that frozen query
matrix against recorded queries offline. Missing queries, failed queries and insufficient search
depth remain distinct. A query reaching its result cap needs inspection or a deeper follow-up;
successful execution alone does not mean its result set was exhausted.

`--write` saves a content-addressed baseline under `audits/research-search/`. It lists candidates,
document hashes/generations, bibliography references still needing relevance screening, current
reading completion and question-specific review labels. No semantic screening is inferred from
titles, source counts, acquisition or the presence of claims. Literature recall and screening
precision stay unknown until separately justified; no scientific ledger or verdict is written.

For effectiveness, record relevance decisions and reasons for every screened work, identify
eligible known papers the search should recover, and inspect opposing/null findings as well as
positive ones. Recovery of these known papers is a benchmark check, not total-literature recall.
Track new relevant works per completed search wave and what citations add beyond keywords.
Low yield supports stopping a declared protocol only after search failures, capped results and
unscreened references are accounted for. It does not prove saturation of all literature. The
default citation threshold misses singly cited references; a focused bibliographic review must
inspect those too. Relevance screening never retroactively removes admitted candidates from the
acquisition denominator.

For updates, use a dated new discovery round and retain an audit of the previous cumulative corpus.
`--previous <baseline-audit.json>` reports new candidate keys and changed document generations;
candidate keys are not independently deduplicated studies, so possible duplicates require inspection.
An unchanged byte/prompt/schema combination can reuse existing work. A revised paper or parser
generation needs current readings; changed annotations need new independent reviews. Historical
evidence and signatures remain recorded, and changed live evidence makes an old signature stale.
Keep both the update-round acquisition report and the cumulative one: candidates belong to the
round that first found them, so the update round alone is not the whole updated corpus. Population
changes require a new dated policy and round; question changes require a registry bump. Existing
commands do not provide an automatic publication watch. Initially run an explicit weekly update;
indexing delays mean newly discovered is not necessarily newly published.

For OpenAlex recovery, an optional free `OPENALEX_API_KEY` in `.env` is passed into the container
and sent as an Authorization header only to its exact HTTPS API origin. Never put it into a query
URL or a committed input. A key increases the provider's anonymous budget but does not remove
daily limits. `tools/resume_research_search.py --plan <search-plan.json> --limit <N>` previews only
missing, failed or insufficient-depth queries from a frozen protocol. With `--execute` on the host,
it reads contact and keys safely from `.env`, shares one fetcher across the selected queries and
stops at the first failure. Completed queries, including capped ones, are skipped: deeper search
requires an explicit follow-up protocol. Default limit is one query; it launches no model calls.

## The scheduler: bounded operations (not finished)

This part of the engine is still being completed, so it comes last. What follows is what exists today. It does not open a
new research round, approve unknown future requests or sign a verdict. Current limits are in
[the scheduler contract](contracts/scheduler_operations.md).

For a bound research flow, `claimstone scheduler-preview PROJECT FLOW_ID`
prints an offline, read-only proposal of next work. It does not authorize or
start a stage. It names protocol/integrity blockers and keeps an empty new
round distinct from a closed candidate cohort (D86).

An existing flow can also run one bounded offline stage through the operation
ledger. For example, after candidates and acquired copies exist:

```bash
.venv/bin/claimstone scheduler plan projects/<name> <flow-id> normalize
.venv/bin/claimstone scheduler authorize projects/<name> <operation-id>
.venv/bin/claimstone scheduler run projects/<name> <operation-id>
.venv/bin/claimstone scheduler status projects/<name> <operation-id>
```

Use `extract-build --batch <name>` or `review-build --batch <name>
--reviewer <backend>/<model>` for scoped queue construction. A local model
queue can be drained with `extract-drain` or `review-drain` plus `--batch`,
`--model` and `--max-calls`; then plan the matching `extract-harvest` or
`review-harvest`. `synthesize` builds a profile. The operator authorizes each
exact plan from the local OS account. These operations permit no external
internet requests except an explicitly planned single-candidate `acquire`
with `--candidate-key`, repeatable `--allow-host` and `--max-requests`.
A `discover` plan instead names `--api`, `--topic`, `--term`, `--per-query`,
`--allow-host` and `--max-requests`; it runs one frozen query per authorization.
For a metered drain, add `--backend ollama-cloud`, `--budget-id`,
`--budget-cents`, `--max-call-cents`, `--price-in-cents` and
`--price-out-cents`. Prices are declared upper estimates in USD cents per
million tokens, and reservations are cumulative across plans with the same
budget ID. Review the exact plan and authorize it before a worker may call the
provider. Credits in an account alone grant no authorization. A provider bill
can exceed a local estimate; use the provider's account spending controls as
the external hard cap. Interrupted calls with uncertain billing stop for
inspection rather than being sent again.
After a failed offline operation, use a new `--run-label` once the cause is
resolved. An uncertain physical request blocks automatic retry even with a
new label.
For a query that failed before any physical request, a new discovery plan may
name `--run-label` and `--retry-reason`. It binds the prior failure row and
still requires a separate operator authorization before execution.

For several query or candidate plans, `scheduler batch-plan` accepts explicit
APIs/hosts, `--max-units` and `--max-requests-each`, and prints one batch ID
with the total ceiling and skipped items. Review that JSON, then run
`scheduler authorize-batch PROJECT BATCH_ID`. `scheduler tick PROJECT` runs a
bounded number of approved operations once; `scheduler worker PROJECT` polls
for further approved operations. The worker does not approve new work.
For a single unattended local pass after collection, run `scheduler drive
PROJECT FLOW_ID --extract-model MODEL_A --review-model MODEL_B
--max-local-calls N`. It stops at the network, acquisition-floor or human
reading gate; it cannot sign a verdict. Run it inside `./claimstone.sh` if
PDF normalization needs the internal GROBID service.
The same invocation first runs any network units for that flow that were
already authorized when it started; it never expands their host lists or
ceilings.

To prepare a finite series of dated update rounds offline, write a JSON array
such as `[ {"round":"update-2026-11", "title":"November update",
"not_before":"2026-11-01T00:00:00Z", "expires_at":"2026-11-02T00:00:00Z"} ]`.
Then use `scheduler periodic-plan PROJECT SOURCE_FLOW_ID --rounds-file FILE
--api crossref --allow-host api.crossref.org --max-units-each N
--max-requests-each N`. The per-round unit cap must fit *all* topic terms for
the selected APIs. This creates new flow bindings and exact discovery batches,
but makes no request. Inspect the returned schedule ID and its batches, then
authorize that finite schedule with `scheduler schedule-authorize PROJECT ID`.
`scheduler periodic-audit PROJECT ID` reports each round's query outcomes and
acquisition floor, ancestor flow admission and whole-corpus admission. It never issues a verdict. A
new candidate still needs a separately authorized acquisition plan; scheduling
discovery does not preapprove unknown future copies. For a bounded allowance
covering later copies, use `scheduler copy-policy-plan PROJECT SCHEDULE_ID
--allow-host HOST --source-class CLASS --max-candidates N
--max-requests-each N --not-before UTC --expires-at UTC`, inspect the policy,
then run `copy-policy-authorize PROJECT POLICY_ID`. The worker prepares exact
candidate acquisitions when matching scheduled search hits arrive.
`copy-policy-status` shows permanent reservations; `copy-policy-revoke` stops
future starts. Unknown hosts and classes remain outside the allowance.
