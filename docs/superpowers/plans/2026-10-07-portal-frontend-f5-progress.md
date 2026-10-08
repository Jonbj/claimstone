# Portal frontend v2.1 — F5 progress log (parallel worktree)

Spec: `docs/superpowers/specs/2026-10-07-portal-frontend-v21-spec.md` §1, §3 and **F5**.
Prompt: `docs/superpowers/specs/2026-10-07-portal-frontend-f5-zai-prompt.md`. Branch
`portal-frontend-f5` (worktree `claimstone-f5`); the reviewer merges. Step F5 only.

| step | title | status |
|---|---|---|
| F5 | Decisions and Add material | DONE (closed by the reviewer) |

- [x] F5.1 Decisions page: open cards in server order (identity, offer, retry campaign), decided recently.
- [x] F5.2 Decisions forms: record a verified offer; plan a retry campaign (Preview verbatim, then Approve).
- [x] F5.3 Add material page: propose (kind, value, note), upload a file (50 MiB client refusal, progress), intake list.
- [x] F5.4 Tests `web/tests/decisions*.test.tsx`, `web/tests/material*.test.tsx`.
- [x] F5.5 Checks: `npm ci && npm run gen:types && npm run typecheck && npm test && npm run build`, then
      `PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m pytest -q
      tests/test_api_contract.py tests/test_portal_fixtures.py`.

## To wire at merge

`web/src/App.tsx`, inside the Shell's children:

```tsx
{ path: "p/:project/f/:sel/decisions", element: <DecisionsPage /> },
{ path: "p/:project/f/:sel/material", element: <MaterialPage /> },
```

with `import DecisionsPage from "@/pages/DecisionsPage";` and
`import MaterialPage from "@/pages/MaterialPage";`.

### F5 closure — 2026-10-08 (reviewer)
The z.ai session stopped after `df8e923` (no activity for ~3 hours) with one uncommitted change: an
unused `waitFor` import removed from `web/tests/material.test.tsx`. The reviewer committed it and
closed the step. Verified: every decision and intake route is used by the pages (`resolveIntake`,
`stageOffer`, `setDecisionState`, `recordOffer`, `retryPreview`, `approveRetry`, `submitIntake`,
`uploadIntakeFile`); `tests/decisions.test.tsx` (5) and `tests/material.test.tsx` (4) pass. Routes wired
at merge on `research-portal`.
