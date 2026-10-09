# Query-hit ledger

`store/<project>/query_hits.jsonl` records each usable result position returned by a completed
keyword search, including results outside the declared population and results whose candidate
identity was already known. This is an observation ledger, not an admission or identity decision.

`hit_id` is SHA-256 of `query_id|rank|candidate_key`. The first observation at a given position
is retained, so replaying the same round, query, provider, and result does not add a row. A later
change of rank makes another observation. The ledger is append-only; historical rounds before
`query_hit_version 1` have no backfilled hits. `query_id` is SHA-256 of
`round|source_api|topic_id|query` and joins `queries.jsonl`.

Each row has `query_hit_version`, `round`, `topic_id`, `source_api`, `query`, one-based `rank`,
`candidate_key`, `title`, normalized `doi` or null, provider ID when available,
`population_in_scope`, and `observed_at`. A hit may refer to a candidate that was not admitted to
`candidates.jsonl`. A matching title or provider ID is a retrieval clue, never permission to merge
records, obtain a copy, or issue a verdict.
