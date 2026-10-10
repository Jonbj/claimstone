# Handoff

Written 2026-09-28, after the first end-to-end round; completeness corrected by D45. It holds what the
repository does not: live state, pending decisions, and the things that were established in conversation
and would otherwise be lost.

`CLAUDE.md` is the contract and overrides this file wherever they differ. `AGENTS.md` says what to read in
what order.

## Where the work stands

2026-10-10 finite network schedule (D123): existing frozen discovery or
acquisition batches may be placed in exact UTC windows under one summed
physical-request ceiling and approved once by the operator. `schedule-plan`
is offline; `schedule-authorize` records the approval, and `schedule-revoke`
stops later starts. Direct execution and polling both enforce the window.
This change created no schedule for a real project and made no network
request. Unknown future candidates, new search rounds and scientific
decisions still cannot be preapproved by this schedule.

2026-10-10 coordinator proposals (D121): version 2 local mandates may include
exact discovery APIs/hosts, copy hosts and per-batch caps. `auto-worker`
automatically prepares the next bounded discovery/acquisition batches after a
pass; `auto-status` lists batch IDs awaiting approval. These are planned rows
only. The operator still authorizes each exact batch before the worker may
make requests. No recurring network sweep, new round, live mandate or real
request was created by this development.
The control server now lists and authorizes whole frozen batches in one
authenticated action (D122); its POST repeats the exact operation IDs and
request ceiling. The parallel frontend session has not been changed here.

2026-10-09 standing local coordinator (D119): a flow may receive one
`scheduler auto-enable` mandate with two distinct local models and a lifetime
call cap. `auto-worker` revisits the flow, executes already authorized external
operations, and advances local normalize/extract/review/profile work; each
model call is reserved before execution and the cap survives restarts.
`auto-disable` stops later passes. This does not authorize a recurring network
campaign, paid model calls, source admission or a verdict. Recurring search,
copy planning and a completed dossier still need implementation and an
operator-approved policy. No mandate was issued for a real flow in this work.

2026-10-09 retrieval continuation (D118): offline comparison of D117's saved
responses against the 20-case L02 packet found three exact DOI identities and
one same-title, different-DOI version hint. This is not a relevance or recall
estimate. A separate, bounded OpenAlex page-2 plan is frozen at
`store/alembic-s4-lungo/audits/research-search/variant-probe/page2-plan-2026-10-09-v1.json`
(SHA-256 `6765e6f55fd1cc04a1e7cce6c46c749a7c62f5db5f0beb257488b76f7742ffbd`).
It allows one API request and one robots check, estimated at 10 OpenAlex
credits. The operator authorized it; both requests completed. Page 2 returned
100 keys with zero exact overlap against page 1 and one additional exact DOI
from the 20-case packet. The content-addressed readout is
`store/alembic-s4-lungo/audits/research-search/variant-probe/page2-readout-cabf123f6e96dbd62f5656324c3f400a01cad55f89d9ce3b8828373bebda211a.json`.
No production candidate or query row changed. A further page needs a new
bounded campaign and operator authorization; do not treat 200/1055 provider
results as a literature coverage rate.

2026-10-09 isolated retrieval calibration (D117): the operator authorized a
bounded L02 search-variant campaign. Three API calls plus three robots checks
completed; the frozen private plan and saved-byte readout are under
`store/alembic-s4-lungo/audits/research-search/variant-probe/`. It did not
change the L02 round or admit candidates. The backend branch
`provider-retrieval-campaign` adds `query_hits.jsonl` to preserve every
keyword-result path on future discovery runs. The frontend work in the
parallel session remains outside this branch. Search expansion, pagination,
known-reference evaluation and a dated production protocol remain pending.

2026-10-08 one compose, full GROBID (D110): `docker compose up -d --build` starts GROBID, `api`, `control`
and `web` (http://127.0.0.1:8788/); the engine job and the trial scheduler keep their profiles, and the trial
worker's container was removed. GROBID is now `grobid/grobid:0.9.1-full` (pinned by digest) on the GPU.
Documents read before today keep their legacy TEI and figures; every new PDF row names its image in
`pdf_parser`, and re-reading old PDFs with the full build is an explicit `normalize --force` — an operator
decision, because it moves the D7 figures.

2026-10-07 portal backend B0–B13 (D89, D99–D108): `claimstone control` is the authenticated write
boundary beside the read-only API. It handles operator sessions, signing from the web with drafts, intake
of DOIs, links and files (quarantine, the engine's own gates, `supplied_copies` policy, default
`separate`), decisions on identity, retry campaigns and verified purchase offers, Today, export and
verify, administration checks, and authorizing scheduler operations as the session's operator.

`./portal.sh` now starts `api`, `control` and `web`. The first run rebuilds the image to add
`poppler-utils`. Before any write, record an operator with `./portal.sh operator add ID --name "Name"`.

Not built, with reasons in the decision entries:
- intake URL fetch (D102), pause, resume and heartbeat (D107): they wait for the scheduler track;
- project creation from the web: it writes `projects/` and needs a decision;
- the React pages for these routes: next.

2026-10-07 portal frontend v2.1 (D109): the React pages for the control routes exist in `web/`. Routes:
`/` Today, `/projects`, `/p/:project`, `/p/:project/f/:sel` (the flow journey with "Right now" and
Authorize), `.../q/:qid` (the reading desk with the signature panel and drafts), `.../claim/:cid`,
`.../source/:key`, `.../export`, `/admin`, `/login`; `/u/` selectors are read-only. Every write goes
through `web/src/lib/control.ts`, the only file allowed a non-GET request (a test enforces it); the CSRF
token is held in memory only. Left out because no API gives the data: the 8-step journey bar, topic
descriptions, money figures per project, worker heartbeat, "opened N of M" on the reading desk, and
pause, resume and the paid test call (shown disabled with the server's 501 reason). The F5 pages
(Decisions and Add material, `/decisions` and `/material`) come from the parallel branch
`portal-frontend-f5` and their routes are wired when it merges; until then those links reach the 404 page.
Nothing was checked in a browser: no server was started, only the vitest suite and the build.

No real project declares `supplied_copies`, so operator-supplied copies are reported separately from
the floor until the operator decides otherwise in `sources.yaml`. That would be protocol drift for any
bound flow, by design.

2026-10-07 L02 arXiv batch: the operator authorized batch
`5154d5409788a992b69540a2db8054b5b85738f246e56025117d3282f1898562`.
Both frozen T01 queries completed with HTTP 200 and zero returned records.
Each campaign made two physical requests (robots and API), four of six
authorized in total. The round remains at zero candidates. D66 had already
measured that the arXiv searcher quotes a whole multiword term as an exact
phrase and obtained zero across nineteen queries; these two new empty phrase
searches repeat that known recall limitation. They do not support a claim
that arXiv or the wider literature lacks relevant work. Do not spend another
campaign on the same grammar without a separately versioned search design.

2026-10-07 L02 scheduler discovery retry: authorized plan
`5ff7c4cc24cd05aa0f827a21d8efdbba8bd29aa092e6acb4d541656c8b609ab6`
ran outside the sandbox. OpenAlex returned HTTP 200 and ten records for
`news sentiment predicts stock returns weeks`; the ledger records two physical
requests, robots and API, within the three-request ceiling. All ten records
were rejected by the round's frozen metadata population (`no_declared_metadata_match`):
their discovery locations were DOI, journal or other undeclared hosts. The
round still has **zero candidates**. This is not a finding of zero relevant
literature: the searcher's primary location does not establish whether an
eligible institutional copy exists. A separate controlled intake route is
still required for those works. An offline arXiv batch plan, ID
`5154d5409788a992b69540a2db8054b5b85738f246e56025117d3282f1898562`,
contains two T01 terms, at most ten results each and six physical requests
total to `export.arxiv.org`; it has not been authorized or executed.

2026-10-07 first live scheduler query: the operator authorized plan
`66b7e73da7fffd60895662dbb097e0e1385f78f1e31041f1d224f79e64793d19`
for one L02 OpenAlex T01 query, at most ten results and three physical
requests. Sandbox DNS blocked it before any HTTP request (`NON_GLOBAL_ADDRESS`);
the query ledger records `ok: false`, `returned: 0`, and there are zero
`request_started` rows for the campaign. These are not zero literature hits.
The host resolves to global addresses outside the sandbox. D97 and
`operations_version 3` allow a separately authorized, named pre-transport
retry bound to that failed row. No copy, model call or purchase occurred.

2026-10-07 scheduler implementation (D87–D93): the project-wide writer lock,
persisted host-failure budget, pinned public-address transport, round-scoped
normalize/extract/review builders and append-only operation ledger are in
place. `claimstone scheduler` can freeze exact one-query and one-candidate
network plans, group them with summed ceilings, record an operator's local
authorization, and run approved units through `tick` or a polling `worker`.
It can also build/harvest scoped queues, drain bounded local llama.cpp calls
and explicitly authorized Ollama Cloud calls under cumulative reservations,
and use `scheduler drive` for a single operator-invoked local pass through
normalize, extraction, review and profiles. A physical request without its stage outcome refuses
automatic retry. No live scheduler campaign or model run has been launched.
The portal remains read-only; automatic paid-lane planning, human copy offers/intake,
portal controls and full autonomous stage planning remain pending. See
`docs/contracts/scheduler_operations.md` and `docs/SCHEDULER_BACKLOG.md`.

2026-10-06 scheduler first slice (D86): `claimstone scheduler-preview PROJECT
FLOW_ID` is an offline, read-only next-work view over a bound flow. On the new
L02 repository flow it reports zero candidates and proposes bounded discovery
or controlled intake; it cannot close the cohort or authorize execution.
The original operation event and resume design is in
`docs/contracts/scheduler_operations.md`; the 2026-10-07 entry above records
the implemented subset.

2026-10-06 portal frontend and containers (D84): the portal now has a React + shadcn/ui + Tremor
frontend (`web/`) over the read-only JSON API `claimstone api`. `./portal.sh` starts both in
containers, at http://127.0.0.1:8788/; stop them with `./portal.sh down`. The API mounts the
store read-only, has no internet access and holds no secret. Q04's adjudication card, with the
hash above, is on the whole-store page `/p/pmc-screen-time/u/-/q/Q04`. Built in steps by GLM;
each step was reviewed and corrected by Claude Code, as recorded in
`docs/superpowers/plans/2026-10-06-portal-frontend-progress.md`. Nothing in the portal writes,
signs or starts work.

2026-10-06 L02 university repository round (D83, D85): the operator authorized a new
dated population. `projects/alembic-s4-lungo/sources.yaml` now declares
population v2 with two additional exact hosts, `eprints.soton.ac.uk` and
`diskussionspapiere.wiwi.uni-hannover.de`, selected from retained OpenAlex
copy locations and matching author affiliations before any request. The new
round `s4-l02-repository-copies-2026-10-06-v2` is frozen in
`populations.jsonl` under policy SHA-256
`f53ed0699c770079d9d97e7992d661b14fb8448dd0600ba1ae3966a58d0b43ed`.
It currently has zero candidates and zero acquisition attempts in that new
round. Its flow ID is `ec6025eff94d39c25429eccc072decdeda5c2aa3ae59330abed12cb42e987700`
and its state is `CURRENT`; this binds the protocol but does not close a cohort.
The v1 and v2
source-policy bytes are preserved under private
`audits/source-selection/population-policies/`, with declaration audit
`declaration-d1a5822d739c35e24ec9dd6d820ca96db2b6b22fb15bdca520b90f4901568912.json`.
Old v1 copy and screening plans preview against the archived v1 policy; the
original rounds and denominators have not moved.

This population is a discovery metadata selector: adding a university copy
host does not import any DOI-keyed work whose discovery URL is `doi.org`.
Controlled candidate intake still needs its own evidence-backed source route,
identity and selection checks. `hdl.handle.net` and BBVA remain outside the
new selector. The operator approved and executed the two-target copy-inspection
campaign frozen at
`audits/source-selection/l02-v2/repository-copy-check-2026-10-06/plan.json`,
SHA-256 `07f1176800b6fc940dfe78aa0a386dcc4ccbf125b1d2e002613527a9f0e9d72f`.
It made three physical page/copy transfers and two robots transfers, within
its ceilings of five and four. Hannover supplied a readable 2008 discussion
paper (PDF SHA-256 `a1ff57d0107ab97ed5dec497ec313147561ccc04460ea9b7e052358021896385`).
Its consumer-confidence exposure and aggregate country returns are outside
direct L02 media/newswire evidence. One full-text `AI_PROVISIONAL` exclusion
and one `POSSIBLE_VERSION` relation to the 2009 DOI were appended; replay writes
zero rows. Southampton returned an HTML record that explicitly says it has no
files for download. Its recorded status is `PDF_LINK_REVIEW_REQUIRED`; the
offline readout clarifies `NO_REPOSITORY_FILE_DECLARED`. A UCD handle is a
separate unverified route requiring a new bounded plan and authorization
before any request. The content-addressed readout is
`audits/source-selection/l02-v2/repository-copy-check-2026-10-06/readout-201241852336d5c697a07d7631b5257959048864038ce4c4bf8bb587d02acb94.json`.
The current L02 selection view has 48 observed and 782 unobserved keys of 830,
three provisional direct candidates and six uncertain; zero admitted and an
open cohort. The offline queue has 788 remaining tasks. No profile or verdict
changed.

2026-10-06 research portal, phases P0–P2b implemented: the canonical selector
(`claimstone/scope.py`) now scopes every per-round figure in `round_state` (claims, reviews,
chunks and the stage's own confirmation count no longer leak across rounds, review F1/F3;
admission itself still reads confirmations and repairs project-wide, disclosed and unchanged), a
damaged ledger surfaces as
a named error with its figures withheld instead of zero (F2), `claimstone flow` binds a round
selector to digests of the protocol it runs under (`flows.jsonl`, `docs/contracts/flows.md`),
`claimstone portal` serves every project read-only on loopback (GET only, Host/Origin checked,
D82), and `claimstone export` / `export-verify` freeze one flow's ledgers at a byte prefix and
verify by prefix plus recomputation (`docs/contracts/exports.md`). The same day an
implementation review (`docs/superpowers/specs/2026-10-06-research-portal-implementation-review.md`)
fixed the findings it reproduced. The main one: Q04's current profile, recorded under the whole-store
selector, was invisible in the portal and is now at `/p/pmc-screen-time/legacy/-/`. Test count as
printed by pytest after the review: **1191 passed, 7 skipped**. No ledger under `store/` was rewritten, no network request
and no model call happened; the only live-store interaction was read-only (page-time
measurement in D82).

2026-10-06 guided L02 continuation: a private, offline batch read two held PDFs against
the frozen v2 media/newswire exposure rule. `ACA001` is a strong direct candidate with
verified held bytes and a previously evidenced same-work DOI relation; `ACA012` has
monthly results but uses a mixed RavenPack feed, and its hard/soft split is by event
category rather than publisher. These remain agent observations, not controlled
admission or human reference. The operator approved a two-landing, one-copy Durham
recovery for an AI-uncertain UK paper. A sandbox DNS attempt was recorded; the host
retry stopped at an unapproved robots redirect, and the other approved institutional
landing returned 403. No PDF, paid offer, stage admission or verdict resulted. The
private readout and plan are in `store/alembic-s4-lungo/audits/source-selection/l02-v2/`;
the concrete scheduler duties observed here are in `docs/SCHEDULER_BACKLOG.md`.
The subsequent current-view join corrected a raw-ledger counting mistake: `ACA001`
has 17 current L02 claims and 17 current v2 reviews, six supported and eleven
overstated; review rows link by claim ID rather than repeat source ID. The six are
annotations from one work. A targeted Table 5 reading flags a rounded-t-statistic
ambiguity for negative sentiment at lags 2 and 6. `ACA012`'s held Appendix B
confirms the hard/soft split is by event category, not publisher source; no
media/newswire-only result was located in that version.

The operator then approved a frozen two-copy check of provisional abstract
exclusions. Toronto's accepted manuscript for `10.2308/accr-51865` and Modena's
open article for `10.1080/23322039.2016.1142847` were obtained through recorded
institutional routes and passed the full-text gate. Each PDF itself gives matching
DOI, title and authors. Toronto contains RavenPack traditional-news sentiment,
but its return test covers the three-day earnings-announcement window. Modena
tests weeks of returns after newspaper publication of price-to-book figures,
without measuring sentiment. Neither supplies direct L02 v2 evidence; both
original Claude exclusions remain `AI_PROVISIONAL`, with no production import.
Toronto's same-host redirect exhausted a physical-transfer guard before the
second PDF request; a one-time resume verified that Modena had received only a
robots response, then fetched that already-approved copy. The private guided
readout has hashes and evidence; the scheduler backlog records this resume case.

The next offline continuation built a content-addressed `ACA001` dossier from
the held PDF, 18 active chunks, 17 current L02 claims and their six supported/
eleven overstated reviews. It appended one full-text `AI_PROVISIONAL` direct
candidate observation and one verified title-key/DOI same-work relationship
to the advisory source-selection ledgers. Idempotent replay wrote zero rows.
The distinct 2013 SSRN DOI remains a possible version. The v2 view now has
21 observed keys, one provisional direct candidate, four uncertain and 809
unobserved; no candidate was admitted. An offline queue snapshot contains
813 tasks (18 held readings, four uncertain, 379 cached-metadata abstract
checks and 412 metadata lookups). Table 5's separate sentiment estimates need
complete extraction/review; rounded t-statistics at lags 2 and 6 remain
ambiguous. The hashes, exact passages and queue path are in the private guided
readout. Do not use this single candidate to close the cohort or sign L02.

The remaining 18 held sources were subsequently reassessed under v2 with
active-chunk quote checks: 17 provisional context observations and one
uncertain mixed-feed observation (`ACA012`). `ACA006` and `ACA015` now remain
context specifically because v2 excludes filing tone from direct exposure.
`tools/record_l02_held_v2_observations.py --apply` wrote 18 advisory rows and
zero on replay. The latest view has **39 observed / 791 unobserved** keys,
one provisional direct candidate, 18 context, 15 not-direct and five uncertain.
An updated offline queue distinguishes one verified same-work relation to
reuse, five locally recorded abstracts to validate/read, five uncertainty
cases, 376 cached-metadata abstract tasks and 409 other metadata tasks.
The five abstracts were reconstructed and identity-checked from their retained
raw payloads in `l02-v2/remaining-held-abstracts-2026-10-06.json`.
A new ten-lookup OpenAlex plan had an offline preview of ten pending,
zero requests, SHA-256 `2709e7c4574cffb9442f358a5ae403fcf3983d71f187bffa4fed52fcfdf4bd2b`.
The operator authorized execution: all ten lookups returned HTTP 200, yielding
three identity-checked abstracts and seven `NO_ABSTRACT` records. All retained
payload hashes and reconstructed texts were checked offline; replay previews
zero pending. The new unlabeled packet is
`l02-v2/human-reference-packets/7fabec05109ec4c5971f5b3aa8f579b149a7697e87400777437c93bcb59964e9.json`.
A seven-case Crossref fallback was then authorized and completed. All seven
responses were HTTP 200 but lacked abstracts; retained payload hashes and
identity/status reconstruction agree with the recorded rows. Its preview now
shows zero pending. Queue snapshot
`audits/source-selection/queues/026753b6d8c1e9d425004e19cef9e84ef713aa69e7474b862ff771c6cd1a6267.json`
routes eleven candidates checked on both OpenAlex and Crossref to copy/text
inspection, with no repeat metadata lookup. Queue generation distinguishes missing abstracts and
failed lookups from never-looked-up candidates and preserves an available
abstract after a later lookup failure. No new scientific
claim, profile, admission or verdict was produced by this continuation.

After the Crossref fallback, the operator asked to continue every offline step.
Eight additional advisory abstract observations were recorded after checking
each abstract against its retained payload hash and metadata row. The three new
OpenAlex texts yield two contextual exclusions (conference-call tone with
annual crash-risk outcome; ESG abnormal returns limited to event day) and one
not-direct result (news-derived volatility and broad price-direction prediction,
without a firm-level text-sentiment return test). Five earlier cached abstracts
were also screened: two provisional direct candidates report weekly-news
prediction over one quarter, one contextual exclusion uses media sentiment as a
moderator of pollution-news exposure returns, one index-level aggregate-news
study is not firm-level evidence, and one remains uncertain because its “short”
and “long” horizons are unspecified. The two one-quarter candidates have
different DOI keys but near-identical titles/abstracts; they are not merged and
need a same-work/version check before independent-study counting. These eight
rows are `AI_PROVISIONAL`, use `codex-interactive` with unknown harness version,
and remain advisory. No model or network calls, identity rows, source admission,
profile or verdict were created.

The current v2 view is **47 observed / 783 unobserved** out of 830, with three
provisional direct-candidate keys (one held full-text candidate plus the two
possible versions), 21 context, six uncertain, zero admitted, and the cohort
open. The fresh offline queue is
`audits/source-selection/queues/5cd7c3f8aa0e98b8f369e80adfc490ad7bfd201dabdd64f273f35add84360d54.json`:
789 tasks, comprising six unresolved observations, one verified relation to
reuse, eleven keys without abstracts from both checked providers, 364 cached
metadata tasks and 407 metadata lookups. Next work is local validation of the
possible-version pair and inspection of cached legal-copy locations. Fetching
any new copy remains a separately authorized network campaign.

An offline audit of cached copy metadata for the eleven provider-exhausted keys
found 52 listed routes, but none uses a host in the frozen exact host selector.
Potential repository/author-copy leads include BBVA Research, University
College Dublin (`hdl.handle.net`), Leibniz University Hannover and Australian
National University (`hdl.handle.net`). These are metadata URLs only: no route
was checked, no robots request was made and no bytes were fetched. The private
content-addressed route audit is
`audits/source-selection/copy-locations/c5b013341fff344bdf04f2046dbc0ba7acede6e23249fe8c9133bff16d641ddc.json`.
The frozen `sources.yaml` population says additional university/author hosts
require a dated population decision and a new round. Do not request these copies
or count their papers in the current population unless the operator changes that
scope.

Offline identity comparison of the two one-quarter direct candidates supports a
`POSSIBLE_VERSION` relation: same authors, near-identical titles, and two exact
shared passages, with SSRN 2013 versus Financial Analysts Journal 2017 metadata.
Keep them as one possible study family; no identity-ledger row or evidence
transfer was made without a held copy. The corrected assessment is
`audits/source-selection/identity-audits/a12ac3e23b0f5cecbd9385732af940b576b1b28cd187940cbf2fe5bece357978.json`.
It supersedes an earlier private audit whose abstract-similarity calculation
used the raw OpenAlex inverted-index object; that earlier metric is invalid and
must not be used.

A draft population-change proposal lists four cached copy routes and the
questions that need an operator decision:
`audits/source-selection/population-proposals/8b94db833b958f4f21bdfe69f7aeed92624855fbe64f307f052d0440908dd2d5.json`.
It is not applied. The exact allowed hosts in `sources.yaml` are unchanged. The
next decision is whether to create a dated population version and new L02 round
for additional verified university/author repositories. A network request
approval alone does not change that selector; redirect destinations also need
their own host and robots checks.

2026-10-06 research portal proposal: the operator requested protocol-bound research flows,
per-stage drilldown, live events, human source/PDF intake, extractable results and model/key
administration. The design at
`docs/superpowers/specs/2026-10-06-research-portal-design.md` incorporates a GPT-6-astra
architecture review, including an intervention inbox, question-centric provenance, verified
access offers and scoped flow state. It is a proposal for Claude Code review, with no portal
implementation, source admission, network sweep or model run implied.

2026-10-05 D81 advisory continuation: `identity_relation_version 2` gives each
candidate/copy counterpart a separate chain while replaying the existing v1 REIT
copy row. `source_selection_import_version 2` accepts a new frozen AI file only
with explicit current assessment IDs; it preserves the later PDF-backed REIT
observation and refuses a stale map or conflicting REIT decision. Fixture tests
exercise two counterparts, legacy replay, replacement and idempotent rerun.
No replacement AI output has been provided or imported into L02, so its 21
screening and one identity rows are unchanged. The code still does not admit a
cohort or turn provisional AI judgments into a human reference.

2026-10-05 Claude Code adversarial review of D79 reported four reproduced risks:
packet text unbound to raw metadata, PDF text/campaign unbound, concurrent
duplicate appends, and append outside the frozen inventory. D80 repairs these
boundaries and adds regression tests. The existing L02 import plan still previews
zero new rows and its saved 21 screening plus one identity rows remain readable;
no ledger rewrite or new request was made. A new AI file with different content
still needs an explicit supersession plan; identity relationship counterparts
also need a future schema design before automatic relationship processing.

2026-10-05 offline L02 crosswalk: `tools/audit_l02_screening_crosswalk.py`
reproduces the frozen v1/v2 counts, disjoint keys and exact Claude quote checks.
The private readout is
`store/alembic-s4-lungo/audits/source-selection/l02-v2/offline-crosswalk-2026-10-05.md`.
The 34 prior agent assessments and 20 new Claude abstract assessments have zero
overlapping keys and cannot measure one another's accuracy. V2 narrows direct E1
to media/newswire sentiment. Held `ACA001` appears to satisfy that exposure; held
`ACA012` uses a RavenPack feed that also lists regulatory and other sources, so its
specific signal needs checking. Two v1 uncertain filing-tone works remain context
under v2 unless a separate media-news analysis is found. All 15 Claude EXCLUDE
reasons are compatible with their abstracts; Twitter-with-media-control, newspaper
non-event and title-only music chapter receive targeted follow-up. No selection,
admission, model or network ledger changed; this audit gives no error estimate.

2026-10-05 D79 source-selection bridge: the private v2 import plan is
`store/alembic-s4-lungo/audits/source-selection/l02-v2/source-selection-import-2026-10-05/plan.json`.
Its offline preview and apply command are in D79. The new advisory
`source_screening.jsonl` has 21 append-only rows for 20 keys (REIT full-text
context supersedes its abstract uncertainty); `source_identity.jsonl` has one
`POSSIBLE_VERSION` REIT title observation. The latest view has 15 provisional
not-direct, one provisional context, four provisional uncertain and zero direct
inclusions. All 830 inventory keys still require a controlled selection decision
before cohort admission; 810 have no observation in this new v2 ledger. The older
34 agent assessments remain in their separate v1 audit. Historical stage ledgers
are byte-identical, no network/model call was made, and rerunning apply adds zero.

2026-10-05 bounded L02 follow-up: Claude Code supplied a separate `AI_PROVISIONAL`
20-abstract screening (15 EXCLUDE, 5 UNCERTAIN, 0 INCLUDE), stored under
`store/alembic-s4-lungo/audits/source-selection/l02-v2/ai-screening-claude-2026-10-05/`.
The packet hash, unique keys and exact abstract quotes were checked locally; this is
not a human reference or a measured screening accuracy. An isolated legal-copy audit
of the five UNCERTAIN cases is under
`store/alembic-s4-lungo/audits/source-selection/l02-v2/uncertain-fulltext-2026-10-05/`.
Its first campaign recorded sandbox connection failures; the named host campaign
retrieved one REIT PDF, saw one stale publisher PDF URL return 404, and found no
eligible Unpaywall copy URL for three works (one green resolver-only SSRN record,
two closed IEEE records). The REIT PDF tests weekly sector indices, not firm-level
returns; it is contextual for direct L02, with a possible title/version variant
still to verify. Its exact passages and raw hash are in `readout.md`. No production
selection, acquisition, profile or verdict was changed. A private automation plan
for the Alembic strategies is at
`store/alembic-s4-lungo/audits/automation/claimstone-autonomy-plan-2026-10-05.md`.

2026-10-03 offline continuation: the current L02 search audit is
`store/alembic-s4-lungo/audits/research-search/858a8b141f29abfb4fe2af7da16ef8bee8a906f55bb101c81a9918d79794656d.json`.
All 57 planned queries completed, but all 19 OpenAlex and 19 Crossref queries reached
their cap of 25; all 19 arXiv exact-phrase queries returned zero. The round has 13
candidates and no citation-channel candidate, despite 1,060 recorded reference identities.
Literature recall remains unknown. Deeper search and citation screening need a separately
approved, bounded protocol; this audit made no request.

D77's frozen six-article Europe PMC pilot ran on the operator's authorization;
D78 records two HTTP 200 XML responses and four HTTP 500 responses. The isolated
outcomes are under `store/pmc-screen-time/audits/europe-pmc/jats-pilot-v1/`.
The offline `--rejudge` command in D78 rechecks the retained bytes. PMC004 has
45 references and six tables in JATS, matching stored HTML counts after
`jats_parser_version 2` fixes body-level bibliographies. PMC001's three graphic
tables keep it `JATS_UNSUPPORTED`; four XML endpoints remain unresolved after
HTTP 500. Both XML files declare their target PMCID. `gate_version 5` and descendant licence URL parsing are documented in
D78. The old Q04 profile and production stage ledgers remain untouched. An
additional network retry needs a separately frozen, bounded campaign; do not
infer missing OA XML from HTTP 500.

2026-10-03 identity update (D75): an offline, frozen-input relationship audit of L02's
830 candidate keys is at `store/alembic-s4-lungo/audits/source-selection/l02-v1/identity-audits/27306ee233f2112afcbcc4677cebdc76fc1b0c8b68994a444b8490997c0b2e09.json`.
It records the existing Balahur/Tavares DOI correction and the one acquired PDF still
indexed by the old key, plus 61 equal-title groups and one possible appendix relation
requiring inspection. No keys were merged, no ledger was rewritten and no request was made.
The 20-case human reference is still blank. Distinct-version/copy relationships remain
unresolved until authoritative evidence is checked; the audit is a queue, not a deduplicated
study count.

D76 continues that audit using held PDFs and cached metadata. The current snapshot is
`store/alembic-s4-lungo/audits/source-selection/l02-v1/identity-audits/4fa62215350e483f49b92c0664d5d95772c04c5f8bfc4ecaa349279ebcdbac53.json`.
It contains two verified mappings from title-based held-copy keys to the Federal Reserve
and NBER work DOI keys, plus two pending possible version/supplement links. The NBER PDF
and inventory disagree on publication year (2012/2013). Earlier content-addressed audits
are retained. No stage ledger, cohort or blinded human reference changed.

D69's 20-case Ollama Cloud pilot ran on the operator's host; D70 records 40 calls, three invalid
Kimi quotes and shared false inclusions. Its actual run cost at plan rates is USD 0.0875178;
the cumulative amount accounted under the existing USD 10 calibration ceiling is USD 0.83477096.
No production screening row was written and neither reader was adopted. The operator then fixed
L02's direct exposure scope to **media/newswire sentiment only**; 10-K/10-Q filing tone is context.
D71 records selection scope v2, a prepared seven-case development regression under
`store/alembic-s4-lungo/audits/source-selection/l02-v2/cloud-regression-v1/plan.json`, and a
ten-record abstract lookup plan under
`store/alembic-s4-lungo/audits/source-selection/l02-v1/abstract-batch-v1-plan.json`.
The operator ran both host commands. Ten OpenAlex lookups yielded four identity-checked
abstracts and six `NO_ABSTRACT` outcomes; all payloads are retained. A six-DOI Crossref fallback
is prepared at `store/alembic-s4-lungo/audits/source-selection/l02-v1/abstract-crossref-v1-plan.json`.
The seven-case regression stopped after two valid DeepSeek responses and one terminal
`SCHEMA_INVALID` response that omitted the two v2 quote fields. Its three original result rows
are retained, spending USD 0.0031386 more at plan rates (cumulative accounted USD 0.83790956).
D72 changes only experimental orchestration: rerunning the same plan now continues independent
cases and Kimi without repeating the malformed call. The other 786 records have not received
metadata lookups. The old 20 agent labels and new seven-case regression labels are development
references, not independently checked human truth.

D73 supersedes that stopped state. Crossref recovered two more abstracts: six of the first ten
now have identity-checked abstracts, four still have none. The v2 seven-case regression is
finished, but DeepSeek again falsely included a news-incidence/price-reaction study as textual
sentiment evidence; it supplied only three valid answers, Kimi four. Neither reader is adopted.
Cumulative accounted calibration spending is USD 0.87448991. Screening version 3 changes only
the experimental prompt's explicit field instructions and has not been run. A new twenty-key
metadata plan for independent human-reference material is at
`store/alembic-s4-lungo/audits/source-selection/l02-v2/heldout-metadata-v1-plan.json`.
Its offline preview has twenty pending and zero requests. After recorded lookups,
`tools/build_screening_reference_packet.py` can produce an unlabeled packet; a person must
assess it before any held-out model score or automatic screening claim.

2026-09-30 metadata update: the operator completed all twenty OpenAlex lookups. Thirteen
identity-checked abstracts are available; seven have `NO_ABSTRACT`. The unlabeled packet is
`store/alembic-s4-lungo/audits/source-selection/l02-v2/human-reference-packets/27b2bcb7172a3cc03621cb3fa040f0d9a0ca77c03993c0766b79b2c2cdf12035.json`.
The seven-DOI Crossref fallback plan is
`store/alembic-s4-lungo/audits/source-selection/l02-v2/heldout-crossref-v1-plan.json`;
the operator executed all seven recorded requests, and all returned identity-checked abstracts.
The rebuilt twenty-abstract packet is
`store/alembic-s4-lungo/audits/source-selection/l02-v2/human-reference-packets/b991c6a06218e1778ab93e8550c3e2ee095ac3f7933a2dc55b85fe8182517904.json`;
the same basename with `.md` is a readable, unlabeled review sheet. The earlier thirteen-abstract
packet remains preserved. Obtain independent human decisions before scoring a model. See D74.


Latest supervised screening continuation (2026-09-29): all thirteen previously pending admitted
candidates now have assessments. Eleven are excluded from direct question reading by exposure,
horizon or methodological role; two held filing-tone studies remain uncertain, including a null
twelve-month prediction test and a monthly sentiment specification alongside document similarity.
The private selection now has 34 assessed, 2 included, 30 excluded, 798 pending (796 unassessed
metadata records plus 2 uncertain). Snapshot `results/9bcd0cfbf9efe409f75e2040a26528874b626627174d615ad05e04fcb88236e7.json`
under the selection directory supersedes the live counts below; previous snapshots remain intact.
An offline metadata queue retains all 796 unassessed records. Cached payloads contain metadata for
387 of them but no abstracts; titles only order the work, not decide eligibility. Resolve study/
version/supplement relationships and fetch missing authoritative metadata in bounded recorded steps.
The public scheduler backlog now records these quality checks, null-result protection, actual
forecast horizons and parser coverage/author-field checks. No production ledger, model assignment,
registry, floor or scientific instrument changed; no new model call or PDF acquisition was made.


D68 adds `tools/audit_source_selection.py` and the preparatory audit contract. It validates
manual assessment structure, declared eligibility dimensions, frozen inventory/inputs,
provenance and explicit identity corrections. Missing/uncertain/unverified cases stay pending;
acquisition/recall/precision remain null. The tool is not a classifier, cannot certify scientific
screening accuracy and writes no production ledger or revised floor. All 19 instruments remain
unchanged. The old round remains below floor.

The operator authorizes proceeding with question-specific screening. The private dated protocol
is `store/alembic-s4-lungo/audits/source-selection/l02-v1/plan.json`, proposed scope
`s4-l02-screened-2026-09-29-v1`. It includes the 809 distinct dedicated-wave metadata identities
plus held candidates (830 distinct keys in the union); it does not silently erase DOI-redirector
exclusions. Eleven initial assessments include two direct-question sources and exclude six
methodological context sources plus the three inspected new PDFs. Context is not deleted.
Publisher title/DOI/abstract checks subsequently exclude all ten blocked AEA works by topic,
not download outcome. Their pages advertise complimentary PDFs; the recorded 403s do not
establish paid-only access. The latest selection is 21 assessed: two included, nineteen excluded.
The other 809 identities remain pending; this is an open selection, not a new closed corpus or
an 80% success. The identity correction explicitly identifies the actual downloaded work as
arXiv:1309.6202 / DOI 10.48550/arxiv.1309.6202 in the audit. The conflicting original key and all
original production bytes remain intact. This is bibliographic correction, not adjudication.

Reproduce the current selection with `.venv/bin/python tools/audit_source_selection.py --plan
store/alembic-s4-lungo/audits/source-selection/l02-v1/plan.json --write`. Its first snapshot is
`results/262f989f079d9956b1e0671dd3585355610ec6410b3da810b9dccd378d4d5066.json` under that directory.
The subsequent publisher-abstract snapshot is
`results/5386ec3997a36035985f9d1e4c3aff03bbc716ecacf2d1f7e5fd18afc68c108e.json`.
`STATUS.md` retains the ten publisher links and scope summaries alongside the correction.
Next inspect pending titles/abstracts and legal-copy eligibility, preserving ambiguous cases;
measure a frozen screening reference before automated classification. The scientific registry,
floor, old population and production model choices remain unchanged; no model credit is spent.

2026-09-29 source inspection supersedes D67's pending acquisition command: the operator
attempts all thirteen dedicated-wave candidates and normalizes the three obtained PDFs.
The update is 3/13 confirmed (WP 3/3, ACA 0/10); cumulative 22/34, ACA 2/12, MET 6/6,
WP 14/16. Both scopes remain INSUFFICIENT_ACQUISITION. Five publisher redirects return
403 and five stop on the actual destination host's failure budget. The recorded
PAYWALL_403 label does not independently establish a paywall. Active chunks are now 606.

Inspection finds an upstream identity conflict: the stored OpenAlex response attaches DOI
10.4230/OASIcs.SLATE.2021.17 to the title/arXiv copy of Balahur et al.'s different work.
The authoritative DOI publisher identifies Tavares et al.'s Portuguese economic-news paper;
that paper cites the Balahur work. The raw response is retained under requests/raw/
4bfa0d628a52a39a449575d103508d526eb21f85cc46504342f95bb41d56b19a.bin.
Do not use the mismatched identity for paid processing, silently repair its key, or count
readable-document confirmation as identity verification. An append-only identity resolution
contract and explicit correction remain pending; no production ledger was changed here.

The BERT paper's seventeen active chunks concern Weibo exposure and trading-day predictions;
annual testing periods do not establish weeks/months predictive horizons. The LLM data-supply
paper is outside L02; the Balahur full text supplies classification context rather than L02
return evidence. Ten blocked candidates have title-level flags, not completed full-text
relevance screening. Preserve the original denominator; do not discard them to pass admission.
The private inspection packet is audits/research-search/screening/
42d01ec91a0e11d981ce136e5a2b61b8f97353aef20313d89b168e46c39697b7.md (with companion JSON).
It retains exact local passages and frozen ledger hashes; model spending remains unchanged.

The operator requests recording all workflow automation needs while manual calibration
continues. [SCHEDULER_BACKLOG.md](SCHEDULER_BACKLOG.md) records the requirements and acceptance
criteria, including identity conflicts, project-specific screening, legal copy recovery,
persistent redirect-host budgets, offline preview, resume, spending, and incremental evidence
updates. It is a backlog, not an implemented orchestrator. Next resolve identity and prepare a
dated screening/search protocol; downloading unrelated papers solely to raise the floor is
not the next scientific step. Configuration validation and all 19 instrument checks pass;
the baseline suite has 1,063 passing, seven skipped and four socket-denied dashboard setup
errors in this sandbox. No engine or instrument change is made in this inspection.

D67 supersedes D66's stopped-query state: the authenticated host resume completes all 17 missing
queries. The dedicated wave is now 57/57 completed, with 38 capped queries and thirteen admitted
candidates (ten ACA, three WP), eleven added by resume. Current cumulative acquisition is 19/34,
ACA 2/12 and WP 11/16; both classes are below floor. The old round's eight discovery failures are
still separate unresolved work. No new source was acquired or read, and no model credit was spent.
The corrected acquisition preview uses execution's shared eligibility/retry filters and shows only
the thirteen requested candidates, instead of all 34. Next host command: `./claimstone.sh acquire
projects/alembic-s4-lungo --round s4-l02-search-2026-09-29-v1 --no-apis --limit 13
--campaign l02-first-acquisition-2026-09-29`, then normalize and report both update/cumulative scope.
Check copy identity, publication version and full-text relevance before model calls. Manual
calibration/debug remains the operator's chosen mode; building an orchestrator is deferred.

D66 supersedes the NOT_RUN baseline below: the host completes 40/57 queries with 17 OpenAlex
failures and 21 queries reaching their result cap. Of 525 observations, 523 are excluded by the
declared metadata population; 437 of 460 distinct excluded identities have doi.org URLs. Five
normalized-title matches concern three existing manifest sources on allowed copy hosts, so metadata
URL representation is a measured limitation of coverage. The two admitted titles are not directly
L02 evidence on title inspection. Neither low admission nor arXiv's 19 empty exact-phrase queries
establishes saturation. The cumulative rate is 19/23, but ACA 2/4 is below its class floor; admission
is INSUFFICIENT_ACQUISITION. Keep the two candidates and the denominator; do not whitelist doi.org
or change the population silently. Exclusion audit is under `audits/research-search/exclusions/`.

Optional OPENALEX_API_KEY support is implemented as an HTTPS-origin-scoped bearer header
(`fetch_version 3`) and passed through compose. The operator is obtaining the key; put it in .env,
not conversation or request URLs. `tools/resume_research_search.py --plan <D65-plan> --limit 17`
previews exactly 17 pending queries. Adding --execute resumes them from .env on the host, skips
all successful queries and stops on the first failure. A key does not guarantee quota availability.
Deepening capped queries, inspecting excluded-copy identities and screening bibliographies remain
pending after that recovery; there is no completed scientific profile or new model spending.

2026-09-29: the operator requests a complete L02 investigation after the partial D64 dossier.
D65 freezes a first dedicated keyword wave: T01/T08/T10/T12, 57 API/query combinations,
25 results each, under unchanged source population and question registry. The private plan is
`store/alembic-s4-lungo/audits/real-use/l02-full-search-v1-plan.json`. No query in this new wave
has run. `tools/audit_research_search.py --plan <path> --write` records the offline baseline;
`--previous <audit>` compares later cumulative inventories. Full-text acquisition is 19/21,
not 90% literature recall. Current effect completion is 18/549 readings, leaving 531 unanswered;
17 L02 annotations have production reviews (six SUPPORTED, eleven OVERSTATED), without certifying
their semantics. All 896 bibliography identities still need a focused, recorded relevance screen.

The next host command is `./claimstone.sh discover projects/alembic-s4-lungo --channel keyword
--topics T01,T08,T10,T12 --per-query 25 --round s4-l02-search-2026-09-29-v1`. This session cannot
open network sockets. After its outputs, inspect capped/failed queries and excluded observations,
screen references including singly cited works, and prepare bounded acquisition and complete
reading/review. No paid corpus plan is executed or production reviewer promoted. The earlier USD 10
authorization was for calibration; account USD 0.74725316 remains unchanged. Obtain a concrete
corpus-reading budget once the queue is known. Do not describe this preparation as a completed round.

D54 implements optional metadata populations and verified local cache reuse. The operator's host
then confirmed all 19 seed sources. Discovery adds two candidates: 19/21 confirmed (0.9048), with
549 current chunks. The latest 30 queries have eight failures, all OpenAlex (five RATE_LIMITED_429
and three DOMAIN_BUDGET_EXHAUSTED). Admission clears the floor but remains provisional, with
awaiting_discovery and awaiting_acquire. No scientific result follows from that coverage alone.

D55 records the operator's separate USD 10 cumulative calibration authorization. D56 records its
completed host run: all 40 whole-document readings valid, one JSON failure recovered by the alternate
extractor; 80 annotations accepted, 13 rejected; all 80 independently reviewed (26 SUPPORTED,
53 OVERSTATED, one NOT_APPLICABLE). USD 0.11250092 is priced at the plan rates, plus USD 0.339
reserved for the original unknown-cost DNS attempt: USD 0.45150092 cumulative accounting, not a bill.

Interactive inspection finds extraction applicability/entity errors and reviewer context/stance
errors, including errors among SUPPORTED annotations. The 53/80 label ratio is not extractor
precision, nor are 26 SUPPORTED annotations 26 independently confirmed findings. The private
reading packet retains all 80 original annotations/reasons, their current contexts and diagnostic
notes. Those notes are consultative and change no review ledger. The next calibration must test
question applicability, whole-passage context and stance explicitly before scaling reading or
changing the production prompts/task version. No corpus profile or signed verdict is produced.

D57 prepares that comparison after the operator says to proceed: 12 provisional development
reference cases (four positive controls), the same 40 original extraction passages, and independent
review of all new accepted annotations. The hash-frozen plan is `audits/prompt-comparison/v2-plan.json`
under the original research store. `tools/run_prompt_comparison.py --plan <path>` previews offline;
adding `--execute` resumes the isolated experiment under `store/prompt-comparisons/s4-v2/`.
No production prompt or review ledger changes. This reference was selected after inspecting errors
and cannot estimate held-out accuracy or justify automatic adoption.

The first experimental diagnostic call fails DNS resolution here, leaving all 12 diagnostics
unanswered and no new extraction. Its USD 0.131672 reservation makes cumulative original-budget
accounting USD 0.58317292 (priced USD 0.11250092 plus unknown-cost reserves USD 0.470672), not a
provider invoice. The experimental audit confirms production hashes and all original bytes are
unchanged. Resume the same plan on the operator's host; do not open another budget or scale yet.

D58 supersedes that stopped execution: the host completes all 12 diagnostics and 40 experimental
readings (one schema failure recovered). Harvest returns 41 accepted annotations and 15 rejections;
all 41 annotations are reviewed (10 SUPPORTED, 28 OVERSTATED, three NOT_APPLICABLE). Diagnostic
agreement moves from 4/12 to 6/12, with positive controls unchanged at 3/4. The post-selected
development reference is not general accuracy. Cumulative accounting is now USD 0.67249986:
USD 0.20182786 priced and USD 0.470672 reserved for unknown-cost attempts. Original bytes and
production hashes remain unchanged; no production prompt is adopted.

Interactive inspection retains all new annotations, reviews and full contexts in the experimental
`audits/assessment/738196ddef1f916f4e0d86710bc0b13a50d1c9d786284882a4b7130022217d06.json`
packet, with a companion Markdown assessment. There are residual applicability errors among
SUPPORTED and rejection reasons that invent conditions or ignore explicit context. The annotation
count dropping from 80 to 41 cannot establish improvement. Next isolate reviewer checks on fixed
annotations, separating applicability, fidelity and stance with positive controls, rather than
paying for another extraction or scaling the corpus. This is consultative assessment, not adjudication.

D59 prepares that next reviewer-only experiment after explicit operator authorization. The new
local plan is `audits/review-diagnostics/v3-plan.json` under the research store, SHA256
`f2427606709d94e35c59487ae7be17921be690c1bca40ccdf07eb35c1e93f08c`.
`tools/run_review_diagnostics.py --plan <path>` previews offline; adding `--execute` runs or resumes
18 fixed-annotation tasks in `store/prompt-comparisons/s4-v3/`. Seven are positive controls; the
provisional reference scores 18 applicability, 16 fidelity and eight direction checks. The schema
keeps the three checks and reasons separate. Diagnostics never enter production reviews or profiles.
No new extraction or model call has run yet; prior cumulative accounting remains USD 0.67249986.
Earlier DNS failures establish that host execution is needed here; no redundant charged/reserved
attempt is made. Both previous scientific stores and accounting histories are frozen before contact.

D60 supersedes that preview state: the first host response is SCHEMA_INVALID (array instead of
the declared object). It is retained with its USD 0.00156 priced attempt; all 18 cases remain
unanswered. The repaired local plan is `audits/review-diagnostics/v3-format-v2-plan.json`, SHA256
`608078075a69bd53215e8099fab97887b85e0e1a9ab8a09db37ee2ed749582e8`.
Run that plan with the same driver and `--execute` from the host. It names the exact JSON shape
in the prompt, retains the original schema and 18 cases, and creates fresh prompt identities in
`v3-three-axis-explicit-format-v2`. The original plan remains readable and invalid responses remain
invalid. The failed diagnostic queue is frozen and included in cumulative USD 0.67405986 accounting,
within the same original USD 10. The repaired preview makes no paid call here; scientific calibration
remains unmeasured. Previous stores remain unchanged.

D61 supersedes that stopped state: the host completes all 18 repaired diagnostic responses.
Summary-label agreement is 10/18 versus 6/18 previously; positive controls 6/7 versus 3/7;
challenge cases 4/11 versus 3/11. The original 12-case subset remains 6/12. Axis agreements are
applicability 12/18, fidelity 15/16 and direction 6/8, all against a post-selected provisional
reference. Two formerly caught errors now pass: an entity substitution across examples and a
wrong CONTRADICTS stance on pre-earnings returns. These block adopting the diagnostic task as
production review. Correct labels can also have invalid reasons, including confusing Week 0
news formation with the return horizon. No production task, review, profile or verdict changes.

The completed audit is experimental `audits/diagnostics/7bb7651a5ba5c0c26e7870c428b98e1b7cf3c33f1f3be66082ccc344c371404d.json`.
The consultative reading packet and Markdown assessment are experimental
`audits/assessment/bf11958c256856abf09b7789692843db1699eda1d69478c95934ceb937c7dadc.json`.
Cumulative original-budget accounting is USD 0.69726086 (priced USD 0.22658886 plus reserves
USD 0.470672), not a bill. Next compare another eligible independent reviewer on the unchanged
cases before another prompt expansion, then test unseen cases before adoption. This next paid
comparison is prepared by D62 below; the assessment itself pays nothing.

D62 prepares the authorized independent-reader comparison with `kimi-k2.6` (Moonshot), requested
thinking off, through the existing Ollama Cloud harness. Its local plan is
`audits/review-diagnostics/v4-kimi-k2.6-plan.json` under the research store, SHA256
`f177faa1cd4b0b95a7c12e1da84b023b3a8a6e552cce5154386ab6d68b05e690`.
Run `tools/compare_reviewers.py --plan <path> --execute` from the operator's host. All 18 requests
are byte-identical to the repaired Mistral diagnostic queue (including the 1,200-token cap), with
separate results in `store/prompt-comparisons/s4-v4/`. Earlier stores and diagnostic responses are
frozen; every paid and unknown-cost attempt remains in the original USD 10 accounting. Preview
confirms USD 0.69726086 already accounted, with USD 4.5690624 conservatively reserved for the 18
first attempts if every response reports no usage. This is an upper reservation, not expected billing.
No Kimi call has been made here because the earlier DNS failures require host execution. Model access,
requested thinking mode support, latency, valid format and scientific reasoning remain unmeasured.
Inspect the entity/certainty and pre-earnings-direction regressions alongside all seven positive
controls before interpreting aggregate agreement. The reference is still post-selected, not held out.

D63 supersedes that preview: the host completes all 18 Kimi responses. Reference-label agreement
improves from Mistral's 10/18 to 14/18, positive controls from 6/7 to 7/7 and challenge cases from
4/11 to 7/11. The original twelve-case subset improves from 6/12 to 8/12. Both critical regressions
are withheld: the entity/certainty defect is correctly UNFAITHFUL but summarized NOT_APPLICABLE
rather than the reference OVERSTATED; the pre-earnings CONTRADICTS stance is correctly INCOHERENT.
The reference is unchanged. Scored applicability, fidelity and direction agreement is 14/18, 16/16
and 8/8, respectively. The unscored causal-design direction still has an incorrect reason, so those
axis totals must not be read as general correctness.

Three false acceptances remain: a regression specification treated as a predictive result, a paper's
organization treated as an earnings-concentration finding, and model knowledge contamination treated
as causal identification. Prefer Kimi as candidate for a frozen-task validation on additional cases
not used to tune the prompt, with a reference fixed before model answers and inspection of reasons.
Neither the experimental task nor Kimi is adopted into production by this assessment; no corpus
reading, profile, review ledger or signed verdict changes, and no new paid experiment is launched.

The completed experimental audit is
`audits/reviewer-comparison/99cbaea6c79586ac52022b6770b07794be6e0c25ed8a5361213a457502af5d29.json`.
The packet with all eighteen annotations, contexts, both readers' replies and assessment notes is
experimental `audits/assessment/6bc7b50add6ad22d41bc115b40666bcc8b5e7c137186f4d07b9e80a25eaf791d.json`,
with a companion Markdown assessment. Kimi's attempts cost USD 0.04999230 at plan rates. Cumulative
original-budget accounting is USD 0.74725316 (USD 0.27658116 priced plus USD 0.470672 reserved),
leaving USD 9.25274684 of the original USD 10 authorization; this is accounting, not billing.

During this assessment, new `round_state.py`, `dashboard.py` and their tests appear in the workspace.
The full suite now has two failing round-state assertions (empty discovery detail and adjudication
staleness) and four dashboard setup errors because this sandbox refuses socket creation. The 1,026-test
suite excluding those two new test modules still passes with seven skips; validation of all six
projects and all 19 instrument versions passes. This assessment does not modify the concurrent
dashboard implementation or claim that the expanded full suite is green.

D64 starts the operator's authorized first supervised use on L02 using local passages only. The
private plan is `audits/real-use/l02-pilot-v1-plan.json` under the research store. Rebuild with
`tools/build_consultative_dossier.py --plan <path> --write`: the consultative dossier is
`audits/consultative/d49f030305af7fe665dd4074fb1701995f3333d67a507ddbee0e9a30614a9aad.md`, with
companion JSON. Nine exact passages from seven current chunks in three working papers pass gate v4.
This is a selected partial reading, not full source/corpus coverage or a new scientific profile.
Interactive curation is recorded honestly; no model call, acquisition or production ledger write occurs.

The useful distinction is between text-sentiment return predictability, persistence of future news
sentiment and price-reaction-based drift. One paper reports up-to-13-week predictability and different
positive/negative durations; another reports a next-month risk-adjusted association, while its multi-year
finding concerns future sentiment. The third forms weekly price-reaction portfolios, expressing daily
returns in monthly units, and separately studies longer event-time drift. Neither monthly display
units nor price-based drift alone answer the text-sentiment question. Costs, current-market transfer,
incremental prediction and causal identification remain separate questions. The pilot supplies a
concrete reading product and material for subsequent calibration; these inspected passages cannot
be relabelled as unseen validation. Cumulative budget accounting remains USD 0.74725316.

The local plan is `audits/s4-calibration-plan-v1.json` under the research store; its completed audit
is `audits/calibration/0728ab8092059597ec491affc7af93c1e9b8341750fd148dfb32bb2ff1e6c574.json`.
The driver previews without writes, retains partial successes and shares one budget across readers.
The input/hash-frozen reuse plan and transfer audit remain under `audits/research-preparation/`.
The original cache and all original target bytes are preserved. Full-corpus readings still unanswered:
effect 531, method 527, heterogeneity 549, premise 549; none is silently covered by the calibration.

One round has run all six stages: `pmc-screen-time`, 37 of 40 confirmed against a floor of 0.80,
1,721 accepted annotations and 271 current rejections, **0 verdicts**. There are eight historical
profiles and eight newly built v5 profiles. **Q04 is formally complete and awaiting human reading;
the other seven remain provisional.** Its current hash is
`9340389c9aac29b77e901c20e27434d211fe9e7825a68d99995d8c6fa5b20fdd`.

D49 applied the offline replay while preserving original bytes. D51/D52 subsequently harvest 53 new
PMC annotations and 12 new rejections from model responses. Repeat extraction harvest appends zero
of either; repeat review harvest reports zero reviewed and 42 already held. These are annotations,
not independent studies. All current scoped annotations satisfy gate v4; harvest/regate backlog is zero.
The historical narrow-task reviews remain in the append-only ledgers; 42 Q04 annotations now also
have usable complete-annotation v2 reviews. No historical profile hash is relabelled or signed.

PMC has 24 unanswered readings: effect 0, heterogeneity 4, method 15, premise 5. The measured
remaining full-review workload is 1,679 unique calls, all outside Q04. The completed effect readings
cover all 734 active chunks. Q04 has 42 current annotations, all independently reviewed by
`ollama-cloud/mistral-large-3:675b`: 4 SUPPORTED, 31 OVERSTATED and 7 NOT_APPLICABLE. SUPPORTED
is the single-annotation review label, not a verdict on the question. The profile retains four results
from four of 37 examined sources, with sample linkage unestablished.

The operator delegated the bounded Q04 run. Seven primary extraction answers and three targeted
`gemma4:31b` answers complete its ten missing readings; original invalid responses remain invalid.
Mistral differs from both extractors. No publisher, parser, registry, floor or population was changed.
The USD 1 plan records USD 0.0556299 at conservative rates, plus USD 0.339 reserved for the old
unknown-cost DNS failure: USD 0.3946299 accounted. This is not a provider invoice. Agent inspection
matches the saved audit/profile hash; no additional model call or profile rebuild was made by the agent.

The human-reading packet is local and gitignored:
`store/pmc-screen-time/audits/reading/6b11da9f50a22c8fbeb4a1cd3b43a132c7034f88e0c75ca9e19a60647781254e.md`.
It flags the relevance/stance of each of the four retained results, especially PMC009's GRADE rating
labelled CONTRADICTS without testing preregistration or correction for multiple comparisons. These
are inspection notes, not new ledger decisions or a scientific verdict. Throughput and valid-output
rate are measured; scientific agreement with an independent v2 reference is not established.

Read the live profile without requests:

```bash
.venv/bin/claimstone verdicts projects/pmc-screen-time --question Q04
```

The completed host audit is
`store/pmc-screen-time/audits/question-round/1943dcbe8082fa76370d8b9fd0b013a55c59e74c04a6a2e24b3b9afa19442e4b.json`.
See D52 and [the completed round report](replays/2026-09-28-q04-ready.md). The cumulative local v2
plan is retained for audit/resume; it is not an instruction to start the other seven questions.

Alembic's curated manifest still has 28 unanswered readings and 6,183 prospective review calls covering
6,188 annotations. It is 14/25 confirmed (0.56), below its floor. Its 27 missing raw responses remain
unresolved; the whole-store count must not replace the selected population.

The earlier queue measurement was offline and used only temporary copies. See
[the production replay report](replays/2026-09-28-production-replay.md) and local content-addressed
audits under `store/<project>/audits/offline-replay/`.

Two other instances exist and both stand below their floor and produce nothing: `alembic-s4` at 0.56 with a
measured ceiling of 0.72, and `pilot-screen-time` at 0.45. That is the correct behaviour, not a backlog.

## Running, or left running

- **GROBID** is up (`docker compose up -d grobid`), healthy, ~3.6 GB. Only `normalize` needs it. Stop it
  with `docker compose down` when idle; it is `restart: unless-stopped`, so it will come back on reboot.
- **Nothing else is in flight.** Drained means no routine retry is pending, not that every reading
  succeeded. The bounded Q04 driver now has no eligible extraction/review work remaining.
  A batch is resumable by `call_id`; answered calls are skipped, while transient failures may retry.

## The decisions to read first

`DESIGN_DECISIONS.md` is 2,000 lines. For what happens next, these are the ones that bind:

| | why it binds |
|---|---|
| **D36** | the per-class floor exists and `alembic-s4` deliberately does not use it, because fitting a bar to a rate already seen is what the invariant prevents. Its closing clause was **corrected** on 2026-09-27: it claimed `sources.yaml` pre-authorised declaring `IND` a pointer, and it does not. |
| **D38** | a reviewer table that was **retracted the same day**. Its numbers measure the tool's filter, not the readers. The consequence matters: hosted reviewers are **unmeasured**, not bad. |
| **D39** | 0.64 on literature that declares itself free, and why the gap does not close by retrying. This is the only evidence a floor revision could rest on. |
| **D40 + D44** | a second reader marks 23 of 41 and 36 of 42 gate-passed claims `NOT_APPLICABLE`. Over-attachment is the dominant cost of the current call shape, and it is not a property of one question kind. |
| **D41** | why the closed round is legitimate: the selector is deposits, not outcomes, and it excludes 159 of 199 candidates. |
| **D49** | production replay completed, with preserved bytes; actual scoped remaining readings and full-review workload. |
| **D50** | delegated Q04 readers, bounded continuation and the first recorded DNS failure; no reading or review was completed. |
| **D51** | five host readings harvested, strict prose rejection, targeted alternate extractor and shared budget. |
| **D52** | Q04 formally complete; four retained results need human relevance/stance assessment before adjudication. |
| **D48** | all review repairs; full-result reviews are a new task, legacy revisions are retained but cannot certify it. |
| **D47** | authoritative replay and immutable reader annotations; measured across all stored batches without changing real ledgers. |
| **D46** | whole numeric tokens, revision-aware gate outcomes and `awaiting_regate`; measurements used temporary ledgers. |
| **D45** | completeness, scope and live signature validation; corrects D44’s claim that Q04 was ready to sign. |
| **D43** | the notation vocabulary was domain knowledge in the engine and a corpus in another field proved it. The `extraction` config section that fixes it had never been loaded at all. |

## What is a person's decision and not an engine's

**The adjudication.** Q04 is now formally complete under profile v5, with the current hash above;
the historical D44 hash is not signable. A person must read the four retained annotations and their
passages, assess their relevance to both preregistration and multiple-comparison correction, and
state the PMC-deposit scope and coverage in the rationale. D52's reading packet identifies specific
stance/attribution ambiguities. An agent does not choose or sign the verdict, and no verdict exists.

**Whether the floor moves.** D39 is the first evidence that 0.80 may be unreachable for openly-obtainable
literature by legal routes. That is a real basis for a dated, versioned, motivated revision — and it is the
operator's call. An agent proposing it must cite the measurement and must not fold it into other work.

**Whether to spend on independent full-result review.** D48 changes the task: the historical estimate
of about 1,100 calls covered only the remaining seven questions. Now all eligible annotations, including
Q04, need a v2 review. D49 measures 1,668 PMC calls, including 42 for Q04, before any new extraction
results. Q04 is completed in D52. The remaining queue is 1,679 calls and extending paid review to
the other questions remains the operator's decision, based on the current measured queue.

## Open problems, with what is known about each

**The reviewer does not scale, measured twice.** `claude-opus-5` discriminates — its verdicts on 83 real
claims are checkable and correct on inspection — but it runs on an interactive subscription plan and
`claude-cli` returned `BACKEND_ERROR: exit 1` on 8 of 43 H15 calls and **36 of 42** Q04 calls before the
limit reset. CLAUDE.md's standing constraint ("interactive subscription plans are not batch
infrastructure") is therefore measured, not precautionary. The calls retry cleanly afterwards.

*The hosted reviewer measurement*: D52 records 42/42 valid full-v2 Mistral responses on Q04.
The four retained cases carry relevance/stance flags for human reading. This measures valid output
and execution, not scientific accuracy. Agreement with `claude-opus-5` over the original 83 reviews
would require using the same old task; it cannot certify metadata those reviews never saw. Full-v2
agreement requires a new independent reading or human reference. Inter-rater agreement is not ground
truth, and no such full-v2 comparison has yet been measured. `SameReader` still forbids the extractor
from reviewing its own annotations.

**Europe PMC is the highest-value acquisition improvement left, and was deliberately not done.** Its REST
API serves full-text JATS XML by design and would plausibly beat the 0.93 the HTML route reaches. It was
skipped because `normalize` handles GROBID's TEI and not JATS, so adding it is a new parser path and a chain
of new assumptions — which was the wrong thing to start while closing a round. It is the right thing to
start next.

D53 implements the local JATS parser and stage-3 routing, with 22 synthetic correctness cases.
It preserves table geometry, notes and explicit references and records `jats_parser_version 1`.
Unsupported tables leave sources awaiting. Existing production ledgers and Q04's hash are unchanged.
The acquisition gate and Europe PMC resolver route are still pending, followed by an explicitly
approved bounded pilot: no acquisition gain or real-article parser accuracy has yet been measured.
See [the implemented boundary](superpowers/specs/2026-09-28-jats-normalize-design.md).

**Over-attachment in stage 4.** Every chunk is asked about every question of its kind and the model answers
rather than declining. 23 of 41 and 36 of 42 claims do not speak to the question they cite. Nothing
mechanical can catch it — the gate's `WRONG_KIND` check passed all of them correctly — so the fix is the
prompt or the unit shape, and it should be measured against the 83 reviewed claims that now exist as a
reference.

**The 586 rows that explain the largest rejection class.** In 586 of 593 `NUMBER_NOT_IN_QUOTE` cases the
asserted figure *is* in the chunk and not in the quoted span: the model quotes one sentence and cites a
figure from the table two lines below. It is a property of the call shape, and it is why the gate's standard
and the reviewer's must differ (D38).

## A discipline this session had to adopt, from four failures

Four times in one day a fix's effect was predicted from counting a signature in a small sample, and four
times the prediction was far too high — 45 predicted and 1 delivered, 166 and 18, 6 and 1, and one
hypothesis falsified outright. **Quote what `regate` or a re-harvest returns, never what a sample suggests.**
The rule is recorded in D37 and D39 and it applies to any figure an agent puts in front of the operator.

The related failure, three times: a test that greps source text matches the comments *explaining* the thing
it forbids. Walk the AST, or strip comment lines first.
