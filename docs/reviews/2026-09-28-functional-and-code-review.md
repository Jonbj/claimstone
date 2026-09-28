# Functional and code review — 2026-09-28

Implementation update, 2026-09-28: all R01–R15 now have repairs in D45–D48 and regression coverage.
The original findings below record the reviewed baseline; dated repair measurements follow them.
All 22 synthetic probes pass and the isolated installed-wheel CLI discovers every backend.
No real ledger, publisher request, model call, floor change or adjudication was performed.

Reviewed revision: `04d7eff` (the checkout has advanced beyond the handoff commit `590af27`). The working
tree was clean when the review began. This review adds only this report and two offline reproduction
scripts. No production module, project configuration, real ledger, fetched artifact, signature, or
instrument version was changed. No scholarly request or model call was made.

**The implemented pipeline runs, but its current safeguards do not establish that a profile is complete,
belongs to the admitted population, or is still eligible for adjudication.** The baseline checks pass;
the functional review does not. The most immediate finding affects the real Q04 profile described as
complete in the handoff.

The report distinguishes measurements of the real store from counterexamples in temporary synthetic
stores. The latter prove reachable behavior, not its frequency in the real corpus. No recovery rate or
expected improvement is inferred from a sample.

## Functional review

Read `CLAUDE.md`, the current README and handoff, the six binding decision entries (including D40/D44),
the six data contracts, and the stage designs; follow the design record where it supersedes a spec.
In particular, D16/D17/D38's descriptive profile and human adjudication remain the intended design.
Pooling, lowering the floor, choosing a reviewer, and adjudicating Q04 are not remedies proposed here.

### What is confirmed

The live store reproduces the principal status figures:

| Project / population | Found | Obtained | Confirmed | Admission | Profiles | Adjudications |
|---|---:|---:|---:|---|---:|---:|
| `pmc-screen-time`, whole store | 40 | 38 | 37 | OK, confirmed rate 0.925 | 8 | 0 |
| `alembic-s4`, whole store | 76 | 17 | 16 | insufficient, rate 0.211 | 0 | 0 |
| `alembic-s4`, manifest | 25 | — | 14 | insufficient, rate 0.56 | 0 | 0 |
| `pilot-screen-time`, whole store | 199 | 90 | 0 | insufficient, obtained rate 0.452; normalize not started | 0 | 0 |

`pmc-screen-time` has 734 current chunk IDs from 37 sources, 1,668 claim IDs, and 42 reviews. Q04 has
3 contributing sources out of 37, 3 `CONTRADICTS` and 2 `QUALIFIES` results, and no unreviewed **stored
claim**. Its stored hash is exactly the handoff's
`8e93cbde7a5a11a2e6d84933dd48539194d22ace3b149f7f2b10003e440c0bf0`.

The code preserves several important boundaries: synthesize makes no automatic literature verdict;
operational questions receive no verdict; synthesis refuses a currently inadmissible population;
unreviewed stored claims make their profile provisional; quoted text is checked against stored chunk text;
conversion retains the written form; append-only ledgers retain rejected records; model results carry
reader and harness provenance. These properties are useful and should survive repairs.

### What is not established

The PMC extraction batch has 2,936 requests and only 2,902 requests with any currently valid result.
The 34 unanswered requests split into **10 effect, 4 heterogeneity, 15 method, 5 premise**. Current result
failures are 26 `NOT_JSON`, 3 `TRUNCATED`, and 5 `SCHEMA_INVALID`. These are failed readings, not empty
readings. Q04 belongs to `effect`, so its evidence production is missing 10 requested passages while its
profile says `provisional: false`.

The review of Q04's 42 received claims is complete. That is a narrower statement than completion of
extraction for Q04. Whether any missing passage would yield a useful result remains unmeasured.
**The handoff's assertion that Q04 is complete and ready to sign is therefore not supported by the
pipeline state.** No adjudication exists to retract, and the real profile was preserved unchanged.

The recorded reviewer and acquisition limitations in D38–D44 remain limitations. Agreement with an
existing reader is not human ground truth; PMC scope is not general literature coverage; and failed
acquisition in the other projects is a legitimate outcome. This review supplies no contrary measurement.

## Code review findings

Priority: **P1** should be repaired before relying on the affected scientific result or workflow;
**P2** affects reporting or a narrower operation. These are confirmed counterexamples, not claims that
every stored result is wrong. Findings are ordered by the consequences for a profile and its signature.

### R01 — P1: completion ignores failed or unrun extraction, and unattempted acquisitions

Locations: [synthesize.py:90](../../claimstone/synthesize.py#L90),
[evidence.py:124](../../claimstone/evidence.py#L124),
[admissibility.py:158](../../claimstone/admissibility.py#L158).

Synthesis reads claims/reviews without checking extraction requests or results. Its only downstream
completion check is the number of stored claims lacking a review. An unanswered queue with no claims
produces a final `NO_VERIFIED_CLAIM` profile. The real Q04 case above has the same defect.

Separately, acquisition `blocking` omits candidates not yet attempted or classified. Four confirmed
sources plus one never-attempted source reach the 0.80 floor and report `final: true`. This contradicts
the function's stated definition of finality and the stage 6 refusal of incomplete rounds.

Repair: establish completion for the selected round, registry and intended extraction workload; expose
unanswered/unharvested units and make affected profiles provisional. Distinguish successful `[]` from a
failure. Experimental and dry batches need an explicit relationship to the production workload: simply
requiring every historical batch to complete would also be wrong.

Probes: `pending_extraction`, `unattempted_acquisition`. Evidence: real PMC batch snapshot.

### R02 — P1: the numeral gate accepts a different signed or decimal number

Location: [claimgate.py:226](../../claimstone/claimgate.py#L226).

`_figure_present` bounds a match only with adjacent digits. A claim of `2` passes on quotes stating `-2`,
`0.2`, or `2.7`. These are distinct figures; substring presence does not satisfy invariant 1's numeric
verification. The quote itself is exact in all three counterexamples.

Repair: compare complete signed numeric tokens while preserving the documented typography/range and
implicit-percent cases from D25/D37/D38. Record a claim-gate version bump and measure the re-harvest;
do not predict how many real claims the fix would change.

Probe: `numeric_boundaries`. This review does not estimate prevalence in accepted real claims.

### R03 — P1: admitted population and registry do not constrain profile evidence

Locations: [synthesize.py:79](../../claimstone/synthesize.py#L79),
[synthesize.py:90](../../claimstone/synthesize.py#L90),
[synthesize.py:121](../../claimstone/synthesize.py#L121).

`--round` and `--manifest-only` filter the admission denominator, but claims, rejections, reviews and
the examined-source denominator are read across the whole store. A profile for an admitted round can
contain a reviewed result from another round. The floor then certifies a different population from the
one whose evidence is shown, contrary to D24/D41.

After a legitimate registry bump that changes Q's wording, v1 claims/reviews for that ID are also
relabelled into an adjudicable v2 profile without a new reading. Profile `registry_version` describes
the current config, not necessarily the evidence's registry.

Finally, `round` is added **after** `evidence.profile` hashes the payload. Changing it leaves the hash
unchanged; recomputing the declared digest over each of the eight stored PMC profile payloads does not
match its stored digest. Excluding the added `round` field explains those mismatches. `manifest_only`
is not recorded in the profile either.

Repair: carry the selected candidate/source population and compatible registry through every join,
record the scope and instrument identities before hashing, and preserve old profiles as old snapshots.
Use an identity that distinguishes profiles for different rounds instead of collapsing only on question ID.

Probes: `round_scope`, `old_registry_claims`, `round_hash`. Snapshot confirms the metadata/hash issue.

### R04 — P1: cached profiles can still be signed after their basis becomes inadmissible

Locations: [synthesize.py:152](../../claimstone/synthesize.py#L152),
[synthesize.py:202](../../claimstone/synthesize.py#L202),
[cli.py:891](../../claimstone/cli.py#L891).

Adjudication trusts the cached profile's `provisional` flag. It neither recalculates admissibility nor
checks that the profile still reflects the current ledger/config. A profile built at 1/1 can be signed
after another candidate makes the actual corpus 1/2 and `INSUFFICIENT_ACQUISITION`. A new reviewed claim
also leaves an existing signature reported current until someone explicitly rebuilds profiles.

The existing stale-signature test rebuilds the profile before reporting, so it misses this sequence.
If a subsequent synthesis refuses the now-inadmissible store, it does not invalidate the old cached row.
The CLI's shown-profile hash is optional, further weakening the promise that the signer signs precisely
what they inspected.

Repair: check current eligibility and freshness at signing/reporting, retain historical signatures
explicitly as snapshots, and require the shown hash. Preserve the rule that only a person adjudicates.

Probes: `adjudicate_after_floor_failure`, `stale_underlying_evidence`. No real signature was created.

### R05 — P1: rejudgement can erase a prompt mismatch; harvest ignores authoritative rejudgements

Locations: [model_call.py:480](../../claimstone/model_call.py#L480),
[extract.py:296](../../claimstone/extract.py#L296),
[review.py:186](../../claimstone/review.py#L186).

Rejudge reconstructs `RawAnswer` with no prompt and preserves truncation only. A previously recorded
`PROMPT_MISMATCH` carrying schema-valid bytes becomes `ok: true`, although `prompt_verified` stays false.
The failure was evidence about a different prompt, not JSON presentation, and cannot be repaired by
reparsing bytes. Refusal/backend failures are similarly not carried through by this path.

Both harvesters iterate historical attempts, skip every `rejudged_from` row, and retain the first
accepted claim/review. A fenced answer corrected from `NOT_JSON` to valid by rejudge therefore still
produces no claim. Conversely, a previously valid result invalidated by rejudge can still be harvested
from the old successful attempt. D14 says a rejudgement is authoritative, not an attempt.

Repair: preserve non-reclassifiable failure facts and consume the current result per call and reader.
When validity changes, record supersession explicitly rather than letting the first success remain
authoritative forever. Keeping a history does not require continuing to use its superseded rows.

Probes: `prompt_mismatch_rejudge`, `harvest_rejudged_answer`.

### R06 — P1: forced normalization leaves old chunks active

Locations: [normalize.py:148](../../claimstone/normalize.py#L148),
[chunk.py:152](../../claimstone/chunk.py#L152),
[extract.py:215](../../claimstone/extract.py#L215).

Chunk IDs use source and position, not a normalization generation. Rechunking a two-chunk document
into one appends `#c1` and leaves old `#c2` in `latest_by`. The document reports one chunk while extraction
reads two. Claims from earlier chunk text are also not bound to the version of text now held under that ID.

Repair: make the document's active chunk set/generation explicit, retain historical chunks, and bind
extraction and review provenance to immutable chunk content. A forced rechunk must supersede an active
set, not overlay whichever positions happen to recur.

Probe: `rechunk_ghosts`. This review has not established a ghost-chunk count in the real store.

### R07 — P1: redirects bypass destination conduct checks

Location: [net.py:226](../../claimstone/net.py#L226).

Excluded-host, budget and robots checks run on the initial URL only; the request then uses
`allow_redirects=True`. An allowed initial URL can follow a redirect to an excluded host. DOI redirects
can likewise reach a publisher whose budget is already exhausted or whose destination path is disallowed.
Recording the failure against the final host, as D27 requires, does not check that host before requesting it.

Repair: handle a bounded redirect chain with checks before every hop, record the resolved URL/chain,
and enforce the same conduct on robots fetches. Test with fake transports; no publisher sweep is needed.

Probe: `redirect_guards`; no request actually left the process.

### R08 — P1: failed discovery queries are indistinguishable from successful empty queries

Locations: [searchers.py:89](../../claimstone/searchers.py#L89),
[searchers.py:118](../../claimstone/searchers.py#L118),
[searchers.py:149](../../claimstone/searchers.py#L149),
[discover.py:83](../../claimstone/discover.py#L83).

OpenAlex/Crossref discard the returned outcome and iterate an empty mapping on failure. arXiv returns
silently on failed transfers or malformed XML. A timed-out query prints zero returned and writes no
failure record, just as a genuinely empty search does. Metadata requests in acquisition's resolver also
discard their outcomes. The store therefore is not a record of every request, as the working conventions
require, and a partially failed discovery can silently reduce the denominator.

Repair: record query/request outcomes separately from candidates, including successful empty queries,
transport/parse failures and resolver calls. Report search completion independently of acquisition rate.

Probe: `discovery_failure`.

### R09 — P1: distinct readers' annotations can collapse to whichever was harvested first

Locations: [extract.py:256](../../claimstone/extract.py#L256),
[extract.py:280](../../claimstone/extract.py#L280),
[extract.py:377](../../claimstone/extract.py#L377).

Claim identity includes chunk/question/quote and a model-chosen result ID, but excludes reader, call
identity and claim content. Two readers using `r1` and the same quote can give different claims/stances;
the first is stored and the other is skipped. This is a collision of annotations, not demonstrated
identity of study results. It can erase contrary interpretations and bias the per-extractor review report.

Repair: distinguish annotation provenance from any later result deduplication. Keep each reader's
annotation available to review; establishing that two annotations identify one study result is a separate
operation. D13/D30 comparisons must not depend on ledger arrival order.

Probe: `cross_reader_identity`.

### R10 — P1: the second reader does not see the study-result fields it is supposed to check

Location: [review.py:89](../../claimstone/review.py#L89).

The review prompt includes question, claim sentence, quote and passage, but omits estimate, uncertainty,
sample, horizon, design, dependence, stance and heterogeneity/method metadata. Those fields are later
shown as part of the usable result. A supported sentence does not establish that its attached sample,
design or estimate is correct; the reader was never asked about that annotation. This leaves the estimand
check identified by the verdict contract and `numbers.py` without its proposed control.

Repair: send and judge the complete result annotation, retaining passage context. Measure the revised
review task against the existing reference material without calling reader agreement ground truth.

Probe: `review_all_fields`. No reviewer was called during this review.

### R11 — P1: per-class admission uses obtained bytes while overall admission uses confirmations

Locations: [admissibility.py:126](../../claimstone/admissibility.py#L126),
[admissibility.py:216](../../claimstone/admissibility.py#L216).

The class rate remains `obtained/found` after normalization. A corpus with 9/10 confirmed passes its
global 0.80 floor, and a class with only 1/2 confirmed also passes a 0.80 class bar because its two fetched
artifacts report a class rate of 1.0. A refuted document is counted as sufficient class acquisition.

Repair: keep obtained and confirmed accounting separately per class and apply admission to the same
basis as the global lower bound. Preserve D36's additional-constraint rule.

Probe: `confirmed_class_floor`.

### R12 — P2: re-gating and sensitivity audits do not replay the acquisition instrument

Locations: [cli.py:300](../../claimstone/cli.py#L300),
[gate_audit.py:147](../../claimstone/gate_audit.py#L147),
[gate_audit.py:87](../../claimstone/gate_audit.py#L87).

Acquisition resolves per-class policy, but regate receives only project policy. A short-enough class of
public guidance admitted with `structural_signal: none` becomes `ABSTRACT_ONLY` during an unchanged-policy
regate. The row records this different policy as a current judgement and can change admission.

Sweep also starts from engine-default thresholds/policy and divides by attempted candidates, not all
found candidates. It is not a sensitivity analysis of the reported configured acquisition rate when
overrides or unattempted candidates exist. Flatness on the earlier fully attempted measured corpus does
not establish general correctness of this tool.

Repair: replay the applicable project/class instrument and declared population, varying exactly one
threshold, with scope/basis reported explicitly.

Probe: `regate_class_policy`. Sweep behavior is additionally evident in its implementation.

### R13 — P1: registry protection is not applied to every CLI store access, and permits rollback

Locations: [cli.py:402](../../claimstone/cli.py#L402),
[cli.py:544](../../claimstone/cli.py#L544),
[config.py:360](../../claimstone/config.py#L360).

Discover and model-run open `Store` directly; several reports do likewise. `discover --reclassify` accepts
a changed digest under the same registry version and exits 0. Model-run can spend on an old batch under
a drifted configuration. `_checked_store`'s docstring claims every opening checks drift, but these callers
bypass it.

Independently, `check_registry_drift` returns on a known matching hash before checking the highest recorded
version. After recording v1 and v2, reopening the original v1 succeeds. The rollback check applies only
to unseen lower versions.

Repair: centralize checked store access and perform monotonic-version validation before the equal-hash
return. Audit the intended registry compatibility of historical work units, not just config validity.

Probes: `unchecked_cli_registry`, `registry_rollback`.

### R14 — P2: reporting misclassifies qualifications, rejections and reader totals

Locations: [evidence.py:150](../../claimstone/evidence.py#L150),
[evidence.py:155](../../claimstone/evidence.py#L155),
[synthesize.py:91](../../claimstone/synthesize.py#L91).

`QUALIFIES` enters `by_class.for`, despite the stated rule that it belongs to neither side. The existing
test named `test_qualifies_counts_on_neither_side_of_by_class` checks only that `against` is empty;
it never asserts the `for` side is empty.

Profiles count raw historical rejection rows, including claims subsequently accepted. `extract-report`
already handles supersession, but synthesis does not use the same interpretation. The PMC store contains
63 IDs in both accepted claims and historical rejections; Q04 itself has no such overlapping ID.
`review-report` likewise counts those historical rejections without excluding accepted IDs.

Additionally, [model_report.py:26](../../claimstone/model_report.py#L26) collapses totals on call/backend
while its reader buckets separate models. The real `hetero-probe` comparison reports **26 total calls
versus 91 summed reader calls**, and **26 total valid calls versus 55 summed valid reader calls**, over
seven readers. The queue already has a call/backend/model identity, but the report reimplements a
different one. This contradicts the model-call contract that totals equal the sum of reader parts.

Repair: represent qualified results separately, distinguish current rejection counts from historical
rejections/superseded rows using one shared interpretation, and use the queue's reader identity for totals.

Probes: `qualified_class`, `historical_rejections`, `reader_report_totals`. Snapshot supplies the real
overlap count and comparison totals.

### R15 — P1: the distributable wheel omits the backend package

Location: [pyproject.toml:17](../../pyproject.toml#L17).

`packages = ["claimstone"]` omits `claimstone.runners`. An offline wheel built from a temporary copy
contains zero runner files. Importing `claimstone.runners` from that wheel in Python with `-I -S` fails
with `ModuleNotFoundError`. The editable checkout masks the omission. Docker builds with `pip install .`,
so the deployed artifact must be checked independently of tests that import the source tree in `/app`.

Repair: include engine subpackages explicitly or via constrained package discovery, keeping private
`projects/` and `store/` excluded. Validate imports and CLI backend discovery from the installed artifact.

Reproduction: `reproduce_wheel_2026_09_28.py`. No image was rebuilt or service changed.

## Validation and reproducibility

The required baseline checks were run before this review's additions, and repeated afterwards:

- `.venv/bin/pytest -q`: **743 passed, 7 skipped**.
- `.venv/bin/claimstone validate --all-projects`: **four projects OK**.
- `.venv/bin/python tools/check_instrument_versions.py`: **7 instruments acknowledged**, exit 0.

Those checks validate the existing test cases, input shapes, and recorded version mentions. They do not
audit completion, evidence scope, all behavioral invariants, the installed wheel, or whether instrument
code changed without its version changing. The version checker explicitly describes itself as a reminder,
not a correctness proof. Its passing result found no undocumented declared version to fix first.

Reproduce all counterexamples without touching the real store:

```bash
.venv/bin/python docs/reviews/reproduce_review_2026_09_28.py
```

**22 of 22 requirements fail on the reviewed code**, exit 1. Each probe asserts the intended behavior;
`FAIL` means the defect still reproduces. Writes go exclusively to temporary stores, and the only
adjudications in the probes are explicitly synthetic fixtures. After repairs these assertions should
become ordinary regression tests and pass.

Read the real measurements independently, without registering a registry or writing stage outputs:

```bash
.venv/bin/python docs/reviews/reproduce_review_2026_09_28.py --snapshot
```

Check the wheel with the host Python, which already has setuptools (the project venv does not):

```bash
python3 docs/reviews/reproduce_wheel_2026_09_28.py
```

This exits 1 on the missing backend package. It copies the source into a temporary directory, builds
offline, and excludes editable import hooks from the import check. No dependency is installed.

## Recommended repair sequence

1. Protect signing and finality first (R01/R03/R04/R13). Preserve Q04's historical profile, but stop
   presenting it as complete while its relevant extraction failures remain unresolved.
2. Repair the numeric gate and record the instrument change (R02); measure the actual re-harvest rather
   than guessing its effect. A current-reading/supersession policy is necessary before trusting that run.
3. Repair authoritative results, annotation identity, chunk generations and full-result review
   (R05/R06/R09/R10), so replay does not silently select, duplicate or misattribute evidence.
4. Repair redirect conduct, request accounting, consistent class admission and audit replay
   (R07/R08/R11/R12), with offline transports and declared fixtures before any operator-approved sweep.
5. Fix the distributable artifact and reporting breakdowns (R15/R14), then rerun baseline, new regression
   cases, a read-only store audit and an installed-artifact check.

Code changes that alter an instrument must carry the dated version and measured design entry required by
the repository. Historical ledgers must remain append-only. The owner still decides Q04's adjudication,
floor revisions and paid reviewer work. Europe PMC/JATS and reviewer scaling remain separate next projects;
adding either would not repair the validity gaps above.

This is a static and offline functional review of the CLI, stage orchestration, gates, storage, model
boundary, parsers, reports, config and packaging, with focused executable counterexamples. It does not
establish live publisher behavior, backend quality, human scientific ground truth, or exhaustive freedom
from defects.

## Repair progress through D47 (2026-09-28)

R01/R03/R04/R13 are repaired by D45; R02 and gate-outcome supersession by D46. D47 repairs R05
(authoritative replay, preservation of provenance failures and immediate invalidation of cached evidence)
and R09 (immutable reader/content annotations, exact legacy-id retention and explicit review target fan-out).
The original findings above describe the reviewed baseline; they are retained as the audit record.

The probe script now follows the scoped profile/signing API and isolates synthetic signing fixtures from
extraction completeness. It reports **14 requirements passing and 8 still failing**, exit 1 intentionally.
Those failures cover full-result review, chunk generations, class admission, audit policy replay,
redirect guards, discovery failure accounting and the two report-count defects. Packaging remains a
separate open reproduction. The current required checks pass: **846 tests, 7 skipped**, six project
configurations valid and ten registered instruments acknowledged. There is no claim that the project
is fully repaired.

`tools/measure_answer_replay.py` replays every stored batch on temporary copies, preserves all original
83 review associations, and verifies zero writes on repetition and unchanged real JSONL hashes. D47
records the whole-corpus counts and their limits. The real production replay remains unapplied until
R06 and R10 are repaired. No acquisition, model call, floor change or adjudication was made.


## Repair progress through D48 (2026-09-28)

D48 repairs R06–R08, R10–R12, the remaining R14 reporting errors and R15 distribution.
Active passage manifests prevent stale chunks and old-context answers; complete annotation reviews
are versioned and digest-bound; every redirect is checked and request/query outcomes are recorded;
class rates and policy-aware audits use declared populations. QUALIFIES contributes to neither
class direction and reader totals reconcile without counting rejudgements as paid attempts.

The complete verification now passes: **878 tests, 7 skipped**, six project configurations,
16 recorded instruments, all 22 counterexamples and an isolated installed-wheel CLI import.
The two complete temporary-store replays retain D47's extraction counts, preserve all 83 historical
review ids, append zero rows on repetition and leave the real ledgers unchanged. **Zero legacy reviews
attest the new complete-annotation task.** These repairs finish the software review; production replay,
unanswered extraction, paid independent v2 review and human adjudication remain separate work.
