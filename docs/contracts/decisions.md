# `decisions.jsonl` — operator decisions (B8)

**Written by:** the control server. **Read by:** the same server's `GET …/decisions`. The B12 operation
routes will read it too. No stage reads it. Append-only: a decision is one `decision_id`, and its
latest row is its state.

Every row carries:
- `decision_version` (`1`, `claimstone/decisions.py:DECISION_VERSION`);
- `decision_id` (24 random hex characters);
- `kind`, `flow_id`, `actor`, `signer_auth: "portal-session"`, `code_revision`, `recorded_at`.

## Kinds

| kind | fields | states |
|---|---|---|
| `identity` | `intake_id`, `candidate_key`, `answer` (`same_work` / `version_of` / `different` / `not_sure`), `reason` (≥ 20 trimmed characters except `not_sure`) | `recorded` |
| `retry_campaign` | `campaign` (new name, not `routine`), `max_requests` (1–50), `plan` (the server preview, verbatim) | `approved`, `deferred`, `declined` |
| `purchase_offer` | `candidate_key`, `work_version`, `vendor`, `price` (decimal string), `currency` (ISO 4217), `tax_status`, `terms_url`, `verified_at`, `resolves`, `supersedes` / `superseded_by` | `proposed` → `approved` → `bought_externally`; `declined`, `deferred`, `obsolete` |

`deferred` and `declined` rows add `until` (a deferral's future date), `reason` and `consequence`. The
consequence text is fixed per kind: a declined campaign makes no request, and a declined offer buys
nothing.

## What an identity answer does to the intake item

| answer | a file | a reference |
|---|---|---|
| `same_work` | accepted through the one acceptance path (B7b), identity `confirmed_by_decision` | `DUPLICATE` of the candidate |
| `version_of` | `REJECTED` for this candidate: a version is recorded, never the candidate's copy | `DUPLICATE`: the relation is recorded and the study count is unchanged |
| `different` | `REJECTED` for this candidate | routed again as a new work (`READY` / `NEEDS_NEW_ROUND`) |
| `not_sure` | stays `POSSIBLE_VERSION` | stays `POSSIBLE_VERSION` |

Both records are always kept. Nothing merges two works.

## What is never set by hand

- **Possession.** `copy_provided` and `copy_verified` are **derived** (`decisions.possession`), never
  written. They hold when a file for the offer's candidate was recorded in intake after the
  purchase: `copy_verified` once one was accepted.
- **Offers.** A 403 is never an offer. An offer exists only when an operator records one they
  verified.
- **Retry plans.** The hosts come from the candidate's recorded attempts (or its URL when never
  attempted). Excluded hosts, and hosts whose recorded failures (`net.recorded_host_failures`)
  reach the fetcher's budget, are listed as refused. An approval with no contactable host is
  refused.

## Order of the open list (F13)

Required items first (identity questions), then optional ones (offers, deferred items whose date has
come). Then by the candidate's `source_class` and `candidate_key`, then by age. The list reads no
claim, review or stance, so the order cannot depend on what a source is expected to say. An approved
campaign waits for an operation, not for a person, and is not in the list.
