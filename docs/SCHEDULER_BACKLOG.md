# Scheduler backlog from supervised use

Recorded 2026-09-29 and updated through 2026-10-09. Requirements and acceptance criteria;
the current worker implements a subset (D87–D115).
Manual calibration/debug remains the operator's chosen mode. Scientific rules remain in
CLAUDE.md and the measured decisions D10, D39, D48, D54 and D65–D67; this document does not
change a floor, registry, population, scientific instrument or model assignment.

The first implementation slice (D86) is `claimstone scheduler-preview`: a
read-only flow-scoped next-work view. It reuses the portal's inbox semantics,
flags an empty new round, protocol drift and integrity problems, and performs
no operation. The worker and append-only execution contract are described in
`docs/contracts/scheduler_operations.md`. The dated entries in `docs/HANDOFF.md`
state which operations have actually been exercised.

2026-10-09 retrieval calibration (D117): an authorized six-request L02 variant
probe returned 100 OpenAlex, 100 Crossref and 6 arXiv rows. The 172 distinct
candidate keys and 34 multi-provider keys are retrieval observations, not
screened studies. New discovery runs now retain every query-result path in
`query_hits.jsonl`, including duplicates and out-of-population rows. Scheduler
work still needed: freeze and measure query variants with known-reference
checks; plan bounded cursor pages for capped queries; compare provider yield
after identity/version checks; avoid interpreting a 100-row cap or exact-phrase
zero as complete coverage. Historical query hits have not been backfilled.
Keep this calibration outside the production L02 round until a dated search
protocol and population decision are made. Retry/backoff must respect the
named campaign, physical ceiling, host failure budget, and provider credits.

## Workflow to automate

The 2026-10-06 repository expansion exposes a round boundary the scheduler
must retain. The project population v2 and new L02 round were frozen with two
exact university hosts before any copy request. Existing DOI-keyed discovery
observations still name `doi.org`: a copy URL found later does not change their
round or pass the metadata host selector. The scheduler needs controlled
candidate intake that records the authoritative DOI, the institutional copy
route, the declared source class and their provenance without moving an old
round's candidate. It must show a newly declared round with zero candidates as
empty, not as a completed cohort or an acquisition rate of zero. Old plans
must remain replayable against their archived v1 policy after a dated v2
configuration change; an unrelated class or floor change must still fail.

The completed bounded copy check adds two distinct stop states. A repository
landing can explicitly say that no file is available; record that statement
with the retained HTML hash as `NO_REPOSITORY_FILE_DECLARED`, instead of a
generic missing-PDF-link state or a paywall. A university discussion paper
can share title and author with a later DOI publication while its version
relationship remains unverified; preserve `POSSIBLE_VERSION` and inspect the
copy before reusing its screening as evidence for the DOI. A handle resolver
whose final host is unknown needs a separately bounded, approved route; do
not treat its repository label as an allowed destination host.

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

The next offline pass checked eight additional cached abstracts against their
recorded payload hashes. Three were newly fetched OpenAlex abstracts and five
were older locally retained records. The two one-quarter prediction abstracts
have separate DOI keys but near-identical titles and text; they remain separate
provisional candidates until a work/version relationship is established. The
scheduler must compare DOI, title, author, venue, publication/version data and
the held text before it counts them as independent evidence. Record an
OpenAlex provider from its request/campaign provenance even where the metadata
row omits an explicit provider field; do not weaken the raw-payload or exact
abstract checks to accommodate that representation. The resulting view has 47
observed of 830, 783 unobserved, six uncertain observations and a fresh 789-task
queue. No observation admitted a source.

An offline review of cached location metadata for eleven works with no abstract
from either checked provider found 52 URLs, all outside the project's exact
frozen host selector. Some appear to be university repositories or a research
institution, but provider OA labels do not verify copy identity, authorship,
robots permission or eligibility under the declared population. The scheduler
must show these as `OUTSIDE_FROZEN_HOST_SELECTOR`, retain their source payload
hashes and stop before requesting them. `sources.yaml` requires a dated operator
population decision and a new round before any newly named university/author
host can enter the acquisition population. Preparing a metadata-derived URL is
not authorization to fetch it.

An offline comparison of two separately keyed L02 candidates found same-author,
near-identical titles and matching abstract statements about a 900,000-story
dataset and a one-quarter weekly-news horizon. Their records identify an SSRN
2013 item and the 2017 *Financial Analysts Journal* version. Treat them as one
possible study family for planning, not two independent works; require copy-level
identity evidence before writing a production identity relation or transferring
source observations. The OpenAlex abstract is an inverted index and must be
reconstructed before exact-text comparisons. The audit records this as
`POSSIBLE_VERSION` without changing selection or admission.

When cached copy routes fall outside the exact population hosts, the operator
decision has two parts: approve a dated population revision/new round for named
eligible host(s), then separately approve any bounded network campaign. A
resolver such as `hdl.handle.net` is not the final repository host; inspect its
redirect target under a specifically bounded plan, stop on an unapproved host,
and do not add a wildcard. A commercial research host such as BBVA requires
evidence that the copy meets the existing author/institution rule before it is
proposed for inclusion.

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

## Implementation ledger, 2026-10-07

The first executable slice is `claimstone scheduler`: exact offline plans for
normalize, scoped extract/review queue construction and profile synthesis.
It records authorization and completion in `operations.jsonl`, checks frozen
inputs and reuses completed results. It can drain bounded local llama.cpp or
explicitly budgeted Ollama Cloud
queues, attempt candidate URLs, and run scholarly API queries under exact
authorized hosts and per-unit request ceilings. Batch planning and approval
allow a worker to process several such units unattended. It cannot yet run
full open-access acquisition cascades or automatically plan paid lanes. The
operator-invoked `scheduler drive` chains the scoped local stages under a
total call cap and stops at network/floor/human gates.

The 2026-10-09 local mandate slice adds `scheduler auto-enable`, `auto-once`,
`auto-worker`, `auto-status` and `auto-disable`. One approval covers recurring
scoped local passes with a cumulative model-call ceiling that survives
restarts. It executes only independently authorized external plans; it neither
schedules a new search/copy request nor renews its own allowance. Its network
proposal policy is separate from the later finite schedule. Safe search-page
and copy planning, incremental source selection and an end-of-run dossier
remain. The local mandate authorizes no periodic network campaign.
Batch planning now scans past already settled query/candidate identities before
applying its actionable-unit cap (D120), so repeated plans can reach later
terms. It still does not generate cursor pages or approve a new sweep.
The D121 coordinator now uses that planner after every pass when a version 2
mandate names exact search/copy proposal limits. It reports pending batch IDs
but leaves them unapproved. D123 adds a finite, revocable, operator-approved
network schedule for batches already frozen, with exact UTC windows and a
summed lifetime physical-request ceiling. Remaining for periodic autonomous
research: safe cursor depth, broader legal-copy resolution, cumulative evidence
profiles and a concise end-of-run dossier. D124 prepares finite dated update
rounds and audits each round plus whole-corpus admission; it does not yet merge
question-level evidence into a new cumulative profile. The schedule cannot
approve candidates that are not yet known. D125 adds a separate finite policy
for later candidates with matching scheduled query hits, exact approved HTTPS
hosts/classes and lifetime caps; other locations still need a new campaign.

The following duties still need executable units:

- Bounded discovery and acquisition plans must freeze exact work identities,
  allowed hosts, robots/redirect ceilings and retry campaigns. Reconcile
  request and stage ledgers after interruption before restarting a unit.
- Use the pinned-public-address transport for every approved network unit;
  never fall back to an unpinned fetcher on a redirect or DNS failure.
- Count physical requests and host failures across restarts, including robots
  and redirects, against the approved ceiling and TTL.
- Drain model queues with explicit backend/model/harness, per-call reservation,
  cumulative spend ceiling and unknown-cost accounting. Keep extract and
  review readers distinct, and retain failed answers as unanswered units.
- Connect the operation ledger to a background worker and the authenticated
  control service. Record heartbeats, stop requests and resource limits; expose
  status and live events without granting a portal process direct write access.
- Turn access refusals into a separate, verified copy-offer and human intake
  workflow. The operator decides any purchase; a supplied copy's effect on
  the floor must follow a declared project policy.

## Provider integration review, 2026-10-07

The operator-supplied guides in `docs/tools/` were compared with the current
searchers, resolver, transport and D65–D67 measurements. These are scheduler
duties and proposed experiments, not permission to alter a frozen round or
start a network campaign.

| Priority | Scheduler duty | Acceptance evidence |
|---|---|---|
| Before another arXiv campaign | Enforce one legacy arXiv API request at a time and at least three seconds between requests across workers under our control, including robots/API requests. The current generic fetcher waits only 0.34 seconds per instance. | A concurrent-worker test proves a shared limit; recorded physical request starts respect it. See `https://info.arxiv.org/help/api/tou.html`. |
| Before relying on arXiv zero hits | Freeze separately authorized query variants: exact phrase, title/abstract terms joined with `AND`, and justified synonyms or categories. Keep the old exact-phrase results and protocol intact. | On a known-source reference set, compare unique verified works, irrelevant results and request cost for each variant. A zero-result exact phrase never closes literature recall. D66 measured 19 such empty queries. |
| Before broad Crossref expansion | Test `query.title` alongside current `query.bibliographic` in a new dated search protocol, with separate query identities and a fixed result/request cap. | Compare retrieval of known relevant works and marginal unique candidates. Do not rank or exclude studies solely by Crossref score or a query's top-N position. |
| Before multiple workers or automatic retries | Apply provider-aware shared rate limits and bounded backoff to 429/5xx/timeouts. Reconcile `request_started` and query/acquisition rows before a retry; a retry consumes the same approved physical-request ceiling or needs a new named plan. | Restart and concurrent-worker tests show no unrecorded request, no over-ceiling retry and no 429 interpreted as an empty search. Crossref's 2025 list-query polite limit is 3 requests/second, below the new guide's suggested 8. See `https://www.crossref.org/blog/announcing-changes-to-rest-api-rate-limits/`. |
| When repeating DOI lookups | Reuse retained Unpaywall/OpenAlex responses by DOI and retrieval date; allow bounded refresh because OA locations change. Keep previous raw bytes and distinguish 404, `closed`, an OA landing page and a failed PDF transfer. | Two rounds can reuse a fresh record without a new request; a stale or failed location produces an explicit refresh proposal, not a silent permanent exclusion. |
| Before version-sensitive deduplication | Store arXiv's canonical base ID, returned version and explicit work/version relationships alongside title and DOI. Do not change `candidate_key_version 2` silently or merge by title alone. | A v1/v2 pair and a preprint/journal pair stay traceable as artifacts without becoming two independent studies by accident. |
| For search monitoring | Report per-query caps, unique-key yield, known-reference retrieval and metadata exclusions. Use diminishing yield to propose a stop, never to claim measured literature completeness. | Preview shows remaining unsearched/deeper queries and the operator can inspect a proposed stop against the frozen protocol. |

Already in place: Crossref `mailto` and identifying User-Agent; Unpaywall DOI
lookup and its best/all OA locations; PDF-first fallback, recorded licence and
version, content checking, raw request retention, idempotent candidate writes,
host refusal budgets and bounded scheduler authorization. The guides' OAI-PMH
mirror, vector database, mass PDF download and paid bulk feeds have no measured
benefit at the present scale and are not implementation prerequisites.

### OpenAlex guide comparison, 2026-10-07

The new `docs/tools/openalex_integration_guide.md` was checked against the
current OpenAlex searcher, DOI/copy resolver, bounded operation planner and
official 2026 authentication, pricing, search and corpus documentation. The
existing key is sent as a bearer token only to HTTPS `api.openalex.org`; raw
responses are retained. The query's `mailto` parameter is legacy and ignored
by the current OpenAlex API, so it must not be counted as authentication.

| Priority | Scheduler duty | Acceptance evidence |
|---|---|---|
| Before unattended OpenAlex expansion | Freeze an API-use ceiling alongside physical request ceilings, record OpenAlex's per-call cost and remaining daily credits, and stop when the approved boundary is reached. The current `budget_cents` applies only to Ollama Cloud model drains; an OpenAlex key may also have prepaid credits. A local estimate cannot guarantee free-only use when other clients share the key, so require a provider-side spending cap or a dedicated key without prepaid credit for that promise. | A simulated depleted free quota stops or follows an explicitly authorized paid policy. Usage is attributed to the exact operation; 429 from quota exhaustion stays distinct from an empty result. Check response headers and the documented `meta.cost_usd` field, accepting only shapes proven by fixtures. |
| Before widening a search protocol | Compare the current broad `search=` query with `search.title_abstract_keywords`, controlled boolean/proximity variants and, if vocabulary is uncertain, a separately bounded semantic query. Freeze `corpus=core/all`, query mode, filters, sort and per-page cap in each plan. | A held known-work set measures unique relevant retrieval, noise and API cost. Changing query mode or corpus creates a dated round/protocol rather than silently altering earlier denominators. No semantic result is auto-admitted. |
| For capped OpenAlex queries | Record `meta.count`, page/rank and result cap. Offer separately authorized cursor pages or a narrower query; save the returned cursor exactly for interrupted work. Do not raise `per_page` to 100 when the operator intentionally capped a pilot at 10 or 25. | A capped first page is reported as incomplete search depth, never complete literature coverage; restart does not repeat a page or exceed the approved page/request ceiling. |
| For identity and provenance | Retain the OpenAlex Work ID and all query-hit observations alongside DOI and source/copy URLs. Treat Work identity and legal copy identity separately; check upstream merge/split errors against the document. | Two queries finding one Work preserve both query paths, and a mismatched copy remains blocked despite matching OA metadata. Changing candidate keys requires a versioned measured migration. |

At current volume, the guide's snapshot, daily sync, paid membership, universal
`per_page=100`, reranking every result and OpenAlex content-download endpoint
are not prerequisites. The existing `select` includes `primary_location` and
`open_access` because this project's frozen metadata population needs them;
dropping those fields for a thinner first pass would change selection behavior.

2026-10-09 implementation status (D112–D117): shared on-machine provider pacing for
arXiv, Crossref and OpenAlex is in place, including one concurrent connection
per provider and recorded start reservations. OpenAlex quota headers and
returned cost fields are retained in request rows; a 429 with zero remaining
credits is explicitly labelled. Local cumulative OpenAlex free-credit
reservations are implemented (D115). Still pending before unattended expansion:
bounded retry and backoff under the physical-request ceiling, production
search-strategy selection from measured relevance, cursor depth, and verified
work/version relationships. The shared lock covers workers
using one mounted store, not separate machines.
`discovery_version 4` now retains OpenAlex Work IDs and one-based rank on new
candidate rows and records `meta.count`, `next_cursor` and first-page capping
on query rows (D113). Following cursors under a new authorized page ceiling,
remains pending for the scheduler. The D118 isolated pilot can follow page 2
of a saved 100-row query using basic paging because OpenAlex reported 1,055
results, below the documented 10,000-result basic-paging limit. A new search
that needs cursor depth must start with `cursor=*` on its first page and freeze
each returned cursor; it cannot splice a cursor into the previous basic-page
result set. New discovery runs retain every query path in
`query_hits.jsonl` (D117); historical rows remain unbackfilled.
The authorized D118 second-page check returned 100 new keys without exact
overlap with page 1 and one new exact identity from a 20-case reference packet.
The scheduler still needs an approved, resumable page operation before it may
perform this automatically; the pilot's isolated audit does not authorize
future pages or add the 200 results to the frozen L02 candidate population.
New arXiv candidate rows now retain the base ID and returned version (D114);
explicit preprint/journal and version relationships remain pending.
`fetch_version 7` now reserves estimated OpenAlex credits against a shared
10,000-credit UTC-day ceiling before transport (D115). This closes the local
Claimstone-only credit ceiling; it does not prove free-only operation for a
prepaid key shared with other applications. Provider-side spending controls
and an account-level policy remain an operator/deployment prerequisite.
