You are implementing **step F5** of the Claimstone portal frontend v2.1, in a **parallel** session. Another
agent builds F2–F4 on `research-portal` at the same time; the reviewer merges your branch.

**STOP RULE: do exactly step F5. When it is DONE, write the report and end the session.** Do not ask
questions. When something is unspecified, make the smallest decision that keeps every existing test
passing and the invariants in `CLAUDE.md` intact, and record it in the log.

## Where you work

- **Directory:** `/home/stefano/Documents/Projects/claimstone-f5`, a git worktree.
- **Branch:** `portal-frontend-f5`. `git branch --show-current` must print it; if not, stop and report.
  Never switch branch, merge, rebase, push, amend, reset or stash.
- **Never touch** `/home/stefano/Documents/Projects/claimstone`, the main checkout.
- **Log:** `docs/superpowers/plans/2026-10-07-portal-frontend-f5-progress.md`, in the worktree. Create it
  at the start with a table holding F5 `TODO`, then commit it alone.

## Read first

1. `CLAUDE.md`.
2. `docs/superpowers/specs/2026-10-07-portal-frontend-v21-spec.md`: §1, which always applies, §3, and
   **F5**. The section "Method and commits" in §3 applies with the log path above.
3. `docs/contracts/control_api.md` (the B7a, B7b and B8 "As built" notes), `docs/contracts/decisions.md`
   and `docs/contracts/intake.md`. Read `claimstone/control.py`, `claimstone/decisions.py` and
   `claimstone/intake.py` for exact field names.
4. What F1 built and you must reuse, never duplicate:
   - `web/src/lib/control.ts`, the only module allowed to send a non-GET request: add a function there
     only if F1 did not type a route you need;
   - the session context;
   - the Shell and the theme tokens.
5. The boards `docs/design/portal/v2/V2Decisions.html` and `V2AddMaterial.html`, for layout and copy only.

## Scope: your files only

- **Create** `web/src/pages/DecisionsPage.tsx`, `web/src/pages/MaterialPage.tsx`, any components under
  `web/src/components/decisions/` and `web/src/components/material/`, and tests
  `web/tests/decisions*.test.tsx` and `web/tests/material*.test.tsx`.
- **Do not edit** `web/src/App.tsx`. Export each page as the default export, and write the route lines
  you would add in the log under "to wire at merge". The planned routes are
  `p/:project/f/:sel/decisions` and `p/:project/f/:sel/material`.
- **Do not edit** the Shell, `api.ts`, `api-types.ts`, the existing pages or any Python. You may edit
  `control.ts` only to add a missing typed function; if you do, list it in the log.

## Tests that must exist

- Decisions renders the open cards in the server's order, without re-sorting them.
- An identity answer other than `not_sure` with a short reason shows the hint, and the server's 422 is
  shown as given.
- The offer stage buttons shown are only those valid for the state, and "copy verified" is never a
  button.
- The retry preview shows the refused hosts verbatim.
- Material refuses a file over 50 MiB before sending, and a `POSSIBLE_VERSION` item links to Decisions.
- Signed out, both pages show "Sign in to …" and no write control.

## Checks (no virtualenv in this worktree; use these exact commands)

```bash
cd web && npm ci && npm run gen:types && npm run typecheck && npm test && npm run build
cd .. && PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m pytest -q tests/test_api_contract.py tests/test_portal_fixtures.py
```

`npm ci` is the only network access allowed, to the npm registry. Every commit message ends with
`Co-Authored-By: glm-5.3 via z.ai`.

## Report

Reply with:
- the step and its marker;
- the commits;
- the final check lines;
- the route lines to wire at merge;
- the decisions and deviations;
- what is NOT DONE.

Keep it under half a page. Then stop.
