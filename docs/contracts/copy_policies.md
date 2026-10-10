# Finite copy policies

`store/<project>/copy_policies.jsonl` is append-only. A policy has one immutable
`planned` event, one optional `authorized` event and one optional `revoked`
event. `policy_id` is the SHA-256 of the canonical plan. Event IDs hash each
event body without its timestamp. The reader rejects invalid IDs or state
transitions.

The plan binds one exact discovery schedule, its flow IDs and query operation
IDs, the current protocol and Python package hashes, exact HTTPS hosts, declared
source classes, a UTC start and expiry within one year, a maximum number of
candidates and a maximum physical-request count per candidate. Their product
is the lifetime request ceiling. Planning makes no request and grants no
permission. `copy-policy-authorize` is a separate operator action; revocation
stops later starts.

During an active policy window, `scheduler tick` may create an exact acquisition
operation for a new candidate only when a version 2 query hit belongs to a
**completed** query operation in the authorized discovery schedule, its query
outcome is successful and names that operation as campaign, and its candidate
key, URL, title, DOI and source class still match the recorded hit. The
candidate must be in that flow, classified in an approved class, have an HTTPS
URL on an approved host and have no unresolved possible-duplicate marker.
Planning and authorization happen under the project writer lock. Every
authorized operation permanently reserves one candidate and its full request
ceiling, including failures and interrupted runs. Restarts cannot replenish
the allowance. The regular acquisition executor enforces robots, redirects,
non-global-address refusal, per-domain failure budgets and content gates.
Metadata resolver API calls are disabled for this policy; a different legal
location or host needs a new, explicit campaign.

The policy cannot admit a source scientifically, purchase a copy, close a
cohort or sign a verdict. A candidate without a matching hit remains visible
for operator review and ordinary exact-batch authorization. The policy and
its schedule must both remain authorized and unexpired when a copy operation
starts. An operation that began before revocation completes under the
project-wide writer lock; revocation prevents later starts.
