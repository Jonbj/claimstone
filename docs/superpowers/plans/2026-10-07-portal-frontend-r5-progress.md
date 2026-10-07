# Portal frontend R5 (profile-diff panel) — progress log

Working document for `docs/superpowers/specs/2026-10-07-portal-frontend-r5-prompt.md`
(step R5 of the portal frontend, on the `portal-frontend-r5` worktree branch; the
backend route B6 is already merged). One session does exactly one step.

## Step table

| step | content | done when | marker |
|---|---|---|---|
| **R5** | profile-diff panel on the question page: `api.profileDiff`, `ProfileDiffPanel`, wired into `QuestionPage`, tests | R5.1–R5.4 done; all checks green | IN PROGRESS |

## Checklist

- [ ] R5.1 `api.profileDiff(project, kind, sel, qid, fromSha, toSha)` in
      `web/src/lib/api.ts`, following the existing function shapes exactly
      (files: `web/src/lib/api.ts`)
- [ ] R5.2 `web/src/components/ProfileDiffPanel.tsx`: two hash inputs (`from`
      prefilled with the question's current `profile_sha256` when the page holds
      one), a compare action, the rendering — `summary` as three labelled counts,
      diff-level `reason` verbatim, each entry with `result_id`, claim text,
      `evidence_quote` verbatim, stance label from `vocabulary`, source class,
      link to the entry's lineage page; a removed entry's `reason` verbatim; a
      changed entry's per-field `from` → `to` verbatim; `counts.from`/`counts.to`
      labelled a count, not a strength; **no verdict word anywhere**; errors
      through `ErrorState`, the 400/404 envelope message verbatim, code named
      (files: `web/src/components/ProfileDiffPanel.tsx`)
- [ ] R5.3 wire the panel into `pages/QuestionPage.tsx` as a collapsed section;
      the page's existing behaviour unchanged
      (files: `web/src/pages/QuestionPage.tsx`)
- [ ] R5.4 tests in the style of the existing `web/tests/*.test.tsx`: the panel
      with inline payloads covering added+removed+changed+diff-reason, the empty
      diff (the committed fixture), the 404/400 refusals; plus a `useApi`/`api.ts`
      test for the new function
      (files: `web/tests/profilediff.test.tsx` (new), `web/tests/apiprofilediff.test.tsx` (new))
- [ ] all checks green: Python gates (`pytest -q`, `validate --all-projects`,
      `check_instrument_versions.py`) and web (`npm ci && npm run typecheck &&
      npm test && npm run build`, the build including `scripts/check-csp.mjs`)

Scope: only `web/src/**` and `web/tests/**` (plus this log). No
`claimstone/**`, no `docs/contracts/**`, no `web/tests/fixtures/**`, no
`web/src/lib/api-types.ts`, no other progress log, no `package.json`.

## Baseline (recorded 2026-10-07, before R5 work, at `861d3e9`)

```
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m pytest -q
1176 passed, 13 skipped in 49.03s
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m claimstone.cli validate --all-projects
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python tools/check_instrument_versions.py
29 instrument version(s) acknowledged in the design record
$ cd web && npm ci && npm run typecheck && npm test && npm run build
Test Files  13 passed (13)
      Tests  55 passed (55)
✓ built in 4.88s
check-csp: ok (no inline script, no style attribute)
```

`git status --short` clean before the first commit.

## Log format, per step

```
### R5 — IN PROGRESS | DONE | BLOCKED
- [x] R5.1 … (files: …)
Checks: <exact final lines of each command, at DONE>
Decisions (spec silent): …
Deviations: …
NOT DONE: …
```

### R5 — IN PROGRESS

Decisions (spec silent, made so far):
- The panel is a **collapsed `<details>`** section on the question page, so the
  page's existing behaviour is unchanged and nothing fetches until the operator
  opens it and asks for a comparison.
- The compare action is a `<button>`, not a `<form>` (F3/F10 scan `src/` for
  `<form`), and the hash inputs are plain `<input type="text">` with
  `monospace` styling, matching the panel's audit character.
- `from==to` is a valid comparison (B6): the compare button is enabled with both
  fields non-empty; no client-side hash validation beyond non-emptiness — an
  unknown hash is the server's 404 to report, never ours to pre-judge.
- The counts' "a count, not a strength" wording: the diff payload carries no
  note field, so the panel renders the label itself as static text beside both
  ends' counts — the same wording `direction_count_note` carries on the question
  page ("a count, not a strength").
- Entries render `result` fields verbatim as key/value rows (claim,
  `evidence_quote`, stance, source class travel inside `result`/`changed.from`'s
  result rows); `changed` renders `fields` as `field: from → to` rows. The
  lineage link uses the existing claim route `${base}/claim/${result_id}`.
- No verdict word anywhere: the panel renders only what the payload carries;
  stance values (SUPPORTS/CONTRADICTS/QUALIFIES) are stances, not verdicts, and
  render as plain text without `Chip` (a chip is the verdict vocabulary's
  carrier; the diff carries none).

Deviations: none yet.

NOT DONE: (the sub-tasks above)