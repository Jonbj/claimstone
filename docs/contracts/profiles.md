# `profiles.jsonl` and `adjudications.jsonl` — the contract

Stage 6 appends profiles; a person alone authorizes an adjudication. Historical rows are never rewritten.
D45 introduced `profile_version 2`; D46 adds `profile_version 3`; D47 adds `profile_version 4`; D48 adds `profile_version 5`, independently of `decision_contract_version 1`.

## Profile identity and completeness

| field | meaning |
|---|---|
| `question_id`, `kind` | the question in the frozen registry |
| `registry_version`, `registry_sha256` | the registry described, never a relabelling of old claims |
| `claim_gate_version` | the current gate required of every scoped annotation before signing |
| `profile_version`, `decision_contract_version` | the profile instrument and the separate judgement contract |
| `round`, `manifest_only` | the candidate selector used for admission **and** all evidence |
| `population` | sorted source identifiers in that selector, including failed acquisition |
| `acquisition` | found, obtained, confirmed, rate, basis, floor identity, finality and blocking reasons |
| `evidence_sha256` | semantic digest of this question's claims, reviews, rejections and current scoped chunks |
| `extraction` | per-kind `expected`, `unanswered`, `unharvested`, `unchunked_sources`, `unregated` |
| `provisional`, `blocking` | any outstanding acquisition, normalization, extraction, harvest or review prevents signing |
| `profile_sha256` | digest of the whole row except this field and `built_at` |
| `built_at` | UTC timestamp of the append; excluded from evidence identity |

Results, direction counts, coverage, gate rejection reasons, review outcomes and linkage retain the fields
specified in the [stage 6 spec](../superpowers/specs/2026-09-25-stage6-synthesize-design.md). Operational
questions receive a `LITERATURE_VERDICT_NOT_APPLICABLE` row and no verdict.

A valid empty extraction array completes a reading. A failed model call never does. At least one current
valid reader must be harvested for each chunk and kind. A nonempty output is harvested when each annotation
is present in claims or rejections for its call, reader and chunk. Obsolete prompts and historical probes
are excluded from the reading obligation. Gate outcomes are selected by `gate_revision` across both
ledgers (see the [claim contract](claims.md)); a new rejection can retire an old accepted claim.
`unregated` counts current annotations in this kind not yet stamped with the required gate version,
including legacy rows whose missing version means 1. They cause `awaiting_regate` and prevent signing.
A profile does not silently certify old annotations under a newly changed gate.

Latest profile selection collapses by `(question_id, round, manifest_only)`, after filtering the selector.
A missing `manifest_only` on a legacy row means false. Version 1's hash omitted scope and extraction
completeness; versions 1–4 require rebuilding and reading again under version 5.

## Adjudication

The row contains `question_id`, `round`, `manifest_only`, `verdict`, `rationale`, `profile_sha256`,
`decision_contract_version`, `registry_version`, `registry_sha256`, `adjudicated_by`, `adjudicated_at`.
The five verdicts and minimum rationale length retain their existing meaning.

The shown hash is mandatory. Before appending, the engine recomputes a profile under the current project
and the exact same selector, checks admission, finality and equality with the saved and shown hashes.
It never signs an operational question or a provisional profile.

`verdicts` recomputes current profiles without appending. Its rows contain `profile`, `verdict`, `stale`,
`stored_profile_stale` and `unavailable`. If current admission fails, `unavailable` explains that refusal
and the saved profile is historical; any attached verdict is stale. If evidence changes while admission
holds, the displayed profile is the fresh in-memory result and the saved row is marked stale. Rebuild and
read it before signing. The awaiting-person count excludes provisional and inadmissible profiles.

Version 4 selects annotations and reviews against authoritative current model answers and verifies
harvest completion by the whole original record, call, reader and chunk. It cannot carry an old
successful claim/review through an invalidating replay, or collapse two readers into one annotation.
Version 5 uses the committed chunk generation and accepts only full-annotation v2 reviews (D48).
QUALIFIES remains a displayed direction count and belongs to neither directional class bucket.
