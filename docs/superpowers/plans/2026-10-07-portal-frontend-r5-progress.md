# Portal frontend R5 (profile-diff panel) — progress log

Working document for `docs/superpowers/specs/2026-10-07-portal-frontend-r5-prompt.md`
(step R5 of the portal frontend, on the `portal-frontend-r5` worktree branch; the
backend route B6 is already merged). One session does exactly one step.

## Step table

| step | content | done when | marker |
|---|---|---|---|
| **R5** | profile-diff panel on the question page: `api.profileDiff`, `ProfileDiffPanel`, wired into `QuestionPage`, tests | R5.1–R5.4 done; all checks green | DONE |

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

## Checklist

- [x] R5.1 `api.profileDiff(project, kind, sel, qid, fromSha, toSha)` in
      `web/src/lib/api.ts`, following the existing function shapes exactly
      (files: `web/src/lib/api.ts`)
- [x] R5.2 `web/src/components/ProfileDiffPanel.tsx`: two hash inputs (`from`
      prefilled with the question's current `profile_sha256` when the page holds
      one), a compare action, the rendering — `summary` as three labelled counts,
      diff-level `reason` verbatim, each entry with `result_id`, claim text,
      `evidence_quote` verbatim, stance label from `vocabulary`, source class,
      link to the entry's lineage page; a removed entry's `reason` verbatim; a
      changed entry's per-field `from` → `to` verbatim; `counts.from`/`counts.to`
      labelled a count, not a strength; **no verdict word anywhere**; errors
      through `ErrorState`, the 400/404 envelope message verbatim, code named
      (files: `web/src/components/ProfileDiffPanel.tsx`)
- [x] R5.3 wire the panel into `pages/QuestionPage.tsx` as a collapsed section;
      the page's existing behaviour unchanged
      (files: `web/src/pages/QuestionPage.tsx`)
- [x] R5.4 tests in the style of the existing `web/tests/*.test.tsx`: the panel
      with inline payloads covering added+removed+changed+diff-reason, the empty
      diff (the committed fixture), the 404/400 refusals; plus a `useApi`/`api.ts`
      test for the new function
      (files: `web/tests/profilediff.test.tsx` (new), `web/tests/apiprofilediff.test.tsx` (new))
- [x] all checks green: Python gates (`pytest -q`, `validate --all-projects`,
      `check_instrument_versions.py`) and web (`npm ci && npm run typecheck &&
      npm test && npm run build`, the build including `scripts/check-csp.mjs`)

### R5 — DONE

- [x] R5.1 `api.profileDiff` (files: `web/src/lib/api.ts` — `ProfileDiff` import,
      one function after `question`, same `selectorPath`/`encodeURIComponent`
      shapes, both hashes encoded in the query string)
- [x] R5.2 `ProfileDiffPanel` (files: `web/src/components/ProfileDiffPanel.tsx`)
- [x] R5.3 question page wiring (files: `web/src/pages/QuestionPage.tsx` — import
      plus one `<ProfileDiffPanel …>` between the results and verdict sections)
- [x] R5.4 tests (files: `web/tests/profilediff.test.tsx` (9 tests),
      `web/tests/apiprofilediff.test.tsx` (8 tests))

Checks (exact final lines, run in the worktree at the final code state):

```
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m pytest -q
1176 passed, 13 skipped in 47.08s
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m claimstone.cli validate --all-projects
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python tools/check_instrument_versions.py
29 instrument version(s) acknowledged in the design record
$ cd web && npm ci && npm run typecheck && npm test && npm run build
Test Files  15 passed (15)
      Tests  72 passed (72)
✓ built in 4.87s
check-csp: ok (no inline script, no style attribute)
```

`npm ci` had already run at baseline this session; its last output line was
`added 222 packages in 2s` (node_modules present throughout, no dependency
changed — `package.json` and `package-lock.json` untouched by this step, as the
scope requires).

Decisions (spec silent):
- **The panel is a collapsed `<details>` section** (spec R5.3 allows "a collapsed
  section is fine"), so nothing fetches on page load and the page's existing
  behaviour is byte-identical until the operator opens it.
- **A comparison is fetched only on the compare action** — the button is
  disabled until both fields are non-empty. `from==to` is a valid comparison
  (B6's own first test), so both fields non-empty is the only client-side gate;
  an unknown hash is the server's 404 to report, never pre-judged here.
- **The `from` prefill comes from `profile_fields.profile_sha256`** (the hash
  the question page already shows), passed as a prop; `null` (no stored
  profile) leaves the input empty. If the page's hash changes after mount the
  prefill does not chase it — the operator is pasting the hashes they mean to
  compare, and a silently re-written input would be the input editing itself.
- **Stances render as plain text, not `Chip`.** A chip is the verdict
  vocabulary's carrier; the diff carries no verdict and renders none
  (invariant 2). `SUPPORTS`/`CONTRADICTS`/`QUALIFIES` are stances; they print
  as data. "No verdict word anywhere" is test-enforced (`profilediff.test.tsx`).
- **The counts' note is the panel's own static label** — "counts — a count, not
  a strength" as the section heading, then `by_class` per relation
  (`for: ACA 1 · against: —`) and `direction_count` (`SUPPORTS 1`) for each
  side, the same wording `direction_count_note` carries on the question page.
  The diff payload carries no note field, so the panel renders the label itself.
- **`changed` entries render `fields` as `field: JSON(from) → JSON(to)`** rows
  (JSON so a non-string value — a number, a list — stays verbatim and visibly
  typed), plus the lineage link via `result_id`. Added/removed entries render
  the whole `result` row's named keys (`claim`, `evidence_quote` in a
  `<blockquote>` matching `Lineage`'s quote styling, `stance`, `source_class`),
  and a removed entry's `reason` verbatim under it.
- **Entry lineage links use the existing claim route** `${base}/claim/${result_id}`
  (`result_id` is the claim id, B6's decision), shortened to 16 chars like the
  results table.
- **`useApi` drives the fetch with the comparison pair in `deps`**, so asking
  for another pair is a new view (no stale diff of another pair on screen —
  `useapi`'s rule), and the fetcher returns `Promise.resolve(null)` before any
  comparison is asked for, so nothing fetches until compare.
- **Tests: `fireEvent`, not `@testing-library/user-event`** — the package is not
  a dependency of this project and installing one is outside R5's scope. The
  panel tests assert on `container.textContent` where the payload's words are
  split across DOM elements (the summary counts are three spans).

Deviations:
- The prompt says "the stance label from `vocabulary`"; `vocabulary.ts` maps
  verdict words and engine states, and has no stance vocabulary — stances are
  not verdicts (invariant 2 is exactly the line between them). The panel
  renders stances as plain text and names the decision above. Recorded rather
  than "fixed", because mapping stances through the verdict vocabulary's
  `word()` would render `SUPPORTS` as an unknown-word chip and edge toward
  verdict-looking chrome for a non-verdict field.

Follow-up for the reviewer (from the prompt, not implemented here):
- **The read API has no route listing a question's stored profile hashes**, so
  the panel cannot offer a picker of real hashes: the operator pastes them (the
  `from` prefill is the one hash the page already shows). Adding a hash-list
  route is backend work outside this step.

NOT DONE: (none — R5 complete)