# `status_observations.jsonl` — what Crossref said about a work, and when

**Written by:** `tools/observe_status.py` (one host, `api.crossref.org`, two requests per DOI). **Read by:** the
portal's overview (`source_tracker[].status`). Append-only; the newest row per `candidate_key` is current. Nothing here
changes a claim, a profile, a floor or a signature (D142).

| field | meaning |
|---|---|
| `status_version` | `1` (`claimstone/status.py:STATUS_VERSION`, registered as an instrument) |
| `candidate_key`, `doi` | the candidate asked about |
| `state` | `NOTICE_RECORDED` · `NO_NOTICE_RECORDED` · `LOOKUP_FAILED` |
| `notices` | each `{type, label, doi, source, updated, via, kind}`; `kind` is `withdrawing`, `correcting` or `other` |
| `withdrawing` | any notice of kind `withdrawing` (retraction, withdrawal, removal, expression of concern) |
| `licences` | Crossref's `license` entries: `url`, `content_version`, `start` |
| `tdm_links` | Crossref `link` entries whose `intended-application` is `text-mining` |
| `work_ok`, `updates_ok` | whether each of the two requests completed |
| `campaign`, `observed_at` | the named run and the UTC moment |

**What the states mean.** `NOTICE_RECORDED`: Crossref listed at least one update that names this DOI. `NO_NOTICE_RECORDED`:
both requests completed and Crossref listed none — *when asked*, which is not a statement that none exists anywhere.
`LOOKUP_FAILED`: a request did not complete and nothing was found; it is retried on the next run regardless of the minimum
age. A half-completed lookup that did find a notice is `NOTICE_RECORDED` with `updates_ok` or `work_ok` false.

**Two routes to a notice.** An `updated-by` entry on the work itself, and the records returned by
`works?filter=updates:<doi>` whose own `update-to` names this DOI. Both are merged and de-duplicated on `(type, notice doi)`.
The field names are Crossref's as documented at the time of writing; the raw bytes are kept in `requests/raw/` by the
recording fetcher so a renamed field can be re-parsed instead of re-fetched. The `updates` filter and the `updated-by` field
are **unverified against a live response** until the first approved run.

A licence or a text-mining link is the publisher's metadata, not a permission to mine.
