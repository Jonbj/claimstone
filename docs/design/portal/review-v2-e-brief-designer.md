# Claimstone portal v2 — revised review and designer brief

**Date:** 2026-10-06. **Revision:** 2, based on the complete local design package.

**Status:** review and proposed refinements of the approved design direction. This document supersedes the earlier review based on the operator's partial description. It does not change the scientific contract or claim that the proposed controls are implemented.

## 1. Material reviewed and limits

Read [the complete v2 description](v2/README.md) and all seven board sources:

- [Projects](v2/V2Projects.html)
- [New project](v2/V2NewProject.html)
- [Project journey](v2/V2Journey.html)
- [Reading desk](v2/V2Desk.html)
- [Decisions](v2/V2Decisions.html)
- [Evidence path](v2/Flow.html)
- [Claim provenance](v2/Lineage.html)

Reference artifact: <https://claude.ai/artifact/1kN6YgEjTwavVyxzCyWoLf>.

The HTML was inspected as source, including copy, controls, structure and declared styles. The canvas runtime is unavailable locally, and the hosted boards could not be loaded through the available reader. This is a content, interaction and contract review, not a rendered visual or accessibility audit. All board figures and quotations are illustrative.

The existing boards and their README remain the designer's source material. This review requests targeted revisions rather than silently editing them.

## 2. Revised assessment: preserve the guided journey

The complete proposal is substantially more developed than the partial description suggested. Its central promise is appropriate: describe the research, approve a bounded start, then follow Claimstone's work and make the necessary decisions in the web interface.

These capabilities are already present and should be retained:

| Existing design | Assessment |
|---|---|
| Projects archive, search, filters and at most five pinned projects | Appropriate for a growing collection; do not replace this with a sidebar listing every project |
| Eight-step journey with Claimstone/you actors | Makes responsibility understandable; refine its state model rather than replacing the layout |
| Right now card | Already explains current work or a pause; extend it with next action and trustworthy liveness |
| Decisions executable in place | Already covers budgets, retry campaigns, copies and identity resolution |
| PDF quarantine, identity and content checks | Already specified, including the declared policy for contributions to the floor |
| Reading desk with authenticated signature | Already binds the decision to the exact profile and handles evidence changing before signing |
| No preselected verdict in the product | Explicit in the README; the checked radio in the static board demonstrates a user-selected state and is not evidence of a default verdict |
| Protocol versioning and stale signatures | Already specified; add history and change-preview views |
| Server-owned labels, states and next actions | Correct; keep the same decision semantics on Journey and Decisions |
| Backend prerequisites | Already names authentication, shared writer coordination, new records, scheduler integration and URL/upload safety |

The first review's suggestions to add these capabilities are superseded. The remaining work is to correct specific inconsistencies, finish missing paths and make the scheduler's behavior precise.

## 3. Corrections needed before implementation

### R1 — Acquisition is not completed reading

**Evidence:** README §5 board 2 describes the floor as the share that “must be read”; Journey step 1 repeats this. Journey's “Evidence so far” labels 37/40 as “sources read”, while step 3 establishes 37 confirmed copies.

**Why it matters:** a confirmed document, a parsed document and a completed scientific reading are different events.

**Designer instruction:** replace the floor explanation with:

> At least 80% of the candidates in this declared search scope must have a confirmed usable copy. Reading and independent review are checked separately before a verdict can be signed.

Use “Confirmed copies: 37 of 40” for that figure. Show completed reading using its own server-supplied measure. Rename step 4 from “Read the documents” to “Prepare the documents” when its output is parsed passages. Preserve per-class floor information and the fact that discovery does not measure all literature in existence.

**Priority:** required.

### R2 — Keep rejected interpretations out of usable results

**Evidence:** Reading desk includes a “Contradicts” result labelled “second reader: overstated” among its four results. In the evidence implementation, only interpretation reviews labelled SUPPORTED enter usable results. Overstated and ambiguous annotations remain visible in audit counts but are not usable profile results.

**Why it matters:** the board gives an interpretation that failed review the same evidential role as a reviewed result.

**Designer instruction:** choose a coherent illustrative case. A usable result may contradict the research question while its review says the interpretation is supported. If keeping the overstated example, move it to “Not used in this profile”, show the reviewer's reason, and update the usable-result counts.

Label the two dimensions explicitly:

- “Relation to the question: contradicts.”
- “Interpretation check: supported by the passage.”

Do not turn a reviewer's SUPPORTED label into a scientific verdict on the question.

**Priority:** required.

### R3 — Operational questions receive no literature verdict

**Evidence:** New project offers the operational kind but says “each one gets its own verdict” and “Each one receives its own verdict, signed by you.” The engine prevents adjudication of operational questions.

**Designer instruction:** qualify this promise and show an operational-question variant: “Tracked in this project; no literature verdict applies.” Do not show it as awaiting signature. Retain it in project listings.

**Priority:** required.

### R4 — Authorization must precede every paid activity it covers

**Evidence:** New project's side rail places “Read and annotate” before “Approve the reading budget”. Journey places approval at step 6, after extraction, for independent review. The general rule correctly prohibits spending without consent; the depicted sequence leaves extraction authorization unclear.

**Designer instruction:** finish “Review and start” with the initial search and model-work authorization. State whether it covers extraction, review or both. If review needs a later measured budget, keep that decision in the journey. Show an already-authorized state when no additional approval is needed.

Distinguish spending cap, estimated cost, amount spent, outstanding reservations and unknown cost. “[USD estimate]” must not stand in for the authorized ceiling.

The eight-step arrangement can stay if budget approval is a conditional checkpoint. Do not require an artificial new approval on every run or imply that extraction is always free.

**Priority:** required.

### R5 — Represent partial and overlapping progress truthfully

**Evidence:** Journey's accessibility label says steps 7 and 8 have not started, while its text says Q04 has completed 42 reviews and is ready to sign. Projects shows the same named project at step 7, whereas Journey says step 6.

**Designer instruction:** use the same illustrative state across boards. Show “Review partly complete; remaining batch awaiting budget” and “1 question ready to sign”. The journey can highlight the next decision without claiming that all later steps are untouched.

Show work running, work awaiting authorization and questions ready for a person as facts that can coexist. Accessible descriptions must match the visible state.

**Priority:** required.

### R6 — Add research scope and history without burdening a first-time user

**Evidence:** Journey offers protocol v2 changes, but the package does not show how multiple flows/rounds and their historical results are selected. The engine binds flows to a project, selector and protocol; it also has legacy scopes whose binding cannot be verified.

**Designer instruction:** keep one project row in the archive. In the project page add a compact “Research / update” selector and a history entry. Hide unnecessary complexity when there is only one research flow.

Every journey, desk, evidence path and export must identify the selected scope and protocol. A protocol change should show its differences and create a linked new flow. An update under the same protocol should still have an identifiable execution scope. Do not imply that switching tabs rewrites history or that arbitrary protocol versions can already run concurrently in the current backend.

At project level use an aggregate sentence such as “2 active research flows · 1 decision”, expandable into individual journeys. Do not combine incompatible denominators. Preserve “protocol not verified” for legacy material.

**Priority:** required for multiple flows and ongoing updates.

### R7 — Finish the desk's validation and evidence context

Authenticated identity, exact profile binding, no default verdict and stale-profile rejection are already correct. Keep the selected radio as a documented interaction variant; also show the initial unselected state.

Refinements:

- The “Sign enabled” explanation must include a chosen verdict, rationale of at least 120 trimmed characters, valid authenticated identity and the server's eligibility checks, alongside the proposed opened-result/attestation requirement. The character minimum is an existing engine rule.
- Opening a result records navigation; it does not prove comprehension. Keep “opened” distinct from the person's reading attestation. Do not add dwell-time or click-based claims of scientific validation.
- Add a complete profile with **zero usable results**. Present coverage, completed reading, gate losses and review exclusions; let the server determine whether adjudication is possible. Do not infer NEVER_ASKED from zero results. Its definition must mention screening within the declared scope.
- Give the signer context beyond the quote: relevant design, sample, horizon, estimate/uncertainty where applicable, source class, linked versions and unresolved limitations. Show fields appropriate to the question kind.
- Make per-class counts available before pooled presentation. Distinguish results, annotations and distinct sources; four result cards need not mean four independent studies.
- Replace “the other seven become ready as review finishes” with “the others become ready when their remaining checks pass”. Review completion alone does not establish every prerequisite.

**Priority:** required before implementing signing.

## 4. Scheduler refinements to add to the existing design

### S1 — Extend Right now into a useful operational summary

Keep the dark card. Add these fields through progressive disclosure:

> **Now:** reviewing 12 results.  
> **Next:** rebuild the evidence profile when this batch finishes.  
> **Waiting:** a separate copy route needs authorization.  
> **Worker last seen:** 20 seconds ago.  
> **Last completed activity:** 4 minutes ago.

A historical ledger event is not a live worker heartbeat. Show “Status being checked” or an interruption state when liveness cannot be established. Distinguish scheduler available, project queued, project running, scheduled for later and paused by the operator.

Add Pause, Resume and View authorized plan. Describe pause behavior while an in-flight request finishes. Resuming a still-valid plan preserves completed work and authorization. A changed scope or exhausted cap needs an updated proposal.

### S2 — Decisions should block their dependent work

“The scheduler waits on each one” and “releases the scheduler for that project” are too broad as universal rules. A missing PDF need not stop an independent review; Q04 can be ready while another question waits.

Each decision should show what is blocked, what can continue and what the action enables. Distinguish optional improvements from required intervention. Being below the floor is not automatically “Waiting for you”: authorized routes might still be running, or no valid human action may be available.

Show declined, deferred and obsolete decisions. “Not now” is not authorization; a resolved or declined item must not immediately reappear after refresh.

Journey and Decisions must display the same underlying decision. If resolved elsewhere, show the result rather than another actionable approval.

### S3 — Complete the bounded-plan preview

The retry card already specifies source count, hosts, request limits, robots and campaign name. Preserve this and extend it to initial search, missing metadata, alternative institutional routes and later updates.

Show scope, allowed destinations, transfer limits, affected questions and spending constraints. Clarify whether counts include redirects and robots checks. Changing selected checkboxes must refresh the server's exact preview before approval.

An unapproved redirect destination stops that route and requires a new proposal. A named campaign or configured scheduler does not authorize arbitrary hosts. Do not ask for consent again merely to resume authorized remaining work.

### S4 — Add Today and a browsable activity history

Today is in navigation but has no board in this package. Design it around:

1. What changed since my last visit?
2. Which decisions need me now?
3. What will continue without me?

Add a project activity stream with readable events, source/question links and expandable technical detail. Distinguish started, completed, interrupted and retried work. Do not move the viewport while someone reads; offer “N new events”.

For periodic research show the next planned run and remaining authorization, distinguishing this future capability from the current implementation.

## 5. Complete the source, purchase and output paths

### P1 — Broaden the existing copy action into persistent material intake

PDF upload and identity resolution are already designed. Keep them. Add a permanent “Add material” entry on the research page, available even when the floor is met or no decision card exists.

Accept a reference, DOI, URL, PDF or supplement. Show received, identity/content checks, possible duplicate/version, rejected or ready for controlled use. Make the target scope explicit and preview whether a new candidate belongs to an existing cohort or needs a new round.

A suggested source does not automatically expand a frozen cohort. A “Same work” or “A version of it” decision records an evidenced relationship; it must not silently merge studies, move candidates or count an additional independent study. Request a short reason and retain both records. Keep “Not sure” as pending.

### P2 — Add verified purchase offers

Purchase offers are not among the five decision types currently drawn. Add a card for an actual verified offer: work/version, vendor, price/currency, tax status if known, terms, verification time and the missing information the copy might help resolve.

Keep approval, purchase completed externally, copy provided and copy verified distinct. A changed offer needs an updated decision. An HTTP 403 is not an offer; a repository declaring no downloadable file is another outcome.

Explain potential value without promising a usable result or a particular verdict. Acquisition priority must not depend on whether findings appear to favor the research hypothesis.

### P3 — Add export and administration views

Show an export entry with scope, protocol version, snapshot date, provisional/final status and signature freshness. Make historical exports discoverable. PDF inclusion follows rights and operator choice. Mark proposed report formats separately from those already implemented.

Administration exists in navigation but has no board. Add configured model backends, verification/availability, secret presence, explicit credential-management actions, parser/service health, limits and cost accounting. Never expose stored secret values. Network health checks and paid test calls are explicit actions.

## 6. Visual and cross-board consistency

Keep the approved typography, sidebar, cards and Claimstone/you distinction. Actual legibility, contrast, keyboard behavior and responsive layouts still need a rendered review.

Specific refinements:

- Blue serves both the automatic actor and a scientific “Contradicts” stance; green serves completion and “Supports”. Preserve the palette if desired, but use distinct labels, placement and component shapes. Scientific disagreement must not look like a failed job.
- Evidence path changes units from documents to annotations to profiles. It already identifies its log scale and says annotations are not studies. Strengthen unit labels or split acquisition from evidence processing, so it cannot be read as one retention percentage. This is an optional clarity improvement.
- Bring the two v1 boards' navigation into v2, as the README already requests. Preserve the active scope and the return path to the exact question/result.
- The archive's status counts do not account for all 128 projects if read as an exhaustive partition. Make counts coherent or label partial/overlapping categories. Distinguish execution finished, archived and signed.
- Show empty, loading, failed, stale and unknown variants. An unavailable count is not zero. An empty queue does not establish completed scientific reading.
- The .dc.html links, runtime elements and external font references belong to canvas sources. They are not production routes or deployment assets. Translate them to app routes and bundled fonts during implementation; do not treat raw boards as runnable product code.

## 7. Deliverables requested from the designer

Revise the seven boards and their README, maintaining the guided journey. Do not rebuild the interface around ledgers or terminal commands.

### First: fix the existing story

1. Correct acquisition/reading wording and counters (R1).
2. Correct usable versus overstated results and review/stance labels (R2).
3. Add the operational-question exception (R3).
4. Make extraction and review authorization explicit (R4).
5. Reconcile partial progress across boards (R5).
6. Add compact scope/history and change preview (R6).
7. Complete signing eligibility, zero-result and evidence-context variants (R7).

### Then: complete the operational journey

Add variants or boards for Today, wizard steps 3/4, material intake, purchase offers, export and administration. Extend Right now and Decisions using S1–S4. Use variants of existing boards where they avoid unnecessary navigation.

Use one coherent illustrative dataset across linked boards. Document initial, selected, submitted and resolved states. Distinguish available functionality from controls that depend on future backend work.

### Scenarios the revised design must demonstrate

| Scenario | What the operator must understand |
|---|---|
| New research with no candidates | Scope is declared; coverage is not yet a meaningful percentage |
| Extraction uses a paid model | Authorization precedes the paid calls |
| Q04 ready, other reviews awaiting budget | Signing one question and blocked work on others can coexist |
| One copy route blocked | Other independent authorized work continues |
| Scheduler heartbeat expires | An old event does not prove work is running |
| A retry plan is resumed | Completed requests and approved budget are retained |
| Operator declines or defers | The consequence is visible; declined work does not execute |
| PDF uploaded twice or an earlier version found | It does not become a second independent study |
| Verified purchase offer | Approval, payment and validated possession are distinct |
| Complete eligible profile with zero usable results | Coverage and losses remain inspectable; no verdict is inferred from zero |
| Profile changes during reading | Draft reasoning can be preserved, but changed evidence must be reviewed before signing |
| Protocol revision or scheduled update | New work has explicit scope; history and signatures retain their meaning |

For each revision, add a short annotation explaining the operator problem it resolves. Where implementation policy remains unresolved, name the dependency rather than inventing scientific behavior in the browser.

## 8. Repository references

- [CLAUDE.md](../../../CLAUDE.md): invariants and operating rules.
- [Guide](../../GUIDE.md): confirmed acquisition versus obtained bytes and later reading.
- [Scheduler backlog](../../SCHEDULER_BACKLOG.md): bounded plans, resume, budgets and operator decisions.
- [Flow contract](../../contracts/flows.md): scope, protocol binding and history.
- [Profile and adjudication contract](../../contracts/profiles.md): completeness, signature freshness and operational questions.
- [Evidence implementation](../../../claimstone/evidence.py): usable reviews and fields by question kind.
- [Adjudication implementation](../../../claimstone/synthesize.py): verdicts, rationale minimum and current-profile checks.
- [Portal design](../../superpowers/specs/2026-10-06-research-portal-design.md): intake, offers, execution state and exports.
- [Design decisions](../../DESIGN_DECISIONS.md): D82/D84 for current portal boundaries; D79–D81 for advisory screening and identity.

This revision changes the designer brief only. The supplied v2 README and seven HTML sources remain unmodified for comparison and revision by the designer.
