# `web_locator.jsonl` — what an open-web search found for a work we could not read

**Written by:** `tools/locate_web_copies.py` (host `api.search.brave.com`, one exact-title query per candidate, a second
bare-title query only when the first returned nothing). **Read by:** the portal overview (`source_tracker[].web_leads`) and the
acquisition cascade. Append-only. It writes nothing to `candidates.jsonl` and downloads nothing (D145).

| field | meaning |
|---|---|
| `locator_version` | `1` (`claimstone/web_locator.py:LOCATOR_VERSION`, registered as an instrument) |
| `provider`, `query`, `query_sha256`, `queried_at` | what was asked, of whom, when |
| `candidate_key`, `doi`, `title` | the work looked for |
| `ok`, `failure_class` | the request completed; a failed one offers no leads |
| `policy_source`, `policy_sha256` | `project` (declared in `sources.yaml`) or `file` (exploratory); the digest of the policy applied |
| `max_results` | the window of results that count as leads; the rest are recorded and never offered |
| `results[]` | **every** result seen: `rank`, `url`, `title`, `description`, `host`, `decision`, `reason` |
| `allowed` | how many results were `ALLOWED` |

**Decisions on a result, in order:** `DENIED_EXCLUDED` (the project's `excluded_hosts`, always first), `DENIED` (the project's
`deny_hosts`), `ALLOWED` (`allow_hosts` or `allow_host_patterns`), otherwise `UNCLASSIFIED`. There is no author-site heuristic: a
personal site stays unclassified until a person adds its host to the policy.

**The project policy** is `sources.yaml: web_locator` — `enabled`, `provider` (`brave`), `allow_host_patterns`, `allow_hosts`,
`deny_hosts`, `max_results` (1..10). A misspelt key is a configuration error. A *declared* block is part of the protocol digest
(declaring or changing it is drift); an absent one leaves every earlier digest as it was.

**Leads become files only through an authorised plan.** The cascade appends `web_locator` locations last, for `ALLOWED` leads
whose exact host an authorised plan named, and only for a project that declared `enabled: true`. A file so obtained is parsed
like any other, and `normalize` then compares the document's own title with the candidate's (`identity_check`,
`identity_check_version 1`): a clear mismatch is `WRONG_DOCUMENT`, a file with no readable title is `IDENTITY_UNVERIFIED`;
neither is a confirmed document and neither counts toward the floor. The bytes are kept.
