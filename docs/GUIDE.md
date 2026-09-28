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
extracted). They are kept separate because completeness is estimated by comparing two *independent* channels
— counting what one channel found says nothing about what is missing.

Every candidate records the query that found it and the channel it came through. A curated reading list
enters instead through `import-manifest`, which is how a corpus someone chose by hand becomes a round.

**Rounds matter.** The floor is judged per round, because a discovery sweep changes the denominator by
design: one citation sweep took a corpus from 14/25 = 0.56 to 14/75 = 0.19, and only the first compares like
with like.

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
  ACA            38/40  0.95   floor 0.80
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

The reviewer gets the question, the claim, the quote, **and the whole chunk** — and must be a different model
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

D45 corrected the saved round's completeness: 34 extraction readings have no valid answer, including
10 effect readings that keep Q04 provisional. A terminal model failure is not a reading with zero claims.
The profile reports `extraction.expected`, `unanswered`, `unharvested` and `unchunked_sources`.

Use the same `--round` and `--manifest-only` on `synthesize`, `verdicts` and `adjudicate`; the scope is
hashed and its profiles and signatures are kept separate. `verdicts` recomputes in memory without
appending; if the saved profile differs, run `synthesize` and read the new hash before signing.

D46 adds `extraction.unregated` and `awaiting_regate`: annotations admitted by an older claim gate
cannot be signed under the current one until re-harvested. Gate revisions now supersede either outcome
across both ledgers. D47 repairs answer/annotation replay (R05/R09). A full offline replay can be measured with
`tools/measure_answer_replay.py <project>`. D48 repairs chunk generations and full-result review too. The real ledgers remain unchanged; all old
reviews attest task v1 and cannot certify v2 complete annotations. Production offline replay, unanswered
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
