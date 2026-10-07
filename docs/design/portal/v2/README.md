# Claimstone portal — redesign v2.1: the guided journey, completed

**Status:** proposed revision of the approved v2 direction. It is a design, not an implementation.
**Date:** 2026-10-06.
**Input:** [`../review-v2-e-brief-designer.md`](../review-v2-e-brief-designer.md) (findings R1–R7, S1–S4, P1–P3,
§6 and the §7 scenarios). Every change below names the finding it answers and the operator problem it solves.
**Previous version:** `v2.0/` keeps the seven v2 boards and their README unchanged, for comparison.

**Reference boards:** the `.html` files in this folder, plus `canvas.json` (board order, positions and the
annotation shown under each board; it names the canvas files `X.dc.html`, saved here as `X.html`). They are design-canvas sources: inline styles plus a small runtime
(`support.js`, `<x-dc>`) that is not in this repository, and Google Fonts links. Read them as markup for layout,
copy and visual tokens. They are **not** routes or deployable assets: during implementation the links become
app routes and the fonts are bundled (§6 of the review). All values are illustrative; quoted passages are
placeholders; `[operator name]`, `[vendor]`, `[price]` and `[backend / model]` are placeholders on purpose.

## 1. What did not change

The promise and the rules of v2 stand: the user describes a topic, structures questions and presses
**Start**; Claimstone drives the project and stops only where a person is needed; every human decision is
taken in the web interface; only a person signs, with no verdict preselected or suggested; five verdicts
that never collapse; no floor, no verdicts, and no override; the protocol is frozen and versioned; unknown is
"—", never 0; counts are labelled as counts; HTTP 403 means "access refused"; nothing runs or spends without
consent; meaning is decided on the server. Visual system and navigation are unchanged except for §3 below.

## 2. The boards

Numbers follow the canvas (page "v2.1 — revised"). "New" boards did not exist in v2.0.

| # | file | board | status | answers |
|---|---|---|---|---|
| 1 | `V2Today.html` | Today — since your last visit | new | S4 |
| 2 | `V2Projects.html` | Projects — search, not a menu | revised | R5, §6 |
| 3 | `V2NewProject.html` | New project, steps 1–2: topic and questions | revised | R3, R1, R4 |
| 4 | `V2NewStart.html` | New project, steps 3–4: scope, rigour, plan, start | new | R1, R4, S3 |
| 5 | `V2Journey.html` | Project — the guided journey | revised | R1, R4, R5, R6, S1, P1, P3 |
| 6 | `V2Activity.html` | Project — activity history | new | S4 |
| 7 | `V2Decisions.html` | Decisions — act in place | revised | S2, S3, P2 |
| 8 | `V2AddMaterial.html` | Add material | new | P1 |
| 9 | `V2Desk.html` | Reading desk — Q04 | revised | R2, R7 |
| 10 | `V2DeskZero.html` | Reading desk — zero usable results; profile changed | new | R7, §7 |
| 11 | `Flow.html` | Evidence path — copies, then evidence | revised | §6 |
| 12 | `Lineage.html` | Claim provenance | revised | §6, R2 |
| 13 | `V2Export.html` | Export | new | P3 |
| 14 | `V2Admin.html` | Administration | new | P3 |
| 15 | `V2States.html` | States and scenarios | new | §6, §7 |

## 3. Changes, and the problem each one solves

### First: the existing story (R1–R7)

| finding | problem for the operator | change | boards |
|---|---|---|---|
| **R1** acquisition is not reading | "37 of 40 read" claimed reading that had not happened; the floor was described as a reading threshold | Step 3 says **"Confirmed copies: 37 of 40 — floor met (0.93 ≥ 0.80)"**; step 4 becomes **"Prepare the documents"**; readings are counted separately ("Readings answered 2,903 of 2,936"). The floor is worded as "a confirmed usable copy"; reading and review are checked separately before signing | 3, 4, 5, 11 |
| **R2** overstated interpretations among usable results | a result whose interpretation check failed sat beside usable ones, and one label mixed two meanings | Only reviews that pass (`evidence.USABLE_REVIEW`) are **usable**. Overstated and not-applicable annotations move to **"Not used in this profile · 38"**, with the reviewer's reason. Each card labels two dimensions apart: **Relation to the question** (supports / contradicts / qualifies) and **Interpretation check** | 9, 10, 12 |
| **R3** operational questions | the wizard promised a verdict for every question | Q08 (operational) shows "Tracked in this project; no literature verdict applies" everywhere: wizard, journey, flow, export. "2 of 7 ready" counts only literature questions | 3, 5, 11, 13 |
| **R4** authorization before paid work | the side rail showed annotation running before its budget was approved | Start authorizes one exact plan: searches, copy requests and model work **up to USD 12.00**, with cap, estimate ("not yet known"), and reserved unknown cost shown apart, and an attestation box. Step 6 becomes a **conditional checkpoint**, reached only when the measured work outgrows the cap: cap 12.00 · spent 11.42 · reserved 0.34 · remaining 0.24 · estimate 6.05 · proposed 18.00 | 3, 4, 5, 7, 14 |
| **R5** partial and overlapping progress | the archive said step 7 while the project said step 6; counts did not add up to 128 | One sentence for both ("Review partly complete · 2 ready to sign"); half-filled segments for partly done steps. Status counts are a partition (4 drafts + 6 running + 2 paused + 116 finished = 128), finished split into 97 signed / 19 closed without verdicts; "Needs you · 3" is a separate filter labelled as overlapping | 2, 5, 15 |
| **R6** scope and history | a project with an update round had no way to say which round a number belonged to | Research-flow selector (Initial research · October update) with **History** (including a legacy round, protocol not verified); scope and protocol on every page's header or breadcrumb; "Propose a change" previews the differences and opens a linked flow under v2 | 5, 8, 11, 12, 13 |
| **R7** desk validation and context | eligibility was incomplete; zero results and changed evidence were not designed | No verdict selected initially; the requirement list covers verdict, reasoning ≥ 120 trimmed characters, attestation, authenticated identity and server checks; per-class counts of results, annotations and sources; context fields per kind (method: support type). Two variants: Q06 complete with **zero usable results** (everything examined stays inspectable; NEVER_ASKED defined as established by screening, never inferred from zero), and **profile changed while reading** (9340389c → 51d07a2e: the draft is kept, the change is listed, signing is blocked until reviewed) | 9, 10 |

### Then: the scheduler (S1–S4)

| finding | problem | change | boards |
|---|---|---|---|
| **S1** Right now | one sentence could not say what runs, what is next and whether the worker is alive | **Now / Next / Waiting**, **worker last seen**, **last completed**, **Pause project**, **View authorized plans**; Pause lets the request in flight finish; Resume continues the same plan, keeping completed work and remaining authorization | 5, 15 |
| **S2** decisions block only their dependants | "the scheduler waits on each one" suggested one decision stops the whole project | Every card says **Blocks / Continues / Enables** and **required or optional**; the cap checkpoint is the same object on the journey and in Decisions. **Declined, deferred, obsolete** have their own states and a "Decided recently" list with the consequence | 1, 5, 7, 15 |
| **S3** bounded plan previews | a retry or campaign was authorized from a partial description | Plan previews state indexes or hosts, request limits, robots.txt and the failure budget, and are the **server's exact preview**, refreshed when the selection changes | 4, 7 |
| **S4** Today and activity | no answer to "what changed since I was last here"; no way to tell an old event from live work | **Today**: what changed, what needs you (required vs optional), what continues without you. **Activity**: readable events linked to sources and questions; started, completed, retried, interrupted, declined told apart; "4 new events — show" never moves the page under the reader | 1, 6 |

### Then: the missing paths (P1–P3)

| finding | problem | change | boards |
|---|---|---|---|
| **P1** material intake | adding a source was possible only from a below-floor decision card | Permanent **+ Add material** on the journey: reference, DOI, link, PDF, supplement. Target scope is chosen explicitly; a frozen cohort accepts only copies or versions of its own candidates, anything new goes to a new round. Each item shows received → file checks → identity → duplicate/version → outcome. The same file twice is recognised by hash; a possible earlier version becomes an identity decision, recorded with a reason and **never merged** | 5, 7, 8 |
| **P2** verified purchase offers | buying a copy had no card; a 403 could be mistaken for an offer | A card for a **verified** offer only: work and version, vendor, price and currency, tax if known, terms, verification time, what the copy might resolve. Four separate stages: **approved → bought externally → copy provided → copy verified**; a changed offer needs a new decision. The value is stated without promising a result or a verdict | 7 |
| **P3** export | export existed only on the CLI | Snapshot of one flow with scope, protocol, provisional/final, signatures per question; earlier snapshots with an explicit **Verify**; implemented formats (manifest, CSV, report.md) marked apart from proposed ones (PDF/DOCX report); source PDFs off by default and limited by licence | 13 |
| **P3** administration | in the menu with no page | Model backends (configured, runner present, last check) with explicit **Check reachability** and **Paid test call…**; credentials as **presence only**, with write-only Replace/Add; services (scheduler, GROBID, API, code revision, instruments); acquisition conduct; spending by authorization (cap, spent, reserved, remaining) | 14 |

### Visual and cross-board consistency (§6) and scenarios (§7)

- **Two funnels with units** on the evidence path: copies (unit: sources) and evidence (unit: annotations, then
  results), so it cannot be read as one retention rate.
- **v1 boards brought into v2:** Flow and Lineage use the v2 sidebar, show scope and protocol, and keep the
  return path to the exact question and result ("← Back to Q04 · result 1 of 4").
- **States board:** loading, empty, unknown ("—" with a reason), failed (the rest of the page stays usable) and
  stale (values kept, labelled with their time).

## 4. Where this proposal departs from the review

Each point quotes the finding and gives the alternative adopted.

1. **§6, "preserve the palette if desired, but use distinct labels, placement and component shapes".** Labels
   and shapes were not enough on their own: on the journey a blue "Claimstone running" chip sits a few
   centimetres from a blue "contradicts" chip. **Alternative:** the Claimstone actor is now **teal**
   (`#0d9488` / `#ccfbf1` / `#115e59`), and blue is reserved for *contradicts*. Completion is a check
   circle on a step; *supports* is a pill on a result. Colour still never carries meaning alone.
2. **R7, "opened N of M".** The review asks to finish the desk's validation. Making "opened every result" a
   condition of signing would turn clicks into a claim of reading, which the server cannot verify.
   **Alternative:** "opened" stays as a **reading aid** that never gates signing. Signing is gated by the
   verdict, reasoning ≥ 120 trimmed characters, the attestation, authenticated identity and the server's
   current-profile checks.
3. **Below the floor ≠ "waiting for you".** v2.0 showed a below-floor project as waiting for the user, which
   implies an action is required. **Alternative:** "Paused · below floor 0.56 of 0.80 · authorized routes
   exhausted · you may add material". The user may act, but nothing is pending on them.
4. **R4, budget timing.** The review asks that authorization precede every paid activity. A separate
   approval for annotation, and another for review, would put two consent screens in front of a first-time
   user before anything is measured. **Alternative:** one authorization at Start covers annotation and review
   up to a cap. Step 6 appears only if measured work needs more than the cap. Nothing beyond the cap is ever
   spent.

## 5. The shared illustrative dataset

Every board uses these values. A value changed on one board must be changed on all of them.

| item | value |
|---|---|
| project | News tone and returns · protocol v1 frozen 28 Sep · 8 questions: 7 literature, 1 operational (Q08) |
| flows | **Initial research** (frozen cohort, 40 candidates: ACA 30, WP 10) · **October update** (started 5 Oct, 25 candidates, copies 12 of 25) · 1 legacy round in history |
| copies | 38 obtained, **37 confirmed** (ACA 28/30, WP 9/10) · floor 0.93 ≥ 0.80 · not obtained S14 (HTTP 403), S31 (bot challenge) · S23 obtained, not a document |
| evidence | 37 copies → 734 passages · readings 2,903 / 2,936 (33 open: Q01 5, Q05 28) · 1,992 annotations, 1,721 kept, 271 rejected · 60 reviewed |
| questions | **Q04** ready to sign, 4 usable results from 4 sources (ACA 3, WP 1): supports 1, contradicts 1, qualifies 2, profile 9340389c · **Q06** ready to sign, 0 usable results (18 reviewed, 9 gate-rejected) · Q01, Q02, Q03, Q05, Q07 still being read · Q08 operational |
| budget | cap USD 12.00 · spent 11.42 · reserved 0.34 · remaining 0.24 · estimate 6.05 · proposed 18.00 |
| decisions (6) | required: raise the cap; sign Q04; sign Q06; S33 identity (possible earlier version of S12). Optional: retry S14/S31; verified purchase offer for S14 |
| scheduler | worker last seen 20 s ago · last completed 4 min ago (S27 copy confirmed) |
| other projects | 128 in total · Screen time and wellbeing annotating, USD 3.10 of 9.00 · one project paused below floor 0.56 of 0.80 |
| variants | Q04 profile changed to 51d07a2e (S28 no longer usable, 4 → 3) · cap declined · protocol v2 adding Q09 · heartbeat expired — each is drawn **as a variant** and does not change the main dataset |

## 6. §7 scenario coverage

| scenario | where it is shown |
|---|---|
| New research with no candidates | 15 (December update: scope declared, copies "—") · 4 (no coverage percentage before candidates exist) |
| Extraction uses a paid model | 4 (authorization at Start, attestation) · 3 (side rail) · 5 step 1 |
| Q04 ready, other reviews awaiting budget | 5 (steps 6–8, questions list) · 1 · 15 |
| One copy route blocked | 15 (host paused, other routes and annotation continue) |
| Scheduler heartbeat expires | 15 ("Status being checked", worker last seen 9 min ago) |
| A retry plan is resumed | 15 (paused October copy plan resumed: 11 of 25 kept) · 5 (Pause/Resume rule) · 7 (retry plan preview) |
| Operator declines or defers | 7 (Decided recently) · 15 (consequence of declining the cap) · 6 (declined event) |
| PDF uploaded twice or earlier version found | 8 (same hash; S33) · 7 (identity decision with reason) · 15 |
| Verified purchase offer | 7 (four distinct stages) · 1 |
| Complete eligible profile, zero usable results | 10 variant A |
| Profile changes during reading | 10 variant B |
| Protocol revision or scheduled update | 15 (protocol v2, monthly update scope) · 5 (Propose a change; flow selector) · 1 (next run 1 November) |

## 7. Available now versus needs backend

The current portal is read-only by decision (D82, D84). "Available now" means the read API or an existing CLI
command already provides the data; it does not mean the web control works.

| board | available now | needs backend |
|---|---|---|
| Today | decisions and changes derived from the ledgers | "since your last visit" (per-user marker, authentication); "continues without you" and next runs (scheduler queue) |
| Projects | project list, names, state words | drafts, pinning, scheduler run states |
| New project 1–2 | — (projects are YAML files today) | drafts, project creation, freezing the registry (invariant 5) |
| New project 3–4 | flow binding via `claimstone flow create`; search-plan previews as tools | authorization record, scheduler plan API |
| Journey | states, counts, floor, profiles, question cards | scheduler state and heartbeat, Pause/Resume, approvals, update flows |
| Activity | completed ledger writes | started, interrupted, retried events from scheduler operations |
| Decisions | identity candidates, refused sources | every action: decision, offer and campaign records; writer lock; authentication |
| Add material | — | intake record, quarantine, identity checks, URL guard, supplied-copy floor policy |
| Reading desk | profile, results, review labels, adjudication card | web signing (authentication, signer field, write path) |
| Desk variants | zero-result profile | draft persistence, profile diff |
| Evidence path | every figure in the read API | — |
| Provenance | the six-step lineage | — |
| Export | `claimstone export` / `export-verify` (manifest, CSV, report.md); exports ledger | web trigger, explicit Verify, PDF inclusion by licence, PDF/DOCX report |
| Administration | credential presence, configured backends and runners, instrument versions, code revision | reachability checks, paid test call, credential write, service health, cost ledger |
| States | "—" for unknown, stale/failed handling in `web/` | heartbeat, plans, Pause/Resume, decline records, protocol v2 flows |

Before any control can work, the backend needs what v2.0 already listed: authenticated identity, one writer
lock, new append-only records (drafts, protocol versions, authorizations with caps, campaigns, uploads,
identity decisions, offers, scheduler operations), the scheduler's interface, upload and URL safety,
server-side meaning, and web security (sessions, CSRF, the existing Host/Origin checks). v2.1 adds three:
a **cost ledger** per authorization (spent, reserved, remaining), a **per-user seen marker** for Today, and an
**evidence diff** between two profile hashes for the changed-profile variant.

## 8. Open dependencies (named, not invented)

- Whether operator-supplied copies count toward the floor is declared per project at step 3 and cannot change
  under the same protocol. The engine does not implement this policy yet.
- The purchase path needs a decision on who records "bought externally" and what evidence of possession is
  required.
- PDF inclusion in exports follows licences; the rule for an unknown licence is not decided (proposal:
  excluded and listed).
- Subscription and local backends show call counts instead of money. Converting them into a cost is not
  invented in the interface.
