# `acquisitions.jsonl` — the contract

Written by stage 2 (`claimstone acquire`). Append-only. One row per candidate per run that the
retry policy allowed; a candidate it declined writes no row, so silence means "not tried this
run" and the previous row stands.

**Stage 3 depends on two fields only — `sha256` and `stored_path`.** Everything else is
accounting, and accounting is why the file exists: the acquisition rate computed from it decides
whether a round may produce verdicts at all.

## Fields

| field | meaning |
|---|---|
| `candidate_key` | identity from `ids.candidate_key`: DOI, else folded title, else URL |
| `source_id` | the manifest's own identifier, when the candidate came from a manifest |
| `source_class` | mandatory, no default. A classless candidate raises rather than passing |
| `campaign` | which run this was; `routine` unless named. Terminal retries must name one |
| `attempt_no` | 1 for the first attempt at this candidate, incremented per recorded row |
| `acquired` | whether bytes passed the content gate. **Not** whether HTTP returned 200 |
| `gate` | the gate's verdict: `kind`, `chars`, `reason`, `gate_version`, `thresholds` |
| `sha256` | content hash of the stored bytes; `null` when not acquired |
| `stored_path` | where those bytes live under `store/<project>/raw/` |
| `url` | the location that succeeded, or the candidate URL when nothing did |
| `provenance` | who named that location: `unpaywall`, `openalex`, `arxiv`, `candidate`, `wayback` |
| `version` | `publishedVersion`, `acceptedVersion`, `submittedVersion`, or empty |
| `licence` | as reported by the resolver; `"unknown"` for archived web sources |
| `oa_status` | `gold`, `green`, `hybrid`, `bronze`, `closed`, or `null` where not applicable |
| `host_type` | `publisher` or `repository`, when the resolver said |
| `content_type`, `bytes` | what came back |
| `failure_class` | the class of the **last** attempt: what stopped us. `null` when acquired |
| `attempts` | every step of the cascade, in order, each with its own `failure_class`, `gate_kind`, `gate_reason` and `stored_path` |
| `fetched_at` | UTC, ISO 8601, seconds |

`gate.thresholds` and `gate.gate_version` are on the row because a rate computed under different
thresholds is not comparable to one computed under these, and without recording them the
difference is invisible.

An attempt whose bytes arrived carries `stored_path` **whether or not the gate accepted them**.
That is what makes `claimstone gate-audit` able to re-run the gate at other thresholds without
re-fetching, and what gives the by-hand rejection check something to look at.

## Failure classes

Terminal — retrying changes nothing until the world changes, so a retry needs a named campaign:

`PAYWALL_403` · `ROBOTS_DISALLOWED` · `EXCLUDED_HOST` · `NOT_FOUND_404` ·
`UNEXPECTED_CONTENT_TYPE` · `LANDING_PAGE_ONLY` · `ABSTRACT_ONLY` · `TOO_SHORT` ·
`CORRUPT_PDF` · `NOT_TEXT` · `NO_LOCATIONS`

Transient — the next ordinary run tries again on its own once the TTL has passed:

`TIMEOUT` · `CONNECTION_ERROR` · `SERVER_ERROR_5XX` · `RATE_LIMITED_429` ·
`DOMAIN_BUDGET_EXHAUSTED` · `EMPTY_RESPONSE` · `WAYBACK_MISS`

An unrecognised class counts as terminal: a typo must cost a retry, not an unbounded loop
against a publisher. `DOMAIN_BUDGET_EXHAUSTED` is transient on purpose — a source dropped
because the budget ran out must return to the queue, or a blocked downloader reads as a
saturated corpus.

Four of those classes are set by the content gate rather than by HTTP. `LANDING_PAGE_ONLY`,
`ABSTRACT_ONLY`, `TOO_SHORT` and `NOT_TEXT` all describe a transfer that succeeded and returned
something that is not the document. `ABSTRACT_ONLY` is distinct from `TOO_SHORT` because "we
obtained the summary page" says a full text may exist elsewhere, where "the document is short"
does not.

## Collapsing the log

A reader that wants one row per candidate takes **the latest successful row**, falling back to
the latest row only when none succeeded. Plain latest-wins would let a failed retry campaign
erase a success whose bytes are still on disk, lowering the rate while the corpus was unchanged.
`admissibility.collapse` is the reference implementation.
