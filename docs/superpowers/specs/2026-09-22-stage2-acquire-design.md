# Stage 2 — acquire: design

Date: 2026-09-22 · Scope: stage 2 only · Status: approved, not implemented

Stage 2 turns candidates into frozen texts and accounts for every attempt. It is the first
milestone because acquisition, not extraction quality, is the binding constraint on the
science (D8). The deliverable is a sentence with a number in it: the acquisition rate on a
26-source manifest that currently stands at 0.42, with OA status, licence and failure
reason recorded per source.

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
| `dashboard.py` | new | read-only local HTTP view over the ledger. stdlib only. |

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

`kind` is one of `PDF_FULLTEXT`, `HTML_FULLTEXT`, `LANDING_PAGE_ONLY`, `TOO_SHORT`,
`CORRUPT_PDF`, `NOT_TEXT`. Only the first two count as acquired.

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

### HTML / XML

XML is treated identically to HTML here; structured parsing belongs to stage 3.
Visible text is extracted with the stdlib `html.parser`, dropping `<script>`, `<style>`,
`<nav>`, `<header>`, `<footer>` and `<aside>`. Then:

| condition | verdict |
|---|---|
| `chars < min_text_chars` (3000) | `TOO_SHORT` |
| `3000 ≤ chars < paywall_doubt_chars` (12000) **and** a paywall phrase is present | `LANDING_PAGE_ONLY` |
| otherwise | `HTML_FULLTEXT` |

Paywall phrases (`get access`, `purchase pdf`, `buy article`, `rent this article`,
`sign in to continue`, `institutional access`, `add to cart`, `subscribe to continue`,
`you do not have access`) are matched case-folded against the extracted text.

**A phrase alone is never sufficient.** A legitimate open-access article also contains
"sign in". Above `paywall_doubt_chars` the text is there whatever the menu says.

### Recorded parameters

`gate_version` and the thresholds in force are written onto every ledger row. A rate
computed under different thresholds is not comparable to one computed under these, and
without recording them the difference would be invisible. Thresholds are overridable per
project under an `acquisition:` key in `sources.yaml`; the defaults are the values above.

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
                         "paywall_doubt_chars": 12000}},
 "sha256": "…", "stored_path": "store/alembic-s4/raw/….pdf",
 "url": "https://…", "provenance": "unpaywall", "version": "acceptedVersion",
 "licence": "cc-by", "oa_status": "green", "host_type": "repository",
 "content_type": "application/pdf", "bytes": 412839,
 "failure_class": null,
 "attempts": [{"url": "…", "http_status": 403, "failure_class": "PAYWALL_403",
               "provenance": "candidate", "version": "", "gate_kind": null,
               "content_type": "text/html", "bytes": 0, "elapsed_s": 1.2}],
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
   attempt list distinguishes them.

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
claimstone serve <project> [--port 8787] [--host 127.0.0.1]
```

`--dry-run` prints the planned cascade per candidate and fetches nothing: the way to
inspect attempt order before spending real requests against publishers.

`report` output:

```
alembic-s4 — campaign routine, 26 candidates
  obtained      19 / 26   0.73        floor 0.80   INSUFFICIENT_ACQUISITION
  by class      ACA 11/14 0.79   WP 6/6 1.00   NEW 2/4 0.50   DOC 0/2 0.00
  failures      PAYWALL_403 4   LANDING_PAGE_ONLY 2   NOT_FOUND_404 1
  by host       sciencedirect.com 3   onlinelibrary.wiley.com 2   …
```

The per-class rate is reported **before** the aggregate, not after: D3 says classes are not
mixed, and a 0.73 hiding `DOC 0.00` is a different fact from a uniform 0.73.

`acquire` always exits 0, including below the floor — measuring is not failing. `report
--gate` exits 3 when the status is `INSUFFICIENT_ACQUISITION`, so a script or CI cannot
ignore it. **No flag overrides the floor** (invariant 3). The only ways past it are to
obtain more sources or to lower `acquisition_floor` in `sources.yaml`, where the change is
visible in a diff.

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
| `test_dashboard.py` | route functions against a temp store; 405 on POST; torn final line skipped; non-loopback bind requires an explicit flag; one real GET against a port-0 bind for wiring |

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
