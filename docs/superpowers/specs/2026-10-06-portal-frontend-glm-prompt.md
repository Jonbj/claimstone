You are implementing **one step** of a multi-step feature in the Claimstone repository.

**STOP RULE: do exactly one step, the first one not marked DONE in the progress log. Then write the
report and end the session. Do not start the next step, even if you have budget left.** Do not ask
me questions. When something is unspecified, make the smallest decision that keeps every existing
test passing and the seven invariants in `CLAUDE.md` intact, record it in the log, and continue.

Your budget may run out at any moment, without warning. The working method below is designed so
that an interruption loses at most one small sub-task. Follow it exactly.

## The work

The specification is `docs/superpowers/specs/2026-10-06-portal-frontend-docker-design.md`. It is the
authority. Read the sections your step names, plus §1.3 and §4.2, which always apply. The framework
decision is made, and it was **revised**: **React + shadcn/ui + Tremor Raw, built with Vite**
(spec §8, which overrides §4.1, §4.3 and §4.4 wherever they differ). S4 and S5 were built with
SvelteKit and are superseded by R2–R4. The visual reference is
`docs/design/portal/flow-overview-react-tremor.html`.

## Start of every session (in this order)

1. Check you are on the right branch: `git branch --show-current` must print `research-portal`. If
   it does not, run `git switch research-portal`. Never work on `main`.
2. Read `CLAUDE.md`, then the progress log
   `docs/superpowers/plans/2026-10-06-portal-frontend-progress.md`. If the log does not exist,
   create it: run the checks below and record their output as the baseline. Then commit it alone
   (`docs: start portal frontend progress log`).
3. Run `git status --short`. **Uncommitted changes mean a previous session was interrupted
   mid-sub-task.** Find the step marked `IN PROGRESS` in the log and its first unticked sub-task.
   Inspect the uncommitted files, then either finish that sub-task or, if the partial work is
   unusable, discard **only those files** with `git restore`/`git clean` on the named paths. Never
   reset anything else.
4. Pick the step: the one marked `IN PROGRESS`, or else the first step in the table that is not
   DONE.

## Working method inside a step

1. **Before writing any code**, append the step's section to the log. Mark it `IN PROGRESS` and add
   a checklist of 3–6 small sub-tasks (`- [ ] S3.1 …`). Each sub-task must be completable and
   checkable on its own. Commit the log: `docs: plan S<n>`.
2. For each sub-task:
   - implement it;
   - run the checks;
   - tick it (`- [x]`) in the log;
   - commit the code and the log together: `wip(S<n>.<k>): <what>`.

   Commit only when the checks pass. If they fail, fix before moving on.
3. When every sub-task is ticked and the step's "done when" holds:
   - change the step's marker to `DONE`;
   - record the final check lines, decisions and deviations;
   - commit: `feat(portal-frontend): S<n> <title>`, or `docs(…)` for S7.
4. Write the report (below) and **end the session**.

Each commit message ends with the line `Co-Authored-By: GLM via opencode`. Commit with
`git commit` on `research-portal` only. Never push, rebase, amend, reset or switch to another
branch.

## Steps

| step | content (spec section) | done when |
|---|---|---|
| **S1** | Factor the shared transport out of `claimstone/portal.py` into a base class, used by `portal.py` unchanged in behaviour. The base covers GET-only, Host/Origin with `--allow-host`, headers and lookup-never-path. | the existing portal tests pass **unchanged**; checks pass |
| **S2** | `claimstone/api.py`: every `/api/v1` route (§3.2), the error envelope (§3.3) and `API_VERSION = 1`. The `claimstone api` CLI command. Tests A1–A7 (§3.5) in `tests/test_api.py`. Do **not** register `API_VERSION` in `tools/check_instrument_versions.py` (that happens in S7). | checks pass; `claimstone api` answers every route on a tmp workspace |
| **S3** | `claimstone/api_schema.py`, `tools/build_portal_api_schema.py` and the committed `docs/contracts/portal-api.schema.json`. The minimal stdlib validator and test A2 (§3.4). `tools/build_portal_fixtures.py` and the committed `web/tests/fixtures/*.json`, plus currency tests. | checks pass |
| **S4** | Scaffold `web/` (§4.1): exact pinned versions, committed `package-lock.json`, configs, `gen:types` and the generated `api-types.ts`, `api.ts`, `vocabulary.ts`, base components (`Chip`, `Fraction`, `Pending`, `ErrorState`, `CommandBlock`), layout, and vitest F1, F4, F5, F6 and F8 (§4.4). | web checks pass; checks pass |
| **S5** | Every route and remaining component of §4.1, following every rule in §4.2. That includes the lazy index with per-selector summaries and 3 s polling. Vitest F2, F3 and F7. | web checks pass; checks pass |
| **R1** | Server fields for the React design (§8.3): `question_state_counts` and `source_tracker` on the overview, computed in `claimstone/portal_state.py` with the matrix's own rules (one `compute()`, no extra pass over the ledgers). Update `api_schema.py`, regenerate the schema and fixtures, and add Python tests: counts sum to the registry size; tracker order equals the scoped candidate order; a 403 entry's tooltip is the F19 text; unbound and flow selectors both carry the fields. | checks pass |
| **R2** | Replace the SvelteKit scaffold with React (§8.2): delete the Svelte sources and config, scaffold Vite + React + TS strict + react-router + Tailwind v4, run the shadcn CLI for the listed components, copy the Tremor Raw components with their README/licence, add the bundled Geist fonts, port `api.ts` / `api-types.ts` / `vocabulary.ts` unchanged, add `useApi` / `usePoll`, the shell (top bar, tabs, rev, theme), the base components (Chip, Fraction, Pending, ErrorState, CommandBlock), the new `check-csp.mjs` (§8.4), the CSP header in `preview.headers`, and port tests F1, F4, F5, F6 and F8 plus F10. | web checks pass (`npm ci && npm run typecheck && npm test && npm run build`); checks pass |
| **R3** | Pages, part 1: index (lazy per-selector summaries, skeletons), project page (integrity, flows, unbound selectors, activity), inbox (server order, category filter only), admin. | web checks pass; checks pass |
| **R4** | Pages, part 2, following §8.3 and every rule of §4.2: flow overview (KPI cards, `CategoryBar` floor, `DonutChart` from `question_state_counts`, `Tracker` from `source_tracker`, questions table, `BarList`, floor per class, inbox, activity, 3 s polling), question, claim lineage, source dossier. Port F2, F3 and F7; add F9 and F11. Then run `npm run build && npx vite preview`, open each page against `claimstone api` on a **tmp** workspace, and record "0 CSP violations" (or the violations, and fix them) in the log. | web checks pass; checks pass; zero CSP violations recorded |
| **S6** | `web/Dockerfile` (build output is `web/dist/`) and `web/nginx.conf` (§4.3, with the CSP **header** of §8.4); the `api` and `web` services and the `portal` network in `compose.yaml` (§5), keeping every existing comment and service; `Dockerfile` args and env; `portal.sh`; `.dockerignore`. Pin base images by digest. | every acceptance command of §7 step 4, with output recorded in the log; `./portal.sh down` afterwards |
| **S7** | Parity check (§7 step 5) between `claimstone portal` and the SPA, on a tmp store built from test fixtures. D84 (§6) in `docs/DESIGN_DECISIONS.md`; register `("claimstone/api.py", "API_VERSION", "portal_api_version")`; update `docs/README.md`, `AGENTS.md` (Node only builds the frontend) and a dated `HANDOFF.md` paragraph. | checks pass; `check_instrument_versions.py` counts one more instrument |

## Checks

Always run:

```bash
.venv/bin/pytest -q
.venv/bin/claimstone validate --all-projects
.venv/bin/python tools/check_instrument_versions.py
```

**Web checks**, from R2 on: `cd web && npm ci && npm run typecheck && npm test && npm run build`.
After the first `npm ci`, plain `npm run typecheck && npm test && npm run build` is enough unless
dependencies changed. (S4–S5 used `npm run check`, the SvelteKit equivalent.)

## Hard constraints. These override any instinct to be helpful.

- Never write to, repair or delete anything under `store/`, and never modify `projects/`. Tests use
  `tmp_path`. Any server you start for a check uses a tmp store built from
  `tests.test_portal_state.build_workspace`.
  - The one exception is in S6: the compose `portal` profile may run against the real `store/`, but
    only after you verify in `compose.yaml` that `store` and `projects` are mounted `:ro`. Run
    `./portal.sh down` afterwards.
- **Network:** only the npm registry and Docker Hub. No scholarly API, no publisher, no model
  backend. Never run `acquire`, `discover`, `normalize`, `extract`, `review`, `synthesize`,
  `adjudicate`, `model-run` or `./claimstone.sh`.
- **No new Python dependency.** The API stays stdlib. Node and npm exist only under `web/` and in the
  frontend image.
- **The frontend writes nothing.** No form, no non-GET `fetch`, no verdict input. API display texts
  are rendered verbatim (§4.2).
- Never weaken, skip, delete or rewrite an existing test to make it pass. If an existing test fails
  because of your change, the change is wrong.
- Never commit `node_modules/`, `web/build/`, `.env`, or anything under `store/` or `projects/`.
  Check `git status` before each commit.
- Never invent figures. Every number in docs or in the log is copied from output you ran.
- If the same failure survives three distinct fix attempts, re-read the spec section and choose the
  simplest design that satisfies its purpose, then record the deviation. If something is truly
  impossible, record it as **NOT DONE** in the step, with the reason. Mark the step `DONE (with NOT
  DONE items)` only if the rest holds; otherwise leave it `IN PROGRESS` and say what blocks it.

## Log format, per step

```
### S<n> — IN PROGRESS | DONE
- [x] S<n>.1 …
- [ ] S<n>.2 …
Checks: <exact final lines of each command, at DONE>
Decisions (spec silent): …
Deviations: …
NOT DONE: …
```

## Report, then end the session

Reply with:
- the step you worked on and its final marker;
- the sub-tasks completed this session;
- the final check lines;
- the commits made (`git log --oneline` since the session started);
- the decisions and deviations;
- the next step.

Keep it under half a page. Then stop: do not begin the next step.
