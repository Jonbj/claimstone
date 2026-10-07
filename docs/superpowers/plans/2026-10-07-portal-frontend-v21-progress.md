# Portal frontend v2.1 — progress log

Spec: `docs/superpowers/specs/2026-10-07-portal-frontend-v21-spec.md`. Branch `research-portal`.

| step | title | status |
|---|---|---|
| F1 | Foundations: shell v2, control client, session, login | DONE |
| F2 | Today, Projects, Project | DONE |
| F3 | The flow journey | DONE |
| F4 | The reading desk | DONE |
| F5 | Decisions and Add material | TODO |
| F6 | Export, Administration, closing pass | IN PROGRESS |

## F1 — Foundations (DONE)

- [x] F1.1 Fonts and theme tokens. Pin `@fontsource/instrument-serif`; v2.1 tokens as CSS variables and Tailwind theme entries.
  Files: `web/package.json`, `web/package-lock.json`, `web/src/index.css`.
- [x] F1.2 Control client `lib/control.ts` with hand-written types for every control route, `ControlError`, in-memory CSRF; vite dev proxy for `/control`; client tests.
  Files: `web/src/lib/control.ts`, `web/vite.config.ts`, `web/tests/control.test.ts`.
- [x] F1.3 `SessionProvider` (context, `useSession`), 401 handling; session tests.
  Files: `web/src/lib/session.tsx`, `web/tests/session.test.tsx`.
- [x] F1.4 Login page `/login`, safe `?next=` redirect; routes wired in `App.tsx` (`/projects`, `/login`, provider).
  Files: `web/src/pages/LoginPage.tsx`, `web/src/lib/session.tsx` (safeNext), `web/src/App.tsx`, `web/tests/login.test.tsx`.
- [x] F1.5 Shell v2: dark left sidebar, collapse to top bar under 900 px, operator footer; Shell test.
  Files: `web/src/components/Shell.tsx`, `web/tests/shell.test.tsx`.
- [x] F1.6 Writes test: `writesnothing.test.ts` rewritten as `writes.test.ts`.
  Files: `web/tests/writesnothing.test.ts` (removed), `web/tests/writes.test.ts`. Done together with F1.2, because control.ts makes the old test fail.

### F1 result

Final checks (web/, then repo root):

```
gen:types unchanged            (git diff --exit-code web/src/lib/api-types.ts: clean)
typecheck: tsc --noEmit -p tsconfig.json   (no errors)
 Test Files  19 passed (19)
      Tests  105 passed (105)
✓ built in 4.06s
check-csp: ok (no inline script, no style attribute)
6 passed in 2.49s              (.venv/bin/pytest -q tests/test_api_contract.py)
```

Files: `web/package.json`, `web/package-lock.json`, `web/src/index.css`, `web/vite.config.ts`,
`web/src/lib/control.ts`, `web/src/lib/session.tsx`, `web/src/pages/LoginPage.tsx`,
`web/src/App.tsx`, `web/src/components/Shell.tsx`, `web/src/components/ErrorState.tsx`,
tests `control`, `session`, `login`, `shell`, `writes` (replaces `writesnothing`), and
`sources.test.ts` (edited).

Decisions where the spec was silent:
- `/` still renders the projects index and `/projects` renders the same page; Today replaces `/` in F2.
  The rail's Today link goes to `/`.
- The Projects link is lit for `/projects`, `/p/...` and `/inbox`.
- `tests/sources.test.ts` (F10) duplicated the old "writes nothing" rules and would fail under v2.1; it now
  allows a non-GET `method:` in `lib/control.ts` and a `<form>` with an `onSubmit`.
- `tests/writes.test.ts` is done in F1.2 with the control client, since the old test fails the moment
  `control.ts` exists; it also checks that `fetch` is called only from `api.ts` and `control.ts`, and that no
  `method:` outside `control.ts` is a non-literal.
- The file upload (`uploadIntakeFile`) uses `XMLHttpRequest`, for upload progress (F5); it sends
  `application/pdf`, `X-CSRF-Token` and no `Idempotency-Key`, and refuses over 50 MiB.
- `GET /session` answering 401 is "nobody signed in", not a sign-out event; a wrong password at login is
  likewise not. Any other 401 clears the token and signs the context out.
- `ErrorState` now renders a `ControlError`'s own code.
- The footer says `rev <12 chars>` without the old "read-only ·" prefix, which is no longer true once signed in.
- Dark rail is dark in both themes (`--rail*` tokens); the v2.1 meaning colours have dark-theme variants.
- A global `h1` rule uses Instrument Serif; existing pages still carry `font-semibold` until restyled.
- Pause/resume/paid-test are typed and exported, but F3/F6 decide how they are shown.

Deviations:
- `tests/test_committed_fixtures.py` does not exist in the repository, so the pytest check ran
  `tests/test_api_contract.py` alone.

NOT DONE (belongs to later steps): Today page, restyled Projects/Project pages, any write control, the
`exports` method in `api.ts`. Not testable in a browser here (no control server was started).

### F1 review — 2026-10-07 (reviewer)
Accepted. Checked: every non-GET request is in `control.ts`; the CSRF token is memory-only; `safeNext`
refuses `//`, `/\` and control characters; the upload sends no Idempotency-Key and refuses > 50 MiB.
The spec named a test file that does not exist (`tests/test_committed_fixtures.py`); corrected to
`tests/test_portal_fixtures.py` in the spec and in the F5 prompt. Note for F4/F5: `Idempotency-Key` is
fresh per call, so double submission is prevented in the UI by disabling a button while its request
runs. F5 is delegated to z.ai on branch `portal-frontend-f5` (worktree `claimstone-f5`); F2–F4 and F6
continue here.

## F2 — Today, Projects, Project (DONE)

- [x] F2.1 Today page at `/` (`GET /control/v1/today`): per project since/first visit, changed counts per stage with the undated count and newest rows, Needs you (required, then optional) with links, Continues without you, project `error`, Mark as seen (disabled while running; reloads Today). Signed out: explains the need for a session and links to Projects. `/` routes to Today; `/projects` stays the index.
  Files: `web/src/pages/TodayPage.tsx`, `web/src/App.tsx`, `web/tests/today.test.tsx`.
- [x] F2.2 Projects table (`/projects`): the design's table with a client-side name filter, one row per project, its flows and legacy selectors, state words from the API, lazy per-selector summaries kept.
  Files: `web/src/pages/IndexPage.tsx` (edited in place; no rename, so imports stay), `web/tests/projects.test.tsx`.
- [x] F2.3 Project header (`/p/:project`): serif title, registry line, research selector (flows, then legacy rounds labelled "protocol not verified"), integrity, activity; each block fails alone.
  Files: `web/src/pages/ProjectPage.tsx`, `web/tests/project.test.tsx`.

### F2 result

Final checks (web/, then repo root):

```
gen:types unchanged            (git diff --exit-code web/src/lib/api-types.ts: clean)
typecheck: tsc --noEmit -p tsconfig.json   (no errors)
 Test Files  22 passed (22)
      Tests  111 passed (111)
✓ built in 3.94s
check-csp: ok (no inline script, no style attribute)
7 passed in 3.89s              (.venv/bin/pytest -q tests/test_api_contract.py tests/test_portal_fixtures.py)
```

Files: `web/src/pages/TodayPage.tsx` (new), `web/src/pages/IndexPage.tsx`, `web/src/pages/ProjectPage.tsx`,
`web/src/App.tsx`, tests `today`, `projects`, `project`.

Decisions where the spec was silent:
- Today needs a session (the control API is authenticated); `TodayBody` fetches only when signed in.
- Links from Today: `identity` and every optional item go to `/p/:project/f/:flow/decisions` (the route is
  wired when F5 merges; until then it falls to the 404 page); `adjudication` goes to the reading desk
  `/p/:project/f/:flow/q/:subject` (the card's subject is the question id); `integrity` and `protocol`
  cards go to the project page.
- `continues_without_you` is typed `OperationSummary[] | null`; `null` is shown as "— not reported", an empty
  list as "No operation is authorized or running". The contract note says the field is a list since B12.
- Timestamps (`since`, `when`) are shown as the API's ISO strings; no date formatting or relative time.
- Mark as seen sends `{project}` only (the marker then covers that project), then reloads Today; the button is
  disabled while the request runs.
- The Projects table's search filters on name only, case-insensitively, and keeps the server's order.
- `IndexPage.tsx` keeps its name (edited in place) to keep imports and `r3review.test.tsx` stable.
- Project page: the research selector is a list of links (not ARIA tabs), because selecting a flow navigates.

Deviations: none from the spec.

NOT DONE (no API data, or later step): project descriptions and the design's project counts line (drafts,
running, finished), pinned projects in the rail, the Decisions badge count, the "your last visit was ..."
sentence (only the API's `since` string), the scheduler status in the rail, money figures, the journey step
bar and "N decisions waiting" on the project header, flow start dates and "needs you / running" in the
selector (only `binding_state` is returned). The Decisions route is not created here (F5, parallel branch).
Not checked in a browser (no servers were started).

### F2 review — 2026-10-07 (reviewer)
Accepted. Nothing computed in the browser beyond list lengths; `continues_without_you: null` and `[]` are
told apart. For F6's states pass: Today's "newest rows" render `JSON.stringify(row).slice(0,160)`; render
the known fields (stage, state, kind, ids) as labelled text instead.

## F3 — The flow journey (DONE)

- [x] F3.1 `OperationsPanel`: "Right now" list from `control.operations` (signed in only; signed out says "Sign in to see and authorize operations"). State word and note verbatim, limits, spent, unknown-cost units said as reserved, completed units, last event, `worker_note`; Pause/Resume disabled with a title. Named error on failure.
  Files: `web/src/components/OperationsPanel.tsx`, `web/tests/operations.test.tsx`.
- [x] F3.2 Authorize for `PLANNED` only: confirmation dialog listing the exact limits, POST them unchanged, disabled while running, the server's 409 sentence as given, reload after success.
  Files: `web/src/components/OperationsPanel.tsx`, `web/tests/operations.test.tsx`.
- [x] F3.3 `FlowOverviewPage` header restyle (serif title, scope and protocol chips, Add material / Decisions / Export / Activity) and the panel mounted for flows only; `/u/` gets no write control and no panel.
  Files: `web/src/pages/FlowOverviewPage.tsx`, `web/src/pages/ProjectPage.tsx` (`id="activity"` on the activity section, the Activity button's target).
- [x] F3.4 Page tests: header links, unbound selector has no panel or write control, signed out shows no write control.
  Files: `web/tests/flowpage.test.tsx`.

### F3 result

Final checks (web/, then repo root):

```
gen:types unchanged            (git diff --exit-code web/src/lib/api-types.ts: clean)
typecheck: tsc --noEmit -p tsconfig.json   (no errors)
 Test Files  24 passed (24)
      Tests  119 passed (119)
✓ built in 3.98s
check-csp: ok (no inline script, no style attribute)
7 passed in 3.88s              (.venv/bin/pytest -q tests/test_api_contract.py tests/test_portal_fixtures.py)
```

Files: `web/src/components/OperationsPanel.tsx` (new), `web/src/pages/FlowOverviewPage.tsx`,
`web/src/pages/ProjectPage.tsx` (one `id`), tests `operations`, `flowpage`.

Decisions where the spec was silent:
- F3.1 and F3.2 were written together in one component and committed together.
- The authorize confirmation is an inline `role="dialog"` block under the list, not a modal overlay.
- Title is `flow.title` when present, else the selector label; scope chip is the selector label, protocol is
  the first 12 characters of the flow id plus the binding state chip.
- Header links and the panel appear for `/f/` only. Signed out the links still show (they are navigation; the
  destination pages ask for a session) and the panel says "Sign in to see and authorize operations".
- A null limit is shown "— (none set)". Spent is labelled "Spent, as reported"; unknown-cost units say
  "reserved at their limit, not counted as 0" (the contract: a paid unit whose cost was not reported).
- Activity links to `/p/:project#activity`; the project page's activity section gained `id="activity"`.
  Browser hash scrolling after a client-side navigation is not tested.
- The operations list is fetched once and reloaded after a successful authorize; it does not poll.

Deviations: F3.1 and F3.2 share a commit.

NOT DONE (no API data, or later step): the 8-step journey bar, topic text and budget figures; a worker
heartbeat (the API gives `worker_note` only); Pause/Resume (disabled, ledger has no stopping event); the
Material, Decisions and Export routes (F5 branch, F6; the links 404 until merged). Not checked in a browser.

## F4 — The reading desk (DONE)

- [x] F4.1 `api.profiles` (GET only) and the diff panel's from/to choices from the stored-profile list (a select per side, the current profile marked); pasted hashes stay only when the list is empty or unavailable. The panel can be opened from outside with a from/to request (used by the stale banner).
  Files: `web/src/lib/api.ts`, `web/src/components/ProfileDiffPanel.tsx`, `web/tests/profilediff.test.tsx`.
- [x] F4.2 `QuestionPage` restyle and the gate that decides what the verdict section shows: operational (the API's `not_applicable_state`), provisional, no profile or `unavailable`, unbound `/u/`, signed out ("Sign in to sign"), or the signature panel. Stored profiles feed the diff panel.
  Files: `web/src/pages/QuestionPage.tsx`, `web/tests/readingdesk.test.tsx`.
- [x] F4.3 `SignaturePanel`: five radios (none checked, definitions from the verdict contract), reasoning with live trimmed count against 120, attestation, Sign as {name}; POST `{verdict, rationale, profile_sha256, attest: true}`; 409 code and sentence verbatim, `STALE_PROFILE` banner with reload and diff; the stored row shown after success.
  Files: `web/src/components/SignaturePanel.tsx`, `web/tests/signature.test.tsx`.
- [x] F4.4 Drafts: `GET …/draft` on load, "profile changed while you read" banner with signing blocked until the profile is reloaded, Save draft and save on blur when the text changed; the verdict is never stored.
  Files: `web/src/components/SignaturePanel.tsx`, `web/tests/signature.test.tsx`.
- [x] F4.5 Close: F4 result in this log.

### F4 result

Final checks (web/, then repo root):

```
gen:types unchanged            (git diff --exit-code web/src/lib/api-types.ts: clean)
typecheck: tsc --noEmit -p tsconfig.json   (no errors)
 Test Files  26 passed (26)
      Tests  143 passed (143)
✓ built in 3.99s
check-csp: ok (no inline script, no style attribute)
7 passed in 3.86s              (.venv/bin/pytest -q tests/test_api_contract.py tests/test_portal_fixtures.py)
```

Files: `web/src/components/SignaturePanel.tsx` (new), `web/src/pages/QuestionPage.tsx`,
`web/src/components/ProfileDiffPanel.tsx`, `web/src/lib/api.ts` (`profiles`, GET), tests `signature` (new,
14), `readingdesk` (new, 7), `profilediff` (+3).

Decisions where the spec was silent:
- The signature binds to a hash **pinned** when the panel appears. If the page later holds a different hash
  (the 3 s poll reloaded it), the panel says "The evidence changed", keeps the text, offers Compare (pinned to
  new, in the diff panel) and "Use the current profile", and blocks signing until that is taken; taking it
  clears the attestation. The profile card above still shows whatever the page holds, so the pinned hash is
  the one in the attestation line and the POST.
- `STALE_PROFILE`: the server's code and sentence are shown by `ErrorState`, the banner appears, the page is
  asked to reload, signing is blocked until the operator takes the new profile; Compare appears once the
  page knows a different hash.
- The draft banner ("The profile changed while you read") blocks signing until "Reload the profile", which
  re-reads the question and takes the current hash; a draft never restores a verdict or the attestation.
- Save draft is disabled for blank text; blur saves only if the text differs from the last saved/loaded text;
  a draft loaded from the server is not re-saved until edited; an in-flight save is not duplicated.
- Character count is in code points of the trimmed text, as Python counts it.
- Gate order on the page: operational (API's `not_applicable_state`), unbound `/u/`, provisional, no hash or
  `unavailable`, session pending, signed out ("Sign in to sign." with a login link), else the panel.
- After signing the form is replaced by the stored row (verdict, adjudicated_by, profile_sha256); the page
  reloads its question so the verdict section updates; no navigation.
- Panel is keyed by project, selector and question, and no storage is used, so no choice carries over.
- Sub-task order: F4.3 was committed before F4.2 (the page needs the panel).

Deviations: none from the spec's requirements. The "Opened N of M" reading aid is omitted.

NOT DONE (no API data, or later step): "Opened N of M" aid; the design's "server: final, admissible, stored
profile equals current (checked N s ago)" line (no such API field); the design's claim-by-claim reading column
and excluded-interpretations list (existing results table kept as is); the Decisions/Material routes (F5).
A failed poll reload replaces the page by the error state and drops unsaved text (existing page behaviour;
the draft is the safeguard). Not checked in a browser (no servers were started).

## F6 — Export, Administration, closing pass (IN PROGRESS)

- [x] F6.1 Export page `/p/:project/f/:sel/export` (flows only): `api.exports` (GET), list, Create snapshot with the copies checkbox and the `copies` answer, per-row Verify (never on load; disabled while running), route in `App.tsx`.
  Files: `web/src/lib/api.ts`, `web/src/pages/ExportPage.tsx`, `web/src/App.tsx`, `web/tests/export.test.tsx`.
- [x] F6.2 Administration `/admin`: read API presence block, control admin when signed in (last check per target, Check buttons, credential form cleared after every submit, never echoed), Paid test disabled with the 501 reason.
  Files: `web/src/pages/AdminPage.tsx`, `web/tests/admin.test.tsx`.
- [ ] F6.3 Reviewer fix A: the reading desk keeps its last good data and the panel state through a failed poll refresh, with a named stale banner; no storage.
  Files: `web/src/pages/QuestionPage.tsx`, `web/tests/readingdesk.test.tsx`.
- [ ] F6.4 Reviewer fix B: Today's newest rows as labelled fields, not JSON.
  Files: `web/src/pages/TodayPage.tsx`, `web/tests/today.test.tsx`.
- [ ] F6.5 States pass: one failed or empty state test per page (Today, Projects, Project, Flow, Question, Claim, Source, Export, Admin, Login) where none exists, and the fixes they expose.
  Files: `web/tests/states.test.tsx` and the pages it exposes.
- [ ] F6.6 Docs: `docs/HANDOFF.md` portal paragraph, a new `D` decision, F6 result in this log.
  Files: `docs/HANDOFF.md`, `docs/DESIGN_DECISIONS.md`, this log.
