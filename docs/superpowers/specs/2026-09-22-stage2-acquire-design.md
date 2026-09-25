# Stage 2 — acquire: design

Date: 2026-09-22 · Scope: stage 2 only · Status: approved, not implemented

Stage 2 turns candidates into frozen texts and accounts for every attempt. It is the first
milestone because acquisition, not extraction quality, is the binding constraint on the
science (D8) — and since D13 it is the only remaining one. The deliverable is a sentence with
a number in it: the acquisition rate on a 25-source manifest that currently stands at 0.42,
with OA status, licence and failure reason recorded per source, **plus the sensitivity of that
rate to the gate thresholds that produced it** (§5) and a by-hand check of every rejection.

Landing below the declared floor is a legitimate outcome of that deliverable, not a failure of
it (see "The floor is versioned" in §8).

## 1. Starting point

`claimstone/acquire.py` and `claimstone/discover.py` already exist as untracked drafts. They
carry a working cascade (arXiv → candidate URL → Unpaywall → OpenAlex → known wall last),
a DOI-from-title resolver, an idempotent `run()` and a `rate()` function.

This document is **normative**: it states the required behaviour independently, and the
drafts are checked against it. Where they diverge, the drafts change. Three divergences are
already known and are recorded in §9.

## 2. Module boundaries

| Module | Status | Responsibility |
|---|---|---|
| `net.py` | exists | HTTP, robots, per-domain failure budget. Gains new failure classes. |
| `resolve.py` | new | candidate → ordered `[Location]`. Pure; the fetcher is injected. |
| `fulltext.py` | new | bytes → verdict on the content. No network, no state. |
| `acquire.py` | rewritten | orchestration: plan → attempt → gate → store → ledger row. |
| `admissibility.py` | new | rate, per-class breakdown, comparison against the floor. |
| `gate_audit.py` | new | re-runs the gate over stored bytes at varying thresholds. No network. |

`resolve.py` and `fulltext.py` are formed by extracting what currently sits in the draft
`acquire.py`. The work already done moves; it is not discarded.

The fetcher enters every function as a parameter satisfying a `Protocol` declared in
`net.py` (`get(url, *, expect) -> Outcome`, `get_json(url) -> (dict | None, Outcome)`).
This is what lets the whole stage be tested offline against a `FakeFetcher`.

## 3. The cascade (`resolve.py`)

`plan(fetcher, candidate, *, use_apis=True) -> (list[Location], oa_status)`

Order, cheapest and most likely first:

1. **arXiv id** found in the candidate URL or title → `https://arxiv.org/pdf/<id>`. A
   guaranteed legal full text; tried before anything else.
2. **The candidate URL**, unless its host is in `KNOWN_WALLS`.
3. **DOI resolution when no DOI is present**: OpenAlex title search, accepted only on exact
   normalised-title equality. Publisher URLs often carry an internal identifier (a
   ScienceDirect PII, an SSRN abstract id), so without this step no open-access lookup is
   attempted at all and the source is recorded as paywalled while a legal copy exists.
4. **Unpaywall** locations for the DOI; **OpenAlex** locations only if Unpaywall returned
   none.
5. **Wayback Machine** for candidates with no DOI and no arXiv id — see §4.
6. **The candidate URL on a known wall**, last: better a landing page than nothing, but
   only after every legal open copy has been tried.

Locations are then sorted by version rank (`publishedVersion` < `acceptedVersion` <
`submittedVersion` < unknown) and deduplicated on `ids.normalize_url`.

A shadow library is never a location. `excluded_hosts` from `sources.yaml` is enforced in
`net.Fetcher` before any request and yields `EXCLUDED_HOST`.

## 4. Sources without a DOI

`NEW`, `IND` and `DOC` classes have no DOI and no open-access infrastructure. Their cascade
is: direct URL → if that fails or the gate rejects it, the Wayback Machine availability API
(`https://archive.org/wayback/available?url=…&timestamp=…`), then the returned snapshot.
A miss is `WAYBACK_MISS`.

For these, `licence` is recorded as `"unknown"` and `oa_status` as `null` — recorded
explicitly rather than left absent, so "we did not know" is distinguishable from "nobody
wrote it down".

## 5. The byte gate (`fulltext.py`)

`classify(body, content_type, url, thresholds) -> FullText(kind, chars, reason)`

`kind` is one of `PDF_FULLTEXT`, `HTML_FULLTEXT`, `LANDING_PAGE_ONLY`, `ABSTRACT_ONLY`,
`TOO_SHORT`, `CORRUPT_PDF`, `NOT_TEXT`. Only the first two count as acquired.

**Why this exists.** The draft counts any HTTP 200 with an acceptable content type as a
success. A ScienceDirect landing page answers 200 `text/html`. Without this gate the
acquisition rate inflates in exactly the way the project exists to prevent (invariant 3).

### PDF

No PDF parser is available at this stage: the dependency set is `requests`, `PyYAML`,
`numpy`, and GROBID belongs to stage 3. The check is therefore structural:

| condition | verdict |
|---|---|
| no `%PDF-` magic within the first 1024 bytes | `NOT_TEXT` — it is not a PDF at all, typically an error page |
| magic present, no `%%EOF` | `CORRUPT_PDF` — a truncated download |
| magic and `%%EOF`, size < `min_pdf_bytes` (default 10000) | `TOO_SHORT` |
| otherwise | `PDF_FULLTEXT` |

The threshold is deliberately low: a short conference note can be a legitimate 12 KB PDF,
and a false `TOO_SHORT` removes a real source from the numerator. The cases this gate is
actually for — an HTML error page and a truncated transfer — are caught by the first two
rows, not by size.

This catches the real pathological case — an HTML error page served as
`Content-Type: application/pdf` — and defers confirmation that text is extractable to stage
3. **This is deliberately weaker than the HTML gate** and is recorded here so it is an
explicit decision rather than a discovery downstream. Stage 3 will write back a
`fulltext_confirmed` signal; until it exists, a structurally valid PDF counts as acquired.

**Measured, 2026-09-24.** That weakness cost exactly one source in 25 on the first corpus:
`IND008`, a vendor fact-sheet PDF with 4,618 characters of body and no references, which this
gate cannot tell from a paper. Reaching a character count needs the parser that does not exist
before stage 3, so the gate stays structural and the rate it produces is an **upper bound** until
stage 3 confirms extractable structure. Recorded under D8.

### HTML / XML

XML is treated identically to HTML here; structured parsing belongs to stage 3.
Visible text is extracted with the stdlib `html.parser`, dropping `<script>`, `<style>`,
`<nav>`, `<header>`, `<footer>` and `<aside>`. Then:

Checked in this order, and the order carries a decision:

| condition | verdict |
|---|---|
| a paywall phrase is present and `chars < paywall_doubt_chars` (12000) | `LANDING_PAGE_ONLY` |
| no structural signal and `chars < fulltext_chars` (15000) | `ABSTRACT_ONLY` |
| `chars < min_text_chars` (3000), but it does cite | `TOO_SHORT` |
| otherwise | `HTML_FULLTEXT` |

The structural check comes **before** the length check on purpose. A 2473-character summary page
is both short and a summary, and `ABSTRACT_ONLY` is the more useful of the two labels: it says a
full text may exist elsewhere and is worth another attempt, where `TOO_SHORT` says the document
itself is thin. `TOO_SHORT` therefore ends up meaning something precise — a document that *does*
cite and is still tiny, which is a truncation, not a summary.

Paywall phrases (`get access`, `purchase pdf`, `buy article`, `rent this article`,
`sign in to continue`, `institutional access`, `add to cart`, `subscribe to continue`,
`you do not have access`) are matched case-folded against the extracted text. **A phrase
alone is never sufficient**: a legitimate open-access article also contains "sign in".

A **structural signal** is a reference list — a heading matching `references`,
`bibliography` or `works cited`, or ten or more citation-shaped patterns. A document that
argues from evidence cites; a page that summarises one does not.

### Why `ABSTRACT_ONLY` exists — measured, 2026-09-22

The rule above was length-only in the first draft of this spec. Running that draft's gate over
the 25 artifacts a real round had already stored showed why length is the wrong instrument.

Six of the 25 came back as HTML. Four were `ravenpack.com/research/…` pages, one an LSEG
product page, one a MarketPsych overview. **All six are abstract or product pages; none is a
full text.** The length-only rule accepted three of them (5981, 4820 and 4190 characters) and
rejected two (2526 and 2473) — *the same kind of page, opposite verdicts, decided by how much
prose the summary happened to contain.* Raising `min_text_chars` would not have fixed it: one of
the six runs to 9243 characters, so any threshold that caught it would have thrown away
legitimate short documents.

The revised rule was then run over the same 25 artifacts: **12 `PDF_FULLTEXT`, 6
`ABSTRACT_ONLY`, nothing else** — every HTML artifact recognised, no PDF disturbed.

What does separate them, checked on those same bytes: **none of the six contains a reference
list, and none links to a PDF.** A full text of a paper essentially always cites.

So the honest figure for that round is not the 0.72 recorded in its commit message, and not the
0.64 the length-only gate produced. With all six HTML artifacts recognised for what they are it
is **12 of 25 = 0.48** — twelve PDFs. The inflation mechanism was precisely the one this gate
exists to stop, and the first draft of the gate did not stop it.

`ABSTRACT_ONLY` is a distinct verdict rather than a flavour of `TOO_SHORT` because "we obtained
the summary page" and "the document is short" are different facts, and only the first tells you
a full text may exist elsewhere and is worth another attempt.

### The gate's language and genre assumptions are declared, not built in

Added 2026-09-24, after a review pointed out that this gate violates invariant 4. The paywall
phrases are English. So are the reference-list headings. The citation pattern is the Western
author-year convention. A corpus in another language, or one of regulatory filings that cite
nothing, could not use the gate without editing the package — which is exactly what invariant 4
forbids.

So `sources.yaml` may declare, under `gate_policy`:

| key | effect |
|---|---|
| `paywall_phrases` | replaces the English defaults entirely |
| `reference_headings` | replaces `references`, `bibliography`, `works cited` |
| `structural_signal` | `reference_list` (default) or `none` |

The same three keys may appear **under an individual class**, where they override the project's for
sources of that class.

`structural_signal: none` asks only for length, and is **weaker on purpose**: a corpus of filings or
API documentation has no bibliographies, and requiring one would reject every source of that class.

**It is declared per source class, not per project** — corrected 2026-09-25 after a review measured
the project-wide switch admitting **four of the six artifacts already established to be abstract or
product pages**. Genre is a property of the source, and a corpus holding both papers and filings
needs the reference list required for the first and not the second. `DOC` declares it in both
shipped projects; nothing else does.

The policy in force is recorded as a **hash of the whole policy** on every ledger row. An earlier
version stored only the count of paywall phrases, so two different lists of the same length were
indistinguishable and a ledger could not tell two instruments apart.

What this does **not** add is a "needs review" verdict. `gate-audit --show-rejected` already lists
every rejection for a by-hand check, which is the same function without a state that nothing
consumes.

### Recorded parameters

`gate_version` (2 — the HTML rule changed on measurement before anything shipped) and the thresholds in force are written onto every ledger row. A rate
computed under different thresholds is not comparable to one computed under these, and
without recording them the difference would be invisible. Thresholds are overridable per
project under an `acquisition:` key in `sources.yaml`; the defaults are the values above.

### Calibrating the thresholds (`gate-audit`)

The numbers above — 10000, 3000, 12000 — were chosen at a desk. Nothing measured them, and a
wrong threshold moves the headline figure silently. Two properties make that recoverable at no
network cost: the bytes are stored content-addressed under their hash, and the gate does no
I/O. **So the gate can be re-run over the whole corpus without re-fetching anything.**

This only works if the bytes survive. **A response the gate rejects therefore has its bytes
stored anyway**, and the attempt records the path. A landing page is a few hundred kilobytes
and the corpus is 25 sources; throwing those bytes away in exchange for nothing would make the
audit impossible and would also make the by-hand rejection check impossible, since there would
be nothing left to look at. Bytes are discarded only when the transfer itself failed — there
was never a body to keep.

`claimstone gate-audit <project>` does two things.

**A sensitivity sweep.** Re-classify every stored artifact across a range of one threshold and
report how the rate moves:

```
min_text_chars   1000  2000  3000  4000  5000  8000
rate             0.73  0.73  0.73  0.69  0.65  0.54
```

A rate flat around the chosen value means the threshold is not load-bearing and the number is
safe. A rate that swings means **the threshold is deciding the result**, and it has to be
looked at by hand. Which of the two we are in is measurable in a second and is currently
unknown — that is the point of running it.

**A rejection listing.** `--show-rejected` prints every rejected artifact with its character
count and the phrase that triggered it, so all of them can be checked by eye. At 25 sources
this takes about ten minutes and is **a required step of the first round**: one false positive
found here is worth more than any desk-chosen threshold, and it is the only way to learn
whether a paywall phrase is catching a legitimate open-access article.

The audit's outcome sets `gate_version: 2`, with thresholds carrying a recorded reason — the
same standard as D4 and D5. Until it has run, the rate is reported with its thresholds and
**without** the claim that those thresholds are right.

## 6. Ledger schema — `acquisitions.jsonl`

One row per candidate per campaign run, append-only. A candidate the retry policy (§7)
declines to re-attempt produces **no new row**: silence in the ledger means "not tried
this run", and the previous row stands.

```json
{"candidate_key": "doi:10.1016/j.jfineco.2019.05.001",
 "source_id": "S07", "source_class": "ACA", "campaign": "routine", "attempt_no": 2,
 "acquired": true,
 "gate": {"kind": "PDF_FULLTEXT", "chars": null, "bytes": 412839,
          "gate_version": 1,
          "thresholds": {"min_pdf_bytes": 10000, "min_text_chars": 3000,
                         "paywall_doubt_chars": 12000, "fulltext_chars": 15000}},
 "sha256": "…", "stored_path": "store/alembic-s4/raw/….pdf",
 "url": "https://…", "provenance": "unpaywall", "version": "acceptedVersion",
 "licence": "cc-by", "oa_status": "green", "host_type": "repository",
 "content_type": "application/pdf", "bytes": 412839,
 "failure_class": null,
 "attempts": [{"url": "…", "http_status": 403, "failure_class": "PAYWALL_403",
               "provenance": "candidate", "version": "", "gate_kind": null,
               "gate_reason": null, "stored_path": null,
               "content_type": "text/html", "bytes": 0, "elapsed_s": 1.2},
              {"url": "…", "http_status": 200, "failure_class": "LANDING_PAGE_ONLY",
               "provenance": "candidate", "version": "", "gate_kind": "LANDING_PAGE_ONLY",
               "gate_reason": "2840 chars and the phrase 'purchase pdf'",
               "stored_path": "store/alembic-s4/raw/….html",
               "content_type": "text/html", "bytes": 61204, "elapsed_s": 0.9}],
 "fetched_at": "2026-09-22T10:41:07+00:00"}
```

Three rules, each for a reason:

1. **`source_class` is mandatory with no default.** A candidate arriving without one makes
   `acquire` fail with an error rather than pass with an empty class. This is invariant 6
   made executable. `discover.import_manifest` sets it from the manifest; API discovery must
   set it from the venue type before its candidates are admissible to stage 2.
2. **A success is never overwritten by a later failure.** `Store.latest_by` keeps the last
   row per key; if a retry campaign re-attempts an already-obtained source and fails, the
   rate would *fall* while the bytes sit on disk. The collapse used for rate computation
   prefers the latest **successful** row per `candidate_key`, falling back to the latest row
   only when none succeeded. The draft's `rate()` does not do this.
3. **`attempts` keeps every step of the cascade**, not only the last. "Unpaywall had a
   location and it 404'd" is a different fact from "no open copy existed", and only the full
   attempt list distinguishes them. An attempt whose bytes arrived carries `gate_kind`,
   `gate_reason` and `stored_path` **whether or not the gate accepted them** — that is what
   makes the threshold audit and the by-hand rejection check possible later.

`failure_class` on a failed row is the class of the **last** attempt: it says what stopped
us. The whole history stays in `attempts`.

## 7. Retry policy and campaigns

```
TERMINAL    PAYWALL_403, ROBOTS_DISALLOWED, EXCLUDED_HOST,
            LANDING_PAGE_ONLY, NOT_FOUND_404, CORRUPT_PDF
TRANSIENT   TIMEOUT, CONNECTION_ERROR, SERVER_ERROR_5XX,
            RATE_LIMITED_429, DOMAIN_BUDGET_EXHAUSTED, WAYBACK_MISS
```

An ordinary run (`--campaign` absent, recorded as `routine`) attempts candidates with no
prior row, plus transient rows older than `retry_after_s` (default 6 hours). **It touches
nothing terminal.**

Re-attempting a terminal class requires an explicit `--retry-class PAYWALL_403`, and then
`--campaign NAME` is mandatory. The name is written on every row, so the ledger answers
"why did this round knock on Elsevier again" without reconstructing it from timestamps.
This is the named-campaign rule from CLAUDE.md made mechanical.

The per-domain budget in `net.Fetcher` is independent and sits above the campaign: a named
campaign authorises retrying, never bypassing the budget. `DOMAIN_BUDGET_EXHAUSTED` is
classified transient so the source returns to the queue on a later run instead of
disappearing from the denominator — a blocked downloader disguised as a saturated corpus is
the confound D10 exists to break.

## 8. CLI and admissibility

```
claimstone import-manifest <project> [--manifest PATH]
claimstone acquire <project> [--campaign NAME] [--retry-class CLASS ...]
                             [--limit N] [--dry-run] [--no-apis]
claimstone report <project> [--by-class] [--json] [--gate]
claimstone gate-audit <project> [--sweep NAME] [--show-rejected] [--json]
```

`serve` belongs to the dashboard and is specified in `2026-09-22-dashboard-design.md`.

`--dry-run` prints the planned cascade per candidate and fetches nothing: the way to
inspect attempt order before spending real requests against publishers.

`report` output:

```
alembic-s4 — round all
  ACA            7/10  0.70
  IND            3/9   0.33
  MET            5/6   0.83
  found          25
  attempted      25/25
  obtained       15/25  0.60
  floor          0.80 (v1, 2026-09-22)   INSUFFICIENT_ACQUISITION   basis: obtained
  failures       ABSTRACT_ONLY 6  PAYWALL_403 4
  by host        www.ravenpack.com 4  www.sciencedirect.com 2  …
```

**The denominator is `found`, not `attempted`** — corrected 2026-09-24 after a review showed the
original divided by acquisition rows, so one obtained source of twenty-five found reported 1.00
and passed the floor. The chain of states is printed separately because the remedies differ: found
but unclassified needs a declared rule, found but unattempted needs the round finishing, attempted
and refused needs a campaign or a better cascade.

The per-class rate is reported **before** the aggregate, not after: D3 says classes are not
mixed, and a 0.73 hiding `DOC 0.00` is a different fact from a uniform 0.73. The floor is
printed with its version (see "The floor is versioned" in §8), because a round-over-round comparison must show whether the
corpus changed or the measuring stick did.

### Progress on stderr

`acquire` writes one line per source to **stderr** as it goes, with the running rate:

```
[ 7/26] 0.71  ok    S07  unpaywall  cc-by  412 KB
[ 8/26] 0.62  fail  S08  LANDING_PAGE_ONLY  (2 840 chars, "purchase pdf")
```

stdout carries the final summary only, so `claimstone acquire … > summary.txt` still works
and the progress remains visible. A round over 25 sources with 30-second timeouts takes
minutes; a silent process that long is indistinguishable from a hung one.

`acquire` always exits 0, including below the floor — measuring is not failing. `report
--gate` exits 3 when the status is `INSUFFICIENT_ACQUISITION`, so a script or CI cannot
ignore it. **No flag overrides the floor** (invariant 3).

### The floor is versioned

Invariant 3 forbids an override flag. That leaves the door next to it open: `acquisition_floor`
is a number in an editable file, and lowering it after seeing an awkward result is the same
post-hoc move that the frozen question registry exists to prevent.

So a floor change is the same class of event as a registry bump (invariant 5). `sources.yaml`
carries three further keys, all required whenever `floor_version > 1`:

```yaml
acquisition_floor: 0.80
floor_version: 1
floor_set_at: 2026-09-22
floor_rationale: >
  Chosen before the first measured round. Below this share of found sources, per-question
  coverage is not interpretable: a question with no claims cannot be distinguished between
  NEVER_ASKED and UNANSWERED_IN_LITERATURE when a quarter of the corpus was never read.
```

The rule, pre-registered: **the floor may be lowered only on a documented argument that a
specific class of sources is structurally unobtainable** — "4 of 26 are Elsevier with no open
copy in any repository, verified per DOI" — and never because the number came out awkward.
`report` prints `floor 0.80 (v1, 2026-09-22)` so the version travels with every figure.

Landing below the floor is a legitimate deliverable: `INSUFFICIENT_ACQUISITION` plus the
losses broken down by failure class and by host is a finding about the cascade, which is what
D11 exists to make sayable.

## 9. The dashboard

Specified separately in `2026-09-22-dashboard-design.md`: it grew from a stage-2 appendix
into a view over the whole round, organised around the question registry, and has its own
lifecycle.

Two of its properties are load-bearing for this stage and are restated here: it is
**read-only** — no route mutates anything and no button starts a fetch, so a browser refresh
can never spend the per-domain budget — and it computes **statelessly per request** by
re-reading the ledger, which is what makes it safe to watch while `acquire` is appending.

## 10. Known divergences from the drafts

1. Any 200 with an acceptable content type counts as acquired — §5 replaces this.
2. `rate()` collapses on the latest row, so a failed retry can erase a recorded success —
   §6 rule 2 replaces this.
3. No campaign concept: `run()` skips only `acquired=True`, so every re-run knocks on every
   wall — §7 replaces this.
4. The round committed in `630ca52` reports **0.72**, measured before any content gate existed.
   Re-gating its stored bytes gives 0.64 under a length-only rule and **0.48** once abstract
   pages are recognised (§5). That figure must be restated when this plan lands; it is not a
   regression, it is the same corpus measured with an instrument that works.

## 11. Manifest — the fourth project file

`projects/<name>/manifest.tsv`, optional, gitignored (it encodes the consuming system's
reading list). Columns: `source_id, class, format, url, title`.

Validated at import against `sources.yaml`: `class` must exist among the declared classes,
`source_id` must be unique, at least one of `url` and `title` must be present. An unknown
class is a configuration error, not a skipped row. `config.py` learns to load it as
`Project.manifest`, keeping validation in one place.

Its purpose is to hold the source list constant: the milestone asks whether the acquisition
rate moves on the manifest that produced 0.42, not whether a fresh search finds easier
papers.

## 12. Testing

Offline by default. A `FakeFetcher` satisfying the `net` `Protocol` answers from a
URL → response dictionary.

| file | covers |
|---|---|
| `test_fulltext.py` | minimal valid PDF, truncated PDF, landing-page HTML, long OA article, HTML under threshold, error page served as `application/pdf` |
| `test_resolve.py` | cascade order, wall last, dedup on normalised URL, version rank, DOI-from-title rejecting an approximate match |
| `test_acquire.py` | row shape, idempotency, success not overwritten by failure, terminal/transient policy, missing `source_class` raises |
| `test_admissibility.py` | rate arithmetic, per-class breakdown, floor comparison, absence of any override |
| `test_manifest.py` | manifest validation: undeclared class, duplicate `source_id`, a row with neither url nor title, absent file is not an error, threshold overrides |
| `test_gate_audit.py` | sweep arithmetic over a fixture store; a rejection listing that names the triggering phrase; re-running the gate opens no socket |
| `test_cli_acquire.py` | `--retry-class` without `--campaign` refused; `report --gate` exits 3 below the floor; progress goes to stderr and the summary to stdout |

HTML fixtures are **synthetic**, hand-written to reproduce the structure of a landing page.
Copying a publisher's real page into a public repository is a copyright problem not worth
having. A live test against three known-OA DOIs lives in `test_live.py`, marked
`@pytest.mark.network` and skipped unless `CLAIMSTONE_LIVE=1` — outside CI.

## 13. Documentation

`docs/contracts/acquisitions.md`: the row schema and the failure taxonomy, which is what
stage 3 will read.

## 14. Out of scope, deliberately

No retrieval behind institutional authentication, even legitimate. A source reachable only
that way stays `PAYWALL_403` and lowers the rate. This keeps the rate truthful about the
corpus *this machine* can read, but it means a floor of 0.80 may be unreachable on a
manifest heavy with Elsevier. The correct response then is to change the manifest or the
floor, not the downloader.

Stage 3 concerns — GROBID, chunking, reference extraction, the citation discovery channel —
are not specified here beyond the `fulltext_confirmed` signal named in §5.
