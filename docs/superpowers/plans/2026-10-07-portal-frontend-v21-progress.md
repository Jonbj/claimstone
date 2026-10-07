# Portal frontend v2.1 — progress log

Spec: `docs/superpowers/specs/2026-10-07-portal-frontend-v21-spec.md`. Branch `research-portal`.

| step | title | status |
|---|---|---|
| F1 | Foundations: shell v2, control client, session, login | IN PROGRESS |
| F2 | Today, Projects, Project | TODO |
| F3 | The flow journey | TODO |
| F4 | The reading desk | TODO |
| F5 | Decisions and Add material | TODO |
| F6 | Export, Administration, closing pass | TODO |

## F1 — Foundations (IN PROGRESS)

- [ ] F1.1 Fonts and theme tokens. Pin `@fontsource/instrument-serif`; v2.1 tokens as CSS variables and Tailwind theme entries.
  Files: `web/package.json`, `web/package-lock.json`, `web/src/index.css`.
- [ ] F1.2 Control client `lib/control.ts` with hand-written types for every control route, `ControlError`, in-memory CSRF; vite dev proxy for `/control`; client tests.
  Files: `web/src/lib/control.ts`, `web/vite.config.ts`, `web/tests/control.test.ts`.
- [ ] F1.3 `SessionProvider` (context, `useSession`), 401 handling; session tests.
  Files: `web/src/lib/session.tsx`, `web/tests/session.test.tsx`.
- [ ] F1.4 Login page `/login`, safe `?next=` redirect; routes wired in `App.tsx` (`/projects`, `/login`, provider).
  Files: `web/src/pages/LoginPage.tsx`, `web/src/lib/session.tsx` (safeNext), `web/src/App.tsx`, `web/tests/login.test.tsx`.
- [ ] F1.5 Shell v2: dark left sidebar, collapse to top bar under 900 px, operator footer; Shell test.
  Files: `web/src/components/Shell.tsx`, `web/tests/shell.test.tsx`.
- [ ] F1.6 Writes test: `writesnothing.test.ts` rewritten as `writes.test.ts`.
  Files: `web/tests/writesnothing.test.ts` (removed), `web/tests/writes.test.ts`.
