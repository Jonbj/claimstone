# Prompt for Claude Code: research portal design review

Read `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/GUIDE.md`, `docs/HANDOFF.md`, relevant entries of `docs/DESIGN_DECISIONS.md` (especially D42 and D79–D81), and the relevant ledger contracts. Then review `docs/superpowers/specs/2026-10-06-research-portal-design.md` against the current code and tests.

The design is a proposal, not an implementation. The operator wants one portal per protocol-bound research flow, stage and question detail, live events, human source/PDF intake, purchase decisions, exports, and administration for keys and model connections. A GPT-6-astra review has already added the intervention inbox, question matrix, verified-offer states, flow identity, scoped data reads, and consistent export. Your job is an independent, adversarial review and further enrichment.

Please deliver:

1. **Findings ordered by severity:** verified defects or contradictions first, then plausible risks. Cite exact code, contract or decision locations. Separate observed behavior from inference.
2. **Scientific and provenance checks:** frozen protocol identity, cohort/selection boundary, acquisition denominator and floor, quote lineage, question registry, source classes, verdict signature, historical comparability and export consistency.
3. **Workflow and security checks:** source and paid-copy intake, vendor offer verification, human authorization, idempotent writes across CLI/worker/portal, job recovery, secrets, local web security and unsafe URLs.
4. **New ideas and improvements:** propose practical features beyond the current design that reduce operator time or improve scientific trust. Give a short user benefit, implementation cost, and recommended phase. Challenge weak ideas already in the spec.
5. **An edited design proposal:** give exact suggested additions, removals or wording changes and an implementation order with acceptance tests. Mark any prerequisite that blocks safe construction.

Preserve all seven `CLAUDE.md` invariants. Do not convert AI provisional screening into human reference or admission, and do not infer purchasability from an HTTP 403. Do not modify the repository, make network requests, run model backends, or sign a verdict. If an answer depends on data unavailable locally, label it unresolved and state how to verify it.
