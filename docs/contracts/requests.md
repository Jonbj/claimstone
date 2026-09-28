# `requests.jsonl` and `queries.jsonl` — the contract

D48 adds append-only scholarly request and query-completion logs. Discovery, citation resolution and
acquisition own their contextual rows through `RecordingFetcher`; no model backend writes here.
Historic unlogged calls cannot be reconstructed and are never assumed successful.

## Request events

| field | meaning |
|---|---|
| `purpose` | discovery, citation-resolution or acquisition |
| `round`, `source_api`, `query`, `topic_id` | discovery context when applicable |
| `candidate_key`, `source_class`, `campaign` | acquisition context when applicable |
| `event` | redirect, robots, transport, blocked, response or validated_response |
| `url`, `request_url`, `redirect_chain` | outcome destination, original URL and destinations actually visited |
| `fetch_version` | transport/check instrument; currently 2 |
| `ok`, `http_status`, `failure_class`, `detail` | explicit outcome; blocked destinations may have no HTTP status |
| `content_type`, `bytes`, `elapsed_s` | available response metadata |
| `raw_sha256`, `raw_path` | available body stored under requests/raw, content-addressed |
| `recorded_at` | UTC event timestamp |

`redirect` records a completed redirect response before checking its next destination. A refused
next destination is a `blocked` event: it is not appended to the visited chain and no HTTP request
is made there. Transport timeout/connection failures remain attempted requests. Robots fetches also
check redirect exclusions and budgets. `response` and `validated_response` are contextual summaries,
**not extra HTTP attempts**; JSON validation can fail after a successful transport. Do not count
all request-log rows as paid transfers or sources. Test/alternate fetchers may only emit summaries.
Only bodies provided by the transport are stored; redirects and HTTP failures can lack raw bodies.

## Query completion

| field | meaning |
|---|---|
| `query_id` | hash of round, API, topic and term; latest outcome determines completion |
| `round`, `source_api`, `topic_id`, `query`, `per_query` | query and requested result cap |
| `discovery_version` | envelope validation instrument; currently 2 |
| `ok`, `failure_class`, `detail` | valid completed search versus explicit failure |
| `returned` | records returned by a valid search, including zero |
| `completed_at` | UTC attempt completion time |

A malformed envelope is a failure, never an empty search. No partial prefix of a malformed search
is harvested as a completed query. `Store` corruption propagates instead of being relabelled as
an API failure. Failed recorded queries make the selected round nonfinal (`awaiting_discovery`);
manifest-only admission excludes these queries because its population is independently declared.
Discovery CLI failure returns 3. Old missing logs remain unknown; this does not invent failed
queries for already recorded curated historical corpora.
