# Research portal: adversarial review

**Status:** review of `2026-10-06-research-portal-design.md`, executed from
`2026-10-06-research-portal-review-prompt.md`. Read-only: no ledger written, no network request, no
model backend, no verdict. The only commands run were `pytest` on `tests/test_round_state.py` and
`tests/test_dashboard.py` (25 passed), plus a read-only count of the `round` field in the local
`candidates.jsonl` files.
**Date:** 2026-10-06. **Implementation spec derived from it:**
`2026-10-06-research-portal-implementation-spec.md`.

Labels: **[CODE]** means verified by reading the cited code. **[RUN]** means verified by running something.
**[INFER]** is a design inference. **[UNRESOLVED]** means the answer depends on data or intent this review
could not see.

---

## 1. Findings by severity

### Critical: these block safe construction

**F1. Several "scoped" reads are not scoped, and the spec names only three of them.** [CODE]
The spec says `_stage_normalize`, `activity` and `_last_write` read project-wide. These do too:

- `round_state.state` takes `claims, rejections = claim_records.current(store)`
  (`claimstone/round_state.py:239`) over the whole store. It drives the extract stage's `outputs` and
  `rejected` values (`:264-268`) and `rejections_by_reason` (`:295-298`).
- `review.current(store)` (`:271`) is project-wide, so the review stage's progress uses a whole-store
  denominator.
- `chunk_count = len(chunk_sets.current(store))` (`:214`) is the extract stage's `inputs`, also
  whole-store.
- `_question_spine` re-reads `claim_records.current(store)` (`:334`), and the per-question `claims` and
  `claims_by_class` figures count every round's claims.
- `admissibility.rate`, which **is the floor computation**, uses three project-wide values:
  - `confirmations(store)` (`admissibility.py:108`), and `started = bool(confirmed_rows)` (`:169`). A
    round in which nothing has been normalized therefore switches its basis from `obtained` to
    `confirmed` because a *different* round has documents. The effect is conservative (it lowers the
    figure), but the floor figure of one round then depends on another round's activity.
  - `any(store.read("ledger_repairs.jsonl"))` (`:187`). A torn tail repaired in any round makes every
    round non-final.
  - `collapse(store)` keyed by `candidate_key` is correctly filtered by key at `:90`.

`synthesize.preview` / `profile_inputs.collect` are correctly scoped through `population()` and `confirmed`
(`profile_inputs.py:15-34`). The profile and the dashboard spine therefore **already disagree** on claim
counts for a project with two rounds. `alembic-s4-lungo` has two rounds today
(`s4-open-copies-v1`: 21 candidates, `s4-l02-search-2026-09-29-v1`: 13) [RUN].

**F2. Errors are converted into "unknown" or zero, including `LedgerCorrupt`.** [CODE]
- `round_state._stage_acquire` uses `except Exception: admitted = None` (`round_state.py:179`).
- `_stage_normalize` uses `except Exception: acquired = 0` (`:211`). A corrupt `acquisitions.jsonl`
  therefore renders as *zero acquired*.
- `state()` turns any exception from `synthesize.verdicts` into `unavailable=str(exc)` (`:247`), which
  puts corruption and `NotAdmissible` in the same box.
- `_profiles_for_spine` returns `[]` (`:326`).

The spec's acceptance test "corrupted ledger surfaced instead of zero counts" fails against the code it
proposes to reuse. This is the defect class `store.py:13-15` exists to refuse.

**F3. Selector semantics differ between modules, so "exact selector" has no single meaning yet.** [CODE]
- `round_state._stage_discover` matches `str(row.get("round") or "routine") == round_name`
  (`round_state.py:149`).
- `admissibility.rate`, `profile_inputs.population` and `acquire.eligible_candidates` match
  `row.get("round") == round_name` (`admissibility.py:83`, `profile_inputs.py:19`, `acquire.py:295`).
- The CLI `_acquire` population check also uses the `or "routine"` form (`cli.py:136`).

A candidate row without `round` belongs to round "routine" for discover and to no round for admission.
This is latent: no local candidate lacks `round` today [RUN]. The spec also treats the selector as one
`round`, but HANDOFF quotes **cumulative** figures over two rounds ("cumulative 22/34"). The engine
expresses that only as `round_name=None`, meaning the whole store. A flow selector must be able to name
"one round", "the whole store" and, later, "a set of rounds".

**F4. Frozen protocol versus live configuration: the engine always judges with the live project.** [CODE]
`admissibility.admit` reads `project.acquisition_floor` and the class floors from the loaded
`sources.yaml` (`admissibility.py:225-241`). `profile_inputs.collect` filters claims by the *current*
`project.registry_version` (`:36-40`). A flow snapshot that stores "acquisition floor" therefore cannot
be *used* to compute anything without making the portal disagree with the CLI. That would break the
spec's own rule that "CLI and portal must agree".

The snapshot can only be **checked**. When live digests differ from the flow's frozen digests, the flow
is `PROTOCOL_DRIFTED` and is read-only. Floors also have no drift ledger analogous to `registry.jsonl`:
nothing refuses a floor value edited under an unchanged `floor_version` (`config.py:669-695` validates
provenance fields only). [CODE] [INFER]

**F5. Writers do not share a lock, and acquisition reads its retry state once.** [CODE]
- The only lock in the package is `.source_selection.lock`, private to `source_selection.append_observations`
  (`source_selection.py:188-196`).
- `acquire.run` reads `previous = store.latest_by("acquisitions.jsonl", ...)` once (`acquire.py:344`).
  Two concurrent acquires (CLI plus portal job) both attempt the same candidate, repeat the publisher
  request and append duplicate `attempt_no` values (`:376`).
- `synthesize.adjudicate` recomputes `preview` and then appends with no lock (`synthesize.py:200-230`).
  A concurrent `synthesize` can change the stored profile between the check and the append.

"One effective lock" is necessary but not sufficient. Every stage writer must take it, and the existing
source-selection lock must become the same lock, or be nested under it in a fixed order, to avoid
deadlock.

**F6. The per-domain failure budget lives in memory per process.** [CODE]
`Fetcher._host_failures` is an in-memory dict (`net.py:149`), documented as "One fetcher per run". Each
new process, and each concurrent portal job, starts with a fresh budget. SCHEDULER_BACKLOG already
requires that "A new worker/process cannot reset the effective host budget" (`SCHEDULER_BACKLOG.md:24`).
The spec's "jobs" design multiplies requests to a refusing host until this is fixed. The data to fix it
already exists: `requests.jsonl` records every `failure_class` with `recorded_at`
(`docs/contracts/requests.md`).

**F7. Stage commands other than discover and acquire are not round-scoped, so a per-flow preview or cost
estimate would be wrong.** [CODE]
`normalize.run(store, ...)` (`cli.py:357`, `normalize.py:72`), `extract.build(project, store, batch=,
limit=, kind=)` (`cli.py:649`) and review build all take no selector. "Start extraction for flow X" with a
priced preview would queue, and bill, every flow's chunks. Until scoped builders exist, the portal must
not offer execution of these stages. A preview may only state that the effect is project-wide.

### High

**F8. The portal would reverse three explicit clauses of the dashboard spec without a decision entry.**
[CODE]
- `2026-09-22-dashboard-design.md` §1: "never triggers work".
- §8 rule 7: "no route mutates anything, no button starts a fetch".
- §13: "No multi-project view. One `serve` per project".

The proposal changes all three (§13 already in Phase 2). CLAUDE.md says these are not to be relitigated
silently. A dated D82 must record which clauses are superseded and why. Phase 2 stays read-only, so only
§13 changes there.

**F9. The long-running server holds a stale project configuration.** [CODE]
`_serve` calls `load_project` and `_checked_store` once (`cli.py:936-947`), and the handler keeps that
`Project` for its lifetime. Editing `questions.yaml` or `sources.yaml` while serving gives the dashboard
the old registry and floor, while the CLI uses the new ones. A multi-flow portal must reload, and recheck
registry drift without recording (`check_registry_drift(..., record=False)`), on every request.

**F10. The spec's flow snapshot freezes the candidate population, but rounds grow by design.** [INFER]
Candidates enter a round through `discover` *after* the round is declared. `population.check_round`
already freezes the **predicate**, not the set (`population.py:64-83`), and refuses retrofits. A flow
must freeze inputs (project input digests, registry, floor provenance, population predicate, selector),
not outputs. Only a closed manifest or cohort has a frozen candidate set. The spec should reuse
`populations.jsonl` and `registry.jsonl` instead of duplicating them.

**F11. Code identity of the executing instrument is absent from the spec. This is D42's lesson.** [CODE]
D42 records a re-normalize that ran stale code because the container image predated the fix
(`DESIGN_DECISIONS.md:1937-1948`). `normalize` can only run in the container (`AGENTS.md:35-38`). A portal
that launches work from the host must record, per operation, the git commit, dirty-tree flag, container
image ID and every instrument version. It must refuse execution when the host code and the image differ.
For read-only Phase 2 the same point applies to display: show the code revision the page was computed
with.

**F12. Invariant 1 lineage needs `copy` and `document generation`, not only "quote → chunk → document →
copy/attempt".** [CODE] [INFER]
Chunks belong to a committed chunk generation (D48, `chunk_sets.current`). Documents are keyed by
`source_id` and re-normalization supersedes them. Lineage must name `chunk_set` / generation and the
document row's parser version (`html_parser_version`, `jats_parser_version`, GROBID image digest).
Otherwise an export cannot show which instrument produced the text a quote was checked against.

**F13. "Purchase prioritization by favorable result direction" is forbidden in words but not by
mechanism.** [INFER]
The inbox ranks by "urgency and affected flow/question". If urgency uses anything derived from claims,
reviews or stances (for example "this source would add a SUPPORTS result"), the operator buys or uploads
selectively by outcome. The bias is invisible in the floor figure. Inbox ordering for access and intake
cards must be a pure function of acquisition metadata and frozen denominators, and must be testable as
such.

**F14. Human-supplied copies change the acquisition numerator, and the spec does not say how.**
[CODE] [INFER]
An imported copy must become an `acquisitions.jsonl` row, or it never counts and never normalizes.
`provenance: store-reuse` is the existing precedent for a non-network acquisition row
(`contracts/acquisitions.md:55-66`). It is re-gated, carries an empty `attempts` list and keeps unknown
licence values. Whether operator-supplied copies count toward the floor is a **scientific policy** to
declare in advance, per project, under a floor/population version. It must not be decided card by card.
Until declared, imported copies should be reported as a separate numerator line.

**F15. URL safety is scheme-only.** [CODE]
`Fetcher._get` rejects non-http(s) and excluded hosts (`net.py:254-257`). It does not refuse loopback,
private, link-local or metadata addresses, and does not re-check those after a redirect. Today URLs come
from scholarly APIs. Once an operator or a pasted publisher link can supply one, it is an SSRF vector
from the operator's own machine. The spec's "URLs are data for validated acquisition routes" needs a
concrete rule: resolve, refuse non-global addresses, re-check on every hop.

### Medium

**F16. `adjudicated_by` is free text** (`synthesize.py:227`, `cli.py:926`). The spec requires
authenticated identity for portal signatures but does not say what happens to CLI signatures. Two
signature classes must remain distinguishable: add `signer_auth` (`cli-declared` / `portal-session`)
under a bumped `decision_contract_version`, never reinterpret old rows. [CODE] [INFER]

**F17. Activity time ordering mixes timestamp keys and mtimes** (`round_state.py:64-65`, `:137-142`).
Rows without a known key take the file mtime, so "newest first" across ledgers is not a trustworthy event
order. A live stream needs a per-ledger byte offset as its cursor, not a time. [CODE]

**F18. Contract drift:** `docs/contracts/requests.md` says `fetch_version` "currently 2", while
`net.py:22` has `FETCH_VERSION = 3`. A portal that documents fields from contracts will mislabel this.
[CODE]

**F19. `PAYWALL_403` is a stored failure class whose name asserts the inference the spec forbids**
(`net.py:32`). HANDOFF already says it "does not independently establish a paywall". The UI must display
it as `HTTP 403 (access refused)` with the stored code beside it. It must never map it to an Offer state.
[CODE]

**F20. Operational questions and `NO_VERIFIED_CLAIM`.** The spec's question matrix does not mention that
`kind: operational` rows carry `LITERATURE_VERDICT_NOT_APPLICABLE`, nor that `NO_VERIFIED_CLAIM` is an
engine state and not `UNANSWERED_IN_LITERATURE`. The dashboard handles both (`dashboard.py:36-45`). The
matrix must keep the same vocabulary. [CODE]

### Low

**F21.** The prompt cites D42 as relevant. Its subject is the HTML parser version. Its operational lesson
(stale image, instrument identity) is what applies here, and it is captured as F11.

**F22.** AGENTS.md and README quote 1026 passing tests and 64 or 68 decisions. HANDOFF quotes 1,063. A
portal "health" page must compute such figures, not quote them.

---

## 2. Scientific and provenance checks

| Check | Status in the proposal | Required change |
|---|---|---|
| Frozen protocol identity | Snapshot is stored but cannot drive computation (F4) | Freeze digests; **check** and mark `PROTOCOL_DRIFTED`; never compute with snapshot values |
| Cohort/selection boundary | Correct: D79–D81 advisory, no admission | Keep `AI_PROVISIONAL` visibly labelled; no "accept AI exclusion" control anywhere |
| Acquisition denominator and floor | Uses existing admit, but the basis/repairs leak across rounds (F1) | Scope `confirmations` and `ledger_repairs` per selector before any portal display |
| Quote lineage | Missing chunk generation and parser instrument (F12) | Lineage tuple: claim → gate revision → chunk id + chunk set → document row + parser version → acquisition row + `sha256` → attempt |
| Question registry | Live registry versus frozen flow (F4, F9) | Per-request reload; `check_registry_drift(record=False)`; drift is a displayed state |
| Source classes | Fine in principle | Every count in the matrix and export is per class first, then pooled (invariant 6) |
| Verdict signature | Free text today (F16); TOCTOU (F5) | Signing is out of scope until Phase 4; then lock plus `signer_auth` field |
| Historical comparability | "legacy: protocol not verified" is correct | Also compare instrument versions (`profile_version`, `claim_gate_version`, `gate_version`, parser versions) before a comparable-flow view |
| Export consistency | Prefix-offset idea is right | Offsets must be **byte** offsets ending at a newline; a torn tail is excluded and reported |

## 3. Workflow and security checks

| Area | Finding | Requirement |
|---|---|---|
| Source and paid-copy intake | Numerator policy undefined (F14) | Declared policy; separate numerator line until declared; re-gate through `fulltext.classify` |
| Vendor offer verification | "Retained proof" implies fetching vendor pages | That fetch is a network operation under the same conduct rules; proof is stored content-addressed under `store/<p>/offers/`, never in git |
| Human authorization | Required, mechanism unspecified | Phase 4: local session token (loopback, random, printed on start), plus `os_user`; never a free-text field alone |
| Idempotent writes across CLI/worker/portal | No shared lock (F5); acquire reads state once | Project lock `store/<p>/.writer.lock` taken by every writer; acquire rereads per candidate under the lock |
| Job recovery | Leases proposed | Reuse `calls/<lane>/<batch>` resumability; leases only for network/model jobs; recovery reads ledgers, never job memory |
| Secrets | `.env` plus compose environment (`compose.yaml` env block) | Admin shows presence only (`bool`), never length or prefix; rotation edits `.env` outside the portal in Phase 2 |
| Local web security | The dashboard has loopback, GET-only and escaping | Add Host-header allowlist and `Origin` check now (DNS rebinding applies even to GET of private data); CSRF token only once mutating routes exist |
| Unsafe URLs | Scheme-only check (F15) | Resolve and refuse non-global IPs on every hop before any operator-supplied URL is fetched |
| Purchases | Correctly outside the portal | Receipts can hold personal and payment data: stored under `store/<p>/private/`, excluded from export by default |

## 4. New ideas and challenges to the spec's ideas

| Idea | User benefit | Cost | Phase |
|---|---|---|---|
| **Next-command cards** (inbox shows the exact CLI command per blocker, copyable, not executed) | Removes most of the operator's command assembly with no write path and no new authorization surface | Low | 2 |
| **Integrity panel** (validate, instrument check, torn tails, `ledger_repairs`, orphans, registry drift, code revision versus image) | One place to see "can I trust these numbers now" | Low | 2 |
| **Floor deficit arithmetic** (per class: confirmed / found, floor, the number still needed, how many in each failure class) in place of the "coverage simulator" | Same decision value as the simulator, with no hypothetical acquired state | Low | 2 |
| **Profile change explainer** (when a signature is stale: which claims/reviews/rejections/chunks differ between the signed and current `evidence_sha256`) | Re-reading after staleness drops from whole-profile to diff | Medium (needs stored evidence inputs per profile or recomputation at two prefixes) | 2b |
| **Blinded human-reference labelling** (for D73/D74's 20 blank decisions: AI labels hidden until the human submits) | Unblocks every screening measurement the project is waiting on | Medium; new ledger and contract | 3 |
| **Persistent host budget** derived from `requests.jsonl` at `Fetcher` construction | Fixes F6 for CLI and portal alike | Low–medium | 0 (prerequisite of any job) |
| **Spending view** derived from call ledgers versus the operator's recorded authorizations | Replaces hand-carried USD accounting in HANDOFF | Medium | 3 |
| **Reading workbench** for adjudication (profile, passages, flags, shown-hash; signs through `synthesize.adjudicate`) | Shortens the only human-only step | Medium–high; needs authentication | 4 |
| **Export verify** (recompute manifest from the recorded offsets) | Makes an export checkable by a third party | Low once export exists | 2 |

Challenges to the spec's ideas:
- The **coverage simulator** invites "buy until it clears". HANDOFF: "downloading unrelated papers solely
  to raise the floor is not the next scientific step". Replace it with deficit arithmetic.
- **Saved bounded operation plans** already exist as frozen `plan.json` files under `audits/`. The
  portal should list and preview them, not invent a second plan format.
- **Live event stream**: polling (as the dashboard does) is enough and simpler than SSE; use byte-offset
  cursors.
- A **typed API plus workers plus leases** contradicts the compose file's recorded refusal of a service
  per stage (`compose.yaml` header). Execution should stay "spawn the existing CLI as a subprocess, record
  the operation". No in-process stage execution.

## 5. Edited design proposal: exact wording changes

1. Replace "exact selector (`round`, `manifest_only`)" with: "a selector `{rounds: [names] | "*",
   manifest_only: bool}` evaluated by one canonical predicate in `claimstone/scope.py`, which every
   reader and builder uses".
2. Replace "The snapshot includes exact contents and digests ... candidate population or selection
   inventory" with: "The snapshot includes digests of the project input files, the registry digest and
   version, floor provenance, the population predicate digest from `populations.jsonl`, and the selector.
   A frozen candidate inventory is included only for closed cohorts. The snapshot is checked against the
   live project on every read; it never supplies values to a computation."
3. In "Honest state model", add a fourth scientific-usability value: `PROTOCOL_DRIFTED`.
4. Replace the `round_state.py` paragraph with the F1 list, and add: "`except Exception` that maps a
   ledger error to `None`/`0` is removed; `LedgerCorrupt` renders as `LEDGER_CORRUPT` and blocks every
   figure that depends on that ledger."
5. In "Acquisition, offers and human-supplied copies", add: "An imported copy is an `acquisitions.jsonl`
   row with `provenance: operator-supplied`, re-gated by `fulltext.classify`. Whether such rows count
   toward the floor is declared in `sources.yaml` under a floor version before any are imported. Until
   then they are reported as a separate numerator line."
6. Add to "Operations and security": "Every operation records git commit, dirty flag, container image ID
   and all instrument versions (D42). Execution is refused when host code and image differ. Normalize,
   extract and review are not offered for execution until their builders accept the flow selector."
7. Add: "The per-host failure budget is derived from `requests.jsonl`, so it survives processes and is
   shared by concurrent jobs."
8. Add: "Inbox ordering for access and intake cards uses only acquisition metadata and frozen
   denominators, never claims, reviews or stances. A test enforces this."
9. Remove idea 4 (coverage simulator). Replace it with "floor deficit arithmetic".
10. Add a decision entry D82 that supersedes dashboard spec §13 (Phase 2), and §1 and §8.7 only when
    mutating routes ship (Phase 3/4).

### Implementation order with acceptance tests

| Step | Content | Blocks |
|---|---|---|
| **P0 (prerequisite)** | `scope.py` canonical selector; fix F1/F2/F3 in `round_state` and `admissibility`; tests with two rounds | everything |
| **P1** | `flows.jsonl` plus `claimstone flow create/list/check`; drift detection | portal flow pages |
| **P2** | read-only multi-project portal: index, flow overview, question matrix, lineage, inbox with next-command cards, integrity, admin presence | none of the writes |
| **P2b** | `claimstone export` / `export-verify` with byte-offset prefixes | — |
| **P3 (blocked)** | project writer lock across **all** writers; persistent host budget; SSRF guard; intake/offer/decision contracts and policy decision on operator-supplied copies | any mutating route |
| **P4 (blocked)** | session authentication, operations ledger, subprocess jobs, signing workbench | — |

Blocking prerequisites for P3/P4: F5 (lock), F6 (budget), F7 (scoped builders), F14 (numerator policy,
the operator's decision), F15 (URL guard), F16 (decision contract bump).

**[UNRESOLVED]** Whether operator-supplied or purchased copies may count toward the floor is a
scientific-policy question for the operator. Verify by recording the decision as a dated entry before
P3.
