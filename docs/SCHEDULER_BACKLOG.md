# Scheduler backlog from supervised use

Recorded 2026-09-29. Requirements and acceptance criteria, **not an implemented scheduler**.
Manual calibration/debug remains the operator's chosen mode. Scientific rules remain in
CLAUDE.md and the measured decisions D10, D39, D48, D54 and D65–D67; this document does not
change a floor, registry, population, scientific instrument or model assignment.

## Workflow to automate

The operator supplies project files, an approved search protocol, scope and spending ceiling.
The scheduler should advance the existing stages from their recorded state. It must show what
finished, what remains and why it stopped, without requiring the operator to assemble commands.

| Step | Required behavior | Acceptance criterion |
|---|---|---|
| Preflight | Validate configuration, registry, declared population and instrument acknowledgments; check required credentials without displaying them; distinguish host and container dependencies. | Missing credentials, parser availability or changed frozen inputs stop the affected work before requests or paid calls. |
| Plan and preview | Freeze input hashes, query/API pairs, scope, limits, campaign, model identities, schemas and shared budget. Separate an offline preview from an explicitly networked metadata lookup. | Preview and execution select the same eligible work; an offline preview makes no request. Metadata lookups use the recorded transport too. |
| Search resume | Resume only missing/failed/shallow planned queries, with rate-limit backoff and provider-specific quotas. Successful capped queries require separately planned pagination or expansion. | A 429 is not an empty search; restarting does not repeat completed work or silently mark capped searches exhaustive. |
| Search quality | Detect persistently empty channels, overly restrictive exact phrases, result caps and metadata exclusions. Show these separately from acquisition. | An empty exact-phrase search cannot establish absence of literature. Known held-source checks and citation-channel inspection expose gaps; literature recall stays unknown unless independently measurable. |
| Work and copy resolution | Resolve canonical identity separately from available copy URLs. Inspect archives, declared author/institution copies and legal OA locations, including metadata excluded solely because their URL is a DOI redirector. | Finding a legal copy does not silently widen the frozen population. New hosts or policy changes produce a dated proposal for a new round. |
| Identity verification | Compare DOI/arXiv identifiers, title, authors and publication/version metadata against the downloaded document and independent authoritative records. | An upstream metadata record combining two different works becomes an identity conflict requiring resolution, even when the PDF is readable and its title matches the candidate title. Retain both original metadata and bytes. |
| Relevance screening | Apply project-supplied criteria for question, source of exposure, unit, outcome and horizon; distinguish direct evidence, methodological context, irrelevant and uncertain. Preserve reasons, references and screening version. | A classifier cannot infer relevance from host membership. A daily prediction or an annual evaluation period is not automatically a weeks/months prediction. Confirm exclusions and measure screening errors before scaling automated screening. |
| Acquisition | Try legal copies of the same verified work, record licences and held versions; reuse bytes already present. Retry terminal failures only within an authorized named campaign. | A different paper cannot substitute for a missing paper. No shadow-library route, duplicate fetch or unrecorded metadata request. |
| Failure handling | Respect robots and failure budgets for actual redirect destinations, across scheduler restarts. Separate HTTP refusal, established paywall, transport failure and exhausted local budget. | A 403 alone is not proof that the work is paywalled. A new worker/process cannot reset the effective host budget and immediately repeat refused requests. |
| Normalize | Start the parser when needed, normalize only new/changed artifacts, publish complete active chunk generations, then check identity and document confirmation separately. | Readable full text does not certify that it is the intended work. Unsupported parsing stays unresolved rather than publishing partial evidence. |
| Admission | Recompute selected-round and cumulative admission, including class floors and unresolved work. Explain the deficit and bounded recovery options. | Sources already admitted are not removed after a failed download to improve the denominator. Below-floor scopes cannot produce a scientific profile. |
| Read and review | Build outstanding tasks from active chunks; preserve original answers, gate quotes/numbers and use an independent reviewer on complete annotations. | A terminal model failure remains unanswered. Relevance screening does not silently count a skipped existing reading as completed. Changed task shapes need explicit versioning and validation. |
| Spending | Estimate the measured queue before a paid phase; account for retries, alternate readers and attempts of unknown cost under one approved ceiling. | Calibration permission does not silently authorize a full-corpus production run. Stop before a call whose reserved cost would exceed authorization. |
| Profile and handoff | Build eligible profiles only after gates pass; surface pending readings/reviews and scientific limitations; provide the human reading packet. | No automatic scientific verdict or signature. Review-label counts do not become a vote on the question. |

## Incremental operation

- Use dated update rounds plus cumulative audits. A newly discovered work may be old; retain
  discovery time, publication time, version and API provenance separately.
- Compare candidate identities, copy hashes, active document generations and task identities.
  Identical bytes and tasks reuse existing results; revised texts need the affected new readings
  and reviews. Suspected duplicates require identity verification, not automatic title merging.
- Recompute affected profiles after new evidence; previous human signatures become stale when
  their live evidence changes. Preserve the previous profile and signature.
- Support a declared periodic cadence and bounded citation expansion. Report completed queries,
  screened works, exclusion reasons, acquisition, reading and review separately. None alone is
  a percentage of literature completeness.
- Persist the work queue, leases and stop reasons; keep one writer per project. JSONL remains
  the source of truth; any scheduler database is a rebuildable read model. Resume after crashes
  without duplicating requests or spending.
- Supply one short status report: new/changed sources, unresolved identity/relevance cases,
  capped/failed searches, acquisition deficits, remaining work, spending and next required action.

## Decisions belonging to the operator

The scheduler may execute already authorized, frozen protocols and prepare concrete proposals.
It must request a decision for changed scientific selection criteria/population, changed registry
or floor, spending beyond scope/ceiling, or new sweeps outside the approved protocol. Human
adjudication remains manual. Routine resume within an existing authorization does not need a
second approval.

## Implementation order and validation

1. Define append-only identity and screening audit contracts, including supersession and how
   unresolved conflicts block downstream use. Resolve the observed identity conflict before
   further paid corpus work. [The source-selection contract](contracts/source_selection.md)
   now includes advisory append-only ledgers (D79); controlled automatic admission does not exist.
2. Measure selection on a frozen reference set containing relevant sources, irrelevant sources,
   uncertain cases, wrong-copy metadata, differing horizons and publication versions. Check
   false exclusions as well as false acceptances. A post-selected development set cannot certify
   general performance.
3. Add orchestration around existing stage APIs, with scope parity, persistent domain budgets,
   bounded OA resolution and an explicit offline/network preview boundary.
4. Validate crash recovery, budget exhaustion, redirects to blocked hosts, partial parser output,
   changed inputs and evidence updates. Then enable a periodic watcher within an approved plan.

The latest supervised case has three readable PDFs, but one has conflicting bibliographic
identity and the others do not supply direct evidence at the requested source/horizon combination.
This demonstrates why chaining the six commands is insufficient. Case details and source-specific
evidence remain in private, gitignored research audits; no internal project configuration belongs
in this public backlog.

## Additional checks from the next manual screening pass

Recorded 2026-09-29; requirements only, no automatic selection enabled.

| Check | What must be recorded and tested |
|---|---|
| Actual prediction horizon | Keep exposure window, forecast/holding horizon, evaluation period, rebalance frequency and displayed return units separate. A next-day prediction with annualized performance is not a monthly prediction. Evidence must identify the paper's own specification rather than a cited study. |
| Exposure scope and null results | A paper whose main signal is document similarity may also contain a sentiment test. Inspect secondary specifications and tables before rejecting it. A null long-horizon result must pass the same eligibility rules as a positive result. Ambiguous boundaries between filings and news stay pending; the scheduler cannot silently broaden or narrow the protocol. |
| Levels of screening | Distinguish title triage, abstract screening, targeted full-text inspection and complete scientific extraction. Save provenance, exact local passages and artifact/version hashes. These levels do not count as interchangeable completed readings. |
| Cached metadata sufficiency | Reuse recorded API payloads first. A response selecting title/DOI/year/location can lack an abstract by construction. Record missing abstracts as missing, then schedule bounded, recorded authoritative lookups; never infer irrelevance from a missing field. |
| OA location freshness | A cached OA PDF URL can return 404; a provider's `green` label can name only a DOI resolver. Record the actual file outcome separately from OA metadata, and queue bounded legal-copy recovery without counting metadata as a document. A venue/author/title variant in a held PDF requires identity assessment before reuse. |
| Triage without exclusion | Title cues may order the queue but cannot exclude an item or certify relevance. Every low-priority record remains in the queue. Report unassessed items separately from assessed uncertain items, along with a clear next batch. |
| Work, version and supplement deduplication | A held manuscript, a journal article, a DOI record and an online appendix can describe overlapping evidence. Verify their relationship using authoritative identifiers and held texts, retaining each artifact and version. Do not count them as independent studies or silently merge matching titles. |
| Parser metadata and coverage | A parser can attach acknowledgments names as authors, and abstracts/front matter may be absent from active body chunks. Compare header metadata with the actual front page; check abstract, methods, results, tables and supplement coverage before claiming complete scientific reading. Keep a missing section distinct from absence of a result. |
| Screening quality and search coverage | Measure false exclusions and false inclusions against independently reviewed, frozen cases including null results, horizon mismatches, secondary analyses and uncertain scope. Audit known-reference retrieval, citation expansion, capped queries, empty channels and excluded metadata separately. Record study-family coverage after deduplication; keep total literature recall unknown without an independent reference population. |

Acceptance for a closed selection: every inventory item has an evidence-backed disposition,
uncertain identities/scope are resolved or remain explicitly blocking, verified study/version
relationships are recorded, and the dated protocol is unchanged. Only then prepare the new
cohort and apply acquisition floors. Finishing a priority batch alone does not close selection.

## Cloud-model screening boundary requested by the operator

The operator proposes moving inventory screening to Ollama Cloud so interactive agent work
focuses on implementation and calibration. Existing cloud runners can execute structured
requests, but an experimental screening task, its prompt/schema, metadata preparation and
budgeted driver are not implemented by the manual selection audit.

Prepare a small frozen comparison before scaling. Previously inspected agent assessments are
a development reference, not independent gold or held-out validation. Include negative/null
results and genuinely uncertain exposure cases. Compare readers on identical supplied evidence;
record model, harness, prompt/schema hashes, exact passages, usage and failures. A model must
return uncertainty when evidence is insufficient, without looking up or inventing an abstract.
Keep its recommendations separate from production eligibility. Independently audit exclusions,
duplicate/version relationships and authoritative identity/copy policy; uncertain cases remain
pending. Acquire missing abstracts through the recorded transport before abstract screening.
Measure the pilot's usage and queue before estimating a full run; retain the original cumulative
calibration spending and unknown-cost reservations rather than resetting the approved budget.

D69 implements the experimental two-reader screening driver over frozen local passages,
including cumulative budget and exact evidence checks. Its hosted calls ran on the operator's
machine; the agent sandbox cannot open network sockets. Next implementation boundary: recorded authoritative abstract
retrieval for the 796 metadata-only records, work/version grouping, an independently checked
screening reference, then measured deployment without automatic source exclusion.

The first host-run pilot (D70) adds two acceptance checks before scaling: an INCLUDE must cite
the paper's actual text-derived exposure and its tested future-return horizon, and two agreeing
readers must not bypass an independent reference or the project scope rule. Three Kimi quotes
failed exact matching; preserve them as failed recommendations and version any prompt/schema
change before retrying. The production dashboard reads the project ledgers, not this separate
experimental pilot, so it must label future calibration status separately if displayed.

D71 supplies a ten-record, identity-checked abstract fetch pilot and screening prompt v2. The
scheduler must resume metadata work by campaign and candidate identity, retain raw responses,
separate missing abstracts from failed requests and identity conflicts, and stop on provider
refusal. It must never feed a conflicted abstract to a model or treat an exact quote as proof
that a paper actually measured the declared exposure. The remaining 786 records are still
pending metadata retrieval after this planned batch; no production exclusion is authorized.

The operator fixed L02's direct exposure scope to media/newswire news; corporate filing tone is
context. The scheduler must bind each screening batch to the dated selection protocol and refuse
to mix v1 and v2 recommendations as though they were produced under the same criteria.

## Requirements observed during the 2026-10-06 guided L02 batch

This batch is recorded in the private
`store/alembic-s4-lungo/audits/source-selection/l02-v2/guided-batch-2026-10-06.md`.
Its Durham recovery used a frozen plan, a sandbox DNS attempt and a bounded host retry.
The old repository host redirected its robots check to an unapproved host; the approved
Worktribe page returned HTTP 403. No PDF was obtained or imported. These are measured
workflow cases, not a new scientific selection rule.

| Work now governed by the agent | Scheduler behavior and acceptance |
|---|---|
| Choose a small next batch | Build a queue from frozen scope, current advisory observations, held copies, identity relations and previous request outcomes. Show why each case is next, its question/criterion, reading level and missing evidence. Ordering may not depend on whether a result favors a strategy. Never turn priority into an exclusion. |
| Freeze and verify the operation | Bind project configuration, selection scope, packet, AI observations, cached metadata, candidate key, allowed hosts, request ceilings and campaign name to hashes. Preview offline; refuse execution after any frozen input changes. |
| Reuse held work | Verify content-addressed PDF bytes and active chunk generation, then present exact local passages with source class and candidate/work/copy identities. A same-work DOI and title key must not become two studies. A summary quote still requires the underlying specification and table for scientific extraction. |
| Reuse readings without claiming new completion | Join `claim_records.current` to `review.current` by `claim_id`; review rows need not repeat `source_id`. In the observed batch `ACA001` had 17 active L02 claims and 17 current v2 reviews (six supported, eleven overstated), while `ACA012` had no L02 claim. Separate daily, weekly, contemporaneous, sentiment and news-attention results; do not carry an old-population claim into a new v2 profile without controlled scope checks. |
| Flag table/prose ambiguity | Preserve the PDF page and table layout alongside parsed chunks. If a table is flattened or the paper's prose calls rounded t-statistics significant at a stated threshold (as in `ACA001` Table 5, lags 2 and 6), queue a targeted reader check; do not silently convert that wording into an exact statistical assertion. |
| Keep selection levels distinct | Show `AI_PROVISIONAL`, targeted full-text context, identity uncertainty and controlled admission separately. A media/newswire criterion cannot be satisfied merely because a mixed RavenPack feed includes some media. Hard/soft event categories are not publisher-source filters. No agent judgment signs a verdict or changes the acquisition denominator. |
| Recover legal copies | Search cached authoritative locations first. Record landing pages, robots checks, redirect hops and actual bytes through the project transport. Before each hop enforce the approved host set, excluded hosts, persisted failure budget and remaining request ceiling. A newly seen redirect host stops for a revised plan instead of being followed implicitly. |
| Interpret access failures | Distinguish DNS/transport failure, robots result, HTTP 403, stale URL/404, a verified paywall, a verified purchase offer, and an identity-checked copy. The transport currently calls 403 `PAYWALL_403`; the scheduler must display this as an access-blocked request until independent paywall/offer evidence exists. A 403 creates no purchase queue item by itself. |
| Resume safely | A retry after sandbox-only DNS failure must prove that prior events had no HTTP response and must retain the failed request rows. A run stopped by an unapproved redirect may continue only with still-approved routes and the remaining aggregate request ceiling. Rechecking a terminal response needs a new named campaign and operator decision. |
| Report a bounded outcome | State attempted transfers separately from `requests.jsonl` event rows, bytes obtained, identity/gate status, unresolved cases and next useful human action. No-copy outcomes remain pending rather than excluded. The request/audit ledgers gain rows; stage-owned ledgers stay byte-identical until an explicit import. |
| Hand off to a person | Present a concise intervention: exact work/version, inspected routes, evidence for access or offer, cost/terms if verified, and the scientific criterion still unresolved. An operator-supplied PDF enters an identity and full-text gate before any admission or floor calculation. |

Automation should first provide a repeatable offline dossier and request preview. Durable
jobs, leases, project-wide writer coordination and persistent host budgets are required
before unattended requests. Controlled admission and a measured screening error boundary
are required before unattended scientific selection. The current guided campaign is a
regression fixture for all three stop paths: sandbox DNS, robots redirect to an unapproved
host, and a 403 landing page without a paid offer.

The next approved two-copy L02 check exposed a separate accounting rule. The first
candidate PDF URL redirected once on the same institutional host, so two physical
transfers consumed a guard configured as though it counted candidate URLs. The second
candidate had only a recorded robots response and no copy request. The scheduler must
track **candidate copy attempts** and **redirect transfers** separately, enforce both
limits across restarts, and show the remaining allowance in a preview. It may resume
the untouched second candidate under the same approval only after checking both the
isolated audit and `requests.jsonl`; it must never re-request the first successful copy.
The final two PDFs also provide regression cases for screening: one contains a
media-sentiment control but only a three-day return window, while the other measures
week-scale returns after publication of a raw valuation figure, not news sentiment.
Source exposure, outcome horizon and role in the model must each be checked before a
provisional exclusion becomes a controlled decision. Their private byte hashes and
exact passages are in the guided L02 audit.

An offline dossier and queue precursor now exercise the scheduler's first useful
read-only operation. For each held source, verify the raw copy hash, active document
generation, current claim quotes and independent review links, then surface known
same-work and possible-version relations separately. For the frozen inventory,
derive outstanding work from the **current** advisory view: unresolved observations,
held unobserved copies, cached metadata without an authoritative abstract, and
records needing metadata lookup. The 2026-10-06 L02 snapshot contains 813 tasks
across those four classes. A queue item must name its next action and may use
title cues only for work ordering, never for scientific exclusion or a recall claim.
Rebuilding the same snapshot must be deterministic; new advisory observations
must change the derived queue without rewriting old snapshots. A new model or
network campaign still needs its own frozen plan and budget.

After the remaining 18 held-source observations, the queue shrank from 813 to
796 outstanding tasks. It must consult verified candidate relationships before
proposing a metadata lookup: the separate DOI key for an already held work needs
controlled reuse, not another fetch. It must also check `screening_metadata.jsonl`
for retained abstracts before requesting them again. Five abstract payloads were
reconstructed and identity-checked offline in this continuation. A possible
version relation is insufficient for this reuse rule; it remains an identity task.

The authorized ten-lookup continuation returned ten HTTP 200 responses, three
abstracts and seven `NO_ABSTRACT` outcomes. The queue now routes the seven to
an alternative-authority plan instead of scheduling the same lookup again.
Recorded lookup failures require inspection before retry; a later failed lookup
does not erase an already retained abstract. The regression fixture in
`tests/test_preview_source_selection_queue.py` covers all three cases. A frozen
seven-key Crossref fallback is prepared separately; provider changes require
their own authorized campaign rather than silently extending the first one.
The operator authorized that fallback: seven HTTP 200 responses still had no
abstract. The scheduler must mark a provider pair exhausted for these candidate
keys and route them to lawful copy or operator-supplied text inspection. A
successful metadata HTTP response is not an abstract, and another automatic
request to either checked provider would add no evidence.

D72 adds a measured resume requirement: a malformed model answer is a terminal unanswered case,
not a reason to abandon all independent cases or retry the same call invisibly. The scheduler
should finish the remaining frozen work, preserve the failed bytes, and report the missing
answer. For metadata, a successful OpenAlex lookup without an abstract moves to a bounded
alternative authority; it is neither an irrelevant paper nor an HTTP failure.

D73 adds a measured semantic check for INCLUDE: exact citation of news incidence cannot stand
in for evidence that sentiment was measured from the news text. Automated acceptance needs
independent review of such boundaries; schema validity and two-model agreement are insufficient.
The scheduler must keep metadata-only records pending, prepare blinded reference packets,
and report screening error on new human-labeled cases before it can scale recommendations.

D74 adds a concrete resume case: twenty recorded OpenAlex lookups yielded thirteen verified
abstracts and seven `NO_ABSTRACT` rows. The scheduler should select only those seven for a
new, bounded Crossref campaign; after recording each outcome, rebuild the unlabeled packet
from the latest verified abstract while preserving the prior packet. It must expose the
remaining missing-text count and never infer a screening decision from a title alone.
The operator ran that fallback and it supplied all seven abstracts; the rebuilt packet now has
twenty of twenty texts. The scheduler must keep the twenty blank human decisions distinct from
metadata completeness, and wait for independent assessment before a held-out model comparison.
