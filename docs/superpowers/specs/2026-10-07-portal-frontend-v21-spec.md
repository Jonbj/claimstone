# Portal frontend v2.1 — implementation specification

**Date:** 2026-10-07. **Branch:** `research-portal`. **Built in steps F1–F6** by a delegated agent, each
step reviewed before the next.

**Design:** `docs/design/portal/v2/README.md` and the boards `docs/design/portal/v2/*.html`. The boards
are canvas sources (inline styles, a `support.js` runtime): read them for layout, copy and tokens, and
never copy them as code. Their figures are illustrative. Do not put any of them in the app.

**APIs:**
- **Read API** (`/api/v1`, GET only): the typed client `web/src/lib/api.ts` and the generated types
  `web/src/lib/api-types.ts`. Contract: `docs/contracts/portal-api.schema.json`.
- **Control API** (`/control/v1`, authenticated, GET and POST): the contract is
  `docs/contracts/control_api.md`, with an "As built" note per step, and the implementation is
  `claimstone/control.py`. There is no JSON schema for it: write its TypeScript types by hand from
  those two files, and **read the Python to get field names right**.

`CLAUDE.md` overrides everything here.

## 1. Rules that hold on every page

1. **Render only what an API returned.** A design element whose data no API provides is left out,
   or shown as "not available yet", and listed in the step log under NOT DONE. The 8-step journey
   timeline, the topic description, money figures for a project, and "worker last seen" are such
   elements. Never compute a scientific state, a count or a sentence in the browser.
2. **Unknown is not zero.** While loading: `Pending`. For a null value: "—" with the reason when the API
   gives one. Show a 0 only when the API returned 0.
3. **Errors are named.** An `ApiError` or `ControlError` renders the server's code and message with
   `ErrorState`. A failed block never blanks the whole page.
4. **No verdict is preselected, suggested or defaulted.** The five verdicts are offered as radios with
   none checked. `NO_VERIFIED_CLAIM` is never offered.
5. **Writes go through one module.** `web/src/lib/control.ts` is the only file allowed to use a non-GET
   `fetch`. Every POST it sends carries:
   - `credentials: "same-origin"`;
   - `X-CSRF-Token` from the session;
   - `Content-Type: application/json`, except the file upload, which sends `application/pdf`;
   - an `Idempotency-Key` it generates (`crypto.randomUUID()`) for every POST except the login, the
     logout and the file upload.
6. **Forms never submit natively.** The CSP has `form-action 'none'`. Every `<form>` has an `onSubmit`
   that calls `preventDefault()`.
7. **The CSP stays as it is.** No inline script, no `style=` attribute in the built HTML, no CDN.
   `npm run build` runs `check-csp`.
8. **Colour meanings** (design §3, v2.1):
   - violet `#7c3aed` = waits for you;
   - teal `#0d9488` / `#ccfbf1` / `#115e59` = Claimstone acting;
   - blue = contradicts;
   - emerald = done or supports;
   - amber = still being read or provisional;
   - rose = not obtained or below floor;
   - slate = neutral or qualifies.

   Every chip carries its word: colour never carries meaning alone.
9. **Type.** Instrument Serif for page titles and question statements, Geist for the UI, Geist Mono
   for identifiers and counts. Fonts are bundled through `@fontsource`, with exact versions pinned in
   `package.json`.
10. **Accessibility.** Use real buttons, links and labels, with 44 px targets for primary actions, and
    make everything reachable by keyboard.
11. **Read-only fallback.** With no session, every read page still works. Write controls show "Sign in
    to …" linking to `/login`.

## 2. Steps

Each step ends with all of these passing:

```bash
cd web && npm run gen:types && npm run typecheck && npm test && npm run build
.venv/bin/pytest -q tests/test_api_contract.py tests/test_committed_fixtures.py   # from the repo root
```

`gen:types` must produce no diff unless the step changed the schema. **No step changes Python code.** If a
step seems to need a backend change, record it under NOT DONE and do not make it.

### F1 — Foundations

- **Fonts and theme.** Pin `@fontsource/instrument-serif`. Add the v2.1 tokens to `src/index.css` as
  CSS variables and Tailwind theme entries.
- **Shell v2** (`components/Shell.tsx`), replacing the top tabs with the design's dark left sidebar
  (`#0f172a`, 232 px; under 900 px wide it collapses to a top bar):
  - **New project**: disabled, with the note "creating projects from the web is not built yet";
  - **Today** (`/`) and **Projects** (`/projects`);
  - **Administration** (`/admin`);
  - a footer with the signed-in operator's name and **Sign out**, or **Sign in**;
  - the code revision, as now.

  The current Inbox tab disappears from the sidebar. Keep `/inbox` routable.
- **Control client** `src/lib/control.ts`:
  - typed functions for every control route that exists;
  - errors parsed into `ControlError(status, code, message)`;
  - a response that is not the envelope becomes a plain `Error`, as in `api.ts`;
  - the CSRF token is held in memory only, never in `localStorage`.
- **Session.** A `SessionProvider` (React context): `GET /control/v1/session` at start, `signIn`,
  `signOut`, and `operator` (`{id, name}`) or `null`. A control route answering 401 at any time sets the
  session to signed out.
- **Login page** `/login`: id and password, the server's message on failure, and the `RATE_LIMITED`
  message as given. After signing in, return to the `?next=` path, accepting only a path starting with
  a single `/`.
- **Writes test.** Rewrite `tests/writesnothing.test.ts` into `tests/writes.test.ts`:
  - a non-GET `method:` appears only in `src/lib/control.ts`;
  - every `<form` has an `onSubmit`;
  - `src/lib/api.ts` still has no non-GET method.
- `vite.config.ts`: the dev proxy gains `"/control": "http://127.0.0.1:8790"`, with a comment that in dev
  the control server must run with `--allow-host localhost:5173`.
- **Tests:**
  - the control client sends CSRF and Idempotency-Key, and none on login;
  - an envelope maps to `ControlError`;
  - a 401 signs the session out;
  - the login redirect refuses `//evil` and `https://…`;
  - Shell shows Sign in when signed out.

### F2 — Today, Projects, Project

- **Today** (`/`), from `GET /control/v1/today`. Per project:
  - "since" or "first visit";
  - the changed counts per stage, with the undated count, and the newest rows;
  - **Needs you**, required then optional, linking where a route exists: an `identity` or offer item
    to the flow's Decisions, an adjudication card to the reading desk;
  - **Continues without you**, from `continues_without_you`: the state word and its note.

  A project with `error` shows it. A **Mark as seen** button POSTs `/control/v1/seen`. Signed out, Today
  explains that it needs a session and links to Projects.
- **Projects** (`/projects`): the current index restyled as the design's table: search box (client-side
  filter on name), one row per project, its flows, state words from the API. Keep the lazy per-selector
  summaries.
- **Project** (`/p/:project`): restyle the current page as the design's project header, with a research
  selector (flows, then legacy rounds labelled "protocol not verified"), integrity, and activity.

### F3 — The flow journey

`/p/:project/f/:sel`, restyling `FlowOverviewPage`:
- **Header:** the flow title, the scope and protocol chips from the API, and the buttons **Add
  material**, **Decisions**, **Export** and **Activity**. The first three link to the F5/F6 routes.
- **"Right now":** from `GET …/operations` (signed in). Each operation shows its stage, state word,
  state note, limits, spent USD, units with unknown cost (said as reserved, never 0), and completed
  units. For "worker last seen", show the API's `worker_note`.
  - A `PLANNED` operation has **Authorize**. It opens a confirmation listing the exact limits and
    POSTs them back unchanged.
  - Pause and Resume are shown disabled, with the 501 sentence as their title.
- **Body:** the existing overview content (KPIs, floor, question matrix, tracker), restyled.
- An unbound selector (`/u/`) is read-only and offers no write control.

### F4 — The reading desk

`/p/:project/f/:sel/q/:qid`, restyling `QuestionPage`:
- the existing results, profile and diff panel;
- the stored-profile list (`/profiles`, BR) feeding the diff panel's choices;
- **Signature panel** (flows only, signed in):
  - the five verdicts as radios, none checked, each with its one-line definition from the verdict
    contract (`docs/superpowers/specs/2026-09-25-verdict-contract-design.md`);
  - the reasoning textarea with a live trimmed character count against 120;
  - the attestation checkbox, "I have read the evidence profile this verdict binds to (hash …)";
  - **Sign as {operator name}**, enabled only when a verdict is chosen, the trimmed count is at least
    120, and the box is ticked.

  POST `…/adjudicate` with the shown `profile_sha256`. A 409 renders the server's sentence. On
  `STALE_PROFILE`, show the "the evidence changed" banner, keep the text, and link to the diff.
- **Drafts:** `GET …/draft` on load. If `current` is false, show the design's "profile changed while you
  read" banner: draft kept, signing blocked until the operator reloads the profile. **Save draft** POSTs
  the draft, and saving also happens on textarea blur when the text changed.
- An operational question shows the API's "no verdict applies" state and no panel.

### F5 — Decisions and Add material

- **Decisions** `/p/:project/f/:sel/decisions`, from `GET …/decisions`. **Open** cards come in server
  order (never re-sorted):
  - identity: the four answers, with a reason field required except for `not_sure`, enforcing ≥ 20
    trimmed characters client-side only as a hint, since the server decides;
  - offer: the stage buttons valid for its state, and possession as derived by the server;
  - defer, with a date and a reason, and decline, with a reason, on offers and campaigns.

  A **Decided recently** list follows. Two forms:
  - **Record a verified offer**, with every field from `decisions.md`;
  - **Plan a retry campaign**: candidate ids, then **Preview**, which renders the server plan verbatim
    including the refused hosts, then a campaign name and max requests, then **Approve**.
- **Add material** `/p/:project/f/:sel/material`:
  - **Propose**: kind, value and an optional note. The response row is shown with its state and
    reason.
  - **Upload a file**: a target candidate (a select fed from the overview's source tracker entries,
    showing each key and title), then a PDF picker, then an upload with progress. The client refuses
    files over 50 MiB before sending, and the server is still the authority.
  - The intake list from `GET …/intake`, newest first, with state chips and reasons. A
    `POSSIBLE_VERSION` item links to Decisions.

### F6 — Export, Administration, and the closing pass

- **Export** `/p/:project/f/:sel/export`:
  - the list from the read API's exports route (add `exports` to `api.ts`);
  - **Create snapshot**, with "Include copies whose licence allows it", which shows the `copies`
    answer: included and excluded with reasons;
  - **Verify** per row, rendering `holds` and the problems.
- **Administration** `/admin`:
  - the read API's admin (presence only);
  - when signed in, the control admin: last check per target, **Check** buttons, and the credential
    form (name select, value, password). A 409 `CREDENTIALS_READ_ONLY` is shown as the server says it.
    Never echo a value; clear the field after submit;
  - **Paid test call** disabled, with the 501 reason.
- **States pass:** every page renders loading, error and empty correctly. Add a test per page for the
  empty or failed state.
- **Docs:** update `docs/HANDOFF.md`'s portal paragraph, and add `D` decision entry (next free number) for
  the frontend v2.1: routes, the single write module, and what was left out for lack of data.

## 3. Log and commits

- **Log:** `docs/superpowers/plans/2026-10-07-portal-frontend-v21-progress.md`. For each step:
  - the plan, written first, with sub-tasks;
  - the files touched;
  - the exact final check lines;
  - decisions where the spec is silent, deviations, and NOT DONE.
- **Commits:** on `research-portal` only, one per sub-task (`wip(F<n>.<k>): …`), then
  `feat(portal-frontend): F<n> …`. Stage files by explicit path. Never push, rebase, amend or reset.
  Every message ends with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- **Never touch:** `store/`, `projects/`, Python code, or `.env`.
- **Network:** only the npm registry, for the one font package of F1.
