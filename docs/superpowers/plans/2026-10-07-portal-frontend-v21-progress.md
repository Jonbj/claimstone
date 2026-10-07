# Portal frontend v2.1 — progress log

Spec: `docs/superpowers/specs/2026-10-07-portal-frontend-v21-spec.md`. Branch `research-portal`.

| step | title | status |
|---|---|---|
| F1 | Foundations: shell v2, control client, session, login | DONE |
| F2 | Today, Projects, Project | TODO |
| F3 | The flow journey | TODO |
| F4 | The reading desk | TODO |
| F5 | Decisions and Add material | TODO |
| F6 | Export, Administration, closing pass | TODO |

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
