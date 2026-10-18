# `citation_edges.jsonl` and `citation_titles.jsonl` — leads around our candidates

**Written by:** `tools/observe_citation_edges.py` (`api.opencitations.net`, two requests per seed; `api.openalex.org`, one
request per 50 suggested DOIs, only for titles). **Read by:** the portal overview as `citation_suggestions`. Append-only. Nothing
here writes `candidates.jsonl`, creates a candidate, changes a floor or counts toward a denominator (D143).

`citation_edges.jsonl` — one row per seed per direction; the newest row per `(seed_candidate_key, direction)` is current.

| field | meaning |
|---|---|
| `snowball_version` | `1` (`claimstone/snowball.py:SNOWBALL_VERSION`, registered as an instrument) |
| `seed_candidate_key`, `seed_doi` | a candidate we already hold, with a DOI |
| `direction` | `cited_by` (other work cites the seed) or `cites` (the seed cites the other work) |
| `ok` | the request completed; a failed one contributes nothing to suggestions |
| `edges` | `{other_doi, creation, oci}`, de-duplicated, at most 200 per direction |
| `truncated` | the answer had more than 200; a long list is never presented as a complete one |
| `campaign`, `observed_at` | the named run and the UTC moment |

`citation_titles.jsonl` — `{doi, title, year, venue, campaign, observed_at}`, so a lead can be read as a work rather than a DOI.

**Suggestions** are the works linked to by at least `min_links` (default 2) distinct seeds in the flow's scope that are not
candidates already, most-linked first, ties by DOI. `links` is **a count of seeds, not relevance**. Depth is one. A person
proposes a lead through the ordinary intake (`kind: doi`); it is routed like any proposal.
