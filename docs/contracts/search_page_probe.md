# Isolated OpenAlex page probe

`store/<project>/audits/research-search/variant-probe/pages.jsonl` records one
authorized page inspection. It is separate from `queries.jsonl`, `query_hits.jsonl`
and `candidates.jsonl`: a page probe cannot admit candidates or change a frozen
production search round.

The plan names its campaign, project input hashes, parent plan path and SHA-256,
first-page response SHA-256, page 2, and a ceiling of two physical requests.
The tool verifies that the parent response is linked to a successful recorded
request and reports a first-page total below OpenAlex's 10,000-result basic
paging limit. The recorded request URL uses the same mode, term and page size;
the only added parameter is `page=2`.

Each outcome row has `campaign`, `plan_sha256`, `parent_response_sha256`,
`page`, `per_page`, `ok`, `http_status`, `failure_class`,
`response_sha256` and `provider_usage`. A valid response also has `returned`,
`total_available`, `overlap_first_page` and `result_keys`. The page's raw
response is stored by `RecordingFetcher` under `requests/raw/`. Its request,
robots, redirect and failure events are in `requests.jsonl` with the same
campaign. A started physical request with no completed page blocks automatic
retry; it needs inspection and a new named plan.

Provider result keys and same-title matches are retrieval observations. They
do not establish that two versions are one study or that either is eligible
for a research question.
