# Source-selection preparation audits

Implemented by `tools/audit_source_selection.py`. This is an offline audit of **manual**
screening, not an automatic classifier or a new production admission rule. It does not write
stage-owned ledgers, start a discovery/acquisition campaign, or change existing round denominators.

## Inputs

`--plan` identifies an independently named proposed round, dated positive protocol version,
question id/text, registry digest, rationale, project-supplied criteria, inventory file, assessment
file and frozen input hashes. The inventory must be hash-frozen; freeze the project inputs as well.
The initial inventory should include metadata exclusions and known sources, not just downloads.
Each inventory identity occurs once; suspected different-key duplicates remain separate.

Criteria have ids, descriptions and one of these generic dimensions: population, topic, exposure,
outcome, unit, horizon, design, identity or duplicate. Download success/accessibility and result
direction are not selection dimensions. Scientific applicability remains a reader's judgment:
structural validation cannot certify that an exclusion rationale is correct or unbiased.

Each manual assessment carries:

| Field | Meaning |
|---|---|
| `candidate_key` | The original inventory identity, never silently replaced |
| `decision` | INCLUDE, EXCLUDE or UNCERTAIN |
| `identity_status` | VERIFIED, CORRECTED, CONFLICT or UNVERIFIED |
| `checked_by`, `reason` | Who assessed it and why; an agent assessment is not a human signature |
| `criterion_ids` | Which declared criteria justify this decision |
| `evidence` | Observations and their provenance locators; local exact passages may include chunk/text/document hashes |
| `corrected_identity` | For CORRECTED: canonical key, title and authority, with other verified metadata as appropriate |

References/observations are inspected by the reader; this preparatory tool neither contacts their
URLs nor re-runs the quote gate. Its validation is structural, not a scientific reading test.
An identity correction needs evidence that the works differ, not merely equal normalized titles.
Corrections stay in the audit, with original and corrected identities; they do not rewrite an old
candidate, acquisition, document or chunk. Applying them to production remains separate work.

## Output and closure

The audit embeds the complete protocol and assessments plus input/assessment hashes. `--write`
stores a content-addressed immutable JSON under the plan's `results/`; repeated identical audits
reuse the same file. Previous assessments remain recoverable from previous audit snapshots even
if the working assessment file is revised. No production result is signed or synthesized.

Included, excluded and pending keys are reported separately. Missing assessments, uncertain
eligibility, conflicting identities and unverified identities remain pending. A cohort is ready
for **preparation**, not acquisition admission or verdict, only after all identities have been
assessed and at least one source is included. A correction updates the proposed eligible metadata;
colliding corrected identities require explicit duplicate assessment, never silent merging.

The tool leaves acquisition rate, literature recall and screening precision null. Downloading
every current inclusion while hundreds of cases remain pending does not close the cohort.
Existing admission calculations remain authoritative for existing rounds. A newly selected cohort
must enter a separately dated scope, with verified reuse and all normal downstream gates.

Example:

```bash
.venv/bin/python tools/audit_source_selection.py --plan <selection-plan.json> --write
```

Next integration work: measured screening error, controlled admission of closed cohorts,
and scheduler resume. The advisory screening/identity ledgers below now exist; they do not
change admission or substitute an AI assessment for a human reference.

## Append-only advisory screening and identity ledgers (D79)

`claimstone/source_selection.py` owns `source_screening.jsonl` and `source_identity.jsonl`
under the project store. `tools/import_source_selection.py --plan <plan>` previews frozen
observations offline; `--apply` validates the whole proposed batch and appends only missing
rows. A rerun is idempotent. Existing stage ledgers remain byte-identical. This is a
production-owned record of **observations**, not a production admission selector.
Append requires the scope, question and frozen inventory keys. The writer holds a
project-local advisory lock across replay and both appends so two writers cannot
commit duplicate IDs from the same previous state. Other writers must use this API.

Every screening row has a content-derived `assessment_id`, `selection_version`, scope,
question, registry hash, original candidate key, explicit source class or `UNCLASSIFIED`,
decision, role, reading level, criteria, reason, assessor, input hash, located exact quotes
and the previous row's id in `supersedes`. A changed assessment cannot replace a row
silently: the new row must point to the current row. The first importer accepts only
`AI_PROVISIONAL`, including Claude Code's interactive model/harness identity and an
explicit `prompt_sha256: null` because the exact interactive prompt file was not retained.
It rechecks abstract quotes against frozen packet text and full-text quotes against frozen
PDF extraction. It also reconstructs each abstract from its retained OpenAlex/Crossref
response and matches the recorded `screening_metadata.jsonl` outcome. The full-text
import requires a named successful copy campaign and regenerates `pdftotext -layout`
from the retained PDF bytes. A blank PDF title is rejected. Semantic correctness
is still not established by substring matching. Within one scope, supersession
cannot lower the evidence level from full text to abstract or change registry/class;
those changes need a separately dated scope.

Identity rows carry their own content id, original candidate key, metadata and copy hashes,
status, reason and located observations. `POSSIBLE_VERSION` is a lead, not a merge. A future
`VERIFIED_SAME_WORK` observation needs an explicit canonical work key; even then this ledger
does not transfer acquisitions or annotations. Uncertain and unclassified cases remain pending.
The legacy identity v1 record is interpreted as a relation to its held copy hash. New
`identity_relation_version 2` rows must name `related_kind` (`CANDIDATE` or `HELD_COPY`)
and `related_key`; a held-copy key must equal `copy_sha256`, and a candidate counterpart
must be in the frozen inventory. Each counterpart has an independent append-only
supersession chain. A second suspicion about one candidate therefore does not hide
the first relation. Existing v1 rows remain readable and can be superseded by a v2
row naming the same copy.

`source_selection_import_version 2` is an explicit rescreen plan for the same scope.
It freezes a new AI file and supplies `replacement.previous_assessment_ids` for every
abstract being replaced plus `replacement.preserved_fulltext` for the one held
full-text case in this importer. Every ID must still be current. The importer
revalidates all original metadata and PDF bytes, refuses a new AI decision that
conflicts with the preserved full-text case, and appends only the abstract
replacements. A rerun writes zero rows. The v1 plan remains valid and unchanged;
there is no automatic promotion of a changed AI file. If the held full-text
assessment itself changes, prepare a separate, evidence-backed plan.

The L02 v2 import plan is private under `store/alembic-s4-lungo/audits/source-selection/`.
Its 20 Claude abstract judgments yield 15 provisional `NOT_DIRECT` observations and five
uncertain observations. A separate PDF-backed row supersedes only the REIT uncertainty with
provisional `CONTEXT`, leaving four uncertain. One `POSSIBLE_VERSION` identity row records
the REIT PDF's differing title. On the 830-key frozen inventory, the resulting preview has
20 observed keys and 810 not observed **in this new scope**; the prior 34 agent assessments
from the older protocol remain separate and are not silently mixed with it. No cohort is
closed, no candidate is admitted, and no screening accuracy or literature recall is inferred.

## Offline identity relationship audit

The guided 2026-10-06 continuation adds source-level offline preparation tools.
`tools/build_source_selection_dossier.py` binds a held PDF, active generation,
current claim quotes and review outcomes to a content-addressed dossier.
`tools/preview_source_selection_queue.py` derives outstanding work from the
frozen inventory and current advisory chains, including recorded abstracts and
verified same-work counterparts. Both write only isolated audit snapshots.
The targeted `record_l02_aca001_observation.py` and
`record_l02_held_v2_observations.py` scripts recheck retained evidence and append
provisional full-text observations through the existing locked API; reruns add
zero. These are interactive agent readings, not batch model measurements or
independent human labels. Their 19 held-source observations increase the current
v2 view from 20 to 39 observed keys without closing or admitting a cohort.

`tools/audit_identity_relationships.py --plan <selection-plan> --acquisitions <ledger> --write`
reuses the frozen selection audit, lists assessed canonical corrections and identifies any
acquisition still stored under an original key. It also lists cross-key identical byte hashes,
nonempty equal-title groups and
titles of the form “Appendix/Supplement for/to …” with possible parents. The JSON report is
content-addressed under `identity-audits/`; re-running identical inputs reuses it. Input hashes
include the plan, inventory, decisions and optional acquisition ledger.

`--relationships <assessments.json>` adds a manually inspected pair list and freezes its
hash. Each pair must name two original inventory keys, a reason and located observations.
`SAME_WORK` and `DISTINCT_WORKS` are `VERIFIED`; `POSSIBLE_VERSION` and
`POSSIBLE_SUPPLEMENT` stay `PENDING`. Verification needs at least two cited observations.
The validator checks structure and provenance fields, not the truth of a reader's inference.
An assessed same-work relationship does not automatically transfer bytes or annotations.

Identical bytes establish the same held copy, not the correctness of its bibliographic identity.
All title-derived relationships are `REVIEW_REQUIRED`: same title can describe a new version,
the same copy or an unrelated work. A proposed appendix parent needs authorship and content
inspection. The audit makes no merges, changes no stage ledger and does not certify a cohort.
An assessed correction retains its original key and authority but is not applied to production.

## Isolated model-screening experiment

`tools/run_source_screening.py --plan <pilot-plan>` previews a frozen 20-case development
packet; `--prepare` writes only experiment requests; `--execute` runs two priced Ollama Cloud
readers and records raw responses and structured recommendations under a separate experiment
store. Neither a recommendation nor agreement with the prior agent reference becomes a source
eligibility decision. See D69 for the measured preparation and its limits.

The prepared L02 plan is private under
`store/alembic-s4-lungo/audits/source-selection/l02-v1/cloud-pilot-v2/plan.json`.
The experiment keeps original references out of prompts, checks quoted evidence as an exact
substring, retains invalid answers and unknown-cost attempts, and shares the prior calibration
ceiling. `UNCERTAIN` and unreviewed exclusions remain visible. The 796 remaining metadata-only
records need authoritative abstracts and identity/version checks before an abstract screening
batch can be prepared; title ordering alone is insufficient.

The first 20-case host pilot is measured in D70. Version 2 of the experimental screen asks for
separate verbatim exposure and horizon spans on an INCLUDE, in addition to its main decision
quote. A mechanically valid span is only traceable, not necessarily a correct interpretation;
the pilot's agent reference is still neither held out nor human gold.

`tools/fetch_screening_abstracts.py` has a separate, read-only preview and an explicit `--execute`.
The frozen plan names the campaign, first ten candidate keys, queue hash, registry digest,
project input hashes and request ceiling. Execution records HTTP attempts and raw responses in
the existing request ledger and appends `screening_metadata.jsonl` rows; it never alters
candidates, source-selection assessments or model screening rows. `ABSTRACT_AVAILABLE` requires
both title and DOI identity checks where a DOI exists. `NO_ABSTRACT`, `IDENTITY_CONFLICT`,
`INVALID_ABSTRACT`, `LOOKUP_FAILED` and `NO_LOOKUP_ID` remain separately visible. Attempted
keys are not retried within the same named campaign. A later retry needs a new plan/campaign.

D72 records the first ten OpenAlex outcomes: four identity-checked abstracts, six absent
abstracts. The Crossref fallback plan selects exactly those six DOI keys and requires their
prior `NO_ABSTRACT` status. `screening_metadata.jsonl` retains both campaigns independently.
The screening pilot's terminal malformed model response is also retained; a second execution
resumes other frozen tasks without retrying that physical call. A missing schema field is not
silently supplied by the driver.

D73 supersedes the running v2 pilot: DeepSeek still made a semantic false inclusion despite
supplying an exact exposure quote, and both readers had format failures. Screening version 3
clarifies the required output shape but has no measured result. A separate twenty-key metadata
plan under `l02-v2/heldout-metadata-v1-plan.json` excludes development-case titles. The
`build_screening_reference_packet.py` output has no labels; only a person independent of the
model run can supply the reference. Missing abstracts stay `metadata_only`, not `EXCLUDE`.
