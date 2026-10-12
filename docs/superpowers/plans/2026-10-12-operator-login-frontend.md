# Operator login — portal Implementation Plan (plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The portal's login page offers the password and, when the server has it, "Sign in with Google"; every signed-in person has a "My account" page; admins have a "People" page — all in English and Italian.

**Architecture:** One new section of typed methods in `web/src/lib/control.ts` (the only module allowed to call `fetch` with a non-GET), two new pages, a rewrite of the login page onto the i18n catalogs, and two links in the shell. Google is a plain browser navigation to the server (`<a href>`), never a `fetch`. The API is the one listed in `2026-10-12-operator-login-backend.md` ("API contract"); this plan does not start before that plan's Task 7 is merged.

**Tech Stack:** React 19, react-router 7, Tailwind 4, Vitest + Testing Library; the i18n infrastructure of the wizard (`web/src/lib/i18n.tsx`, `web/src/messages/{en,it}.json`, `t()` with literal keys only).

## Conventions every task follows

- Worktree on branch `operator-login`; from `web/`: `npx vitest run <file>`, at the end `npm run typecheck && npm test && npm run build` (the build runs `check-csp`: **no inline `style`, no inline script**).
- Only `src/lib/control.ts` calls `fetch` for anything but GET. Pages call `control.*`.
- Every visible string is a `t("literal.key")` with the key in **both** `en.json` and `it.json` (the catalog test fails otherwise). Italian copy follows the wizard's register: plain, second person, no jargon without a gloss.
- Commit trailer, every commit:
  ```
  Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE
  ```
- Test style: copy `tests/login.test.tsx` (declarative `MemoryRouter`, `fetch` stubbed with `vi.stubGlobal`, `setCsrfToken("tok")`, `LocaleProvider` + `SessionProvider` wrappers).

## File structure

- Modify `web/src/lib/control.ts` — types and methods. (T1)
- Modify `web/src/lib/session.tsx` — nothing but the `Operator` type flowing through. (T1)
- Modify `web/src/pages/LoginPage.tsx` — catalogs, Google button, error code. (T2)
- Create `web/src/pages/AccountPage.tsx`. (T3)
- Create `web/src/pages/PeoplePage.tsx`. (T4)
- Modify `web/src/components/Shell.tsx`, `web/src/App.tsx` — links, routes, the forced-password-change redirect. (T5)
- Modify `web/src/messages/en.json`, `it.json` throughout. 
- Tests: `tests/controlauth.test.ts`, `tests/login.test.tsx` (extend), `tests/account.test.tsx`, `tests/people.test.tsx`, `tests/shell.test.tsx` (extend).

---

### Task 1: Typed methods in `control.ts`

**Files:** modify `web/src/lib/control.ts`; create `web/tests/controlauth.test.ts`.

- [ ] **Step 1: Failing test** — `tests/controlauth.test.ts`

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { control, setCsrfToken } from "@/lib/control";

let calls: Array<{ url: string; method: string; body: unknown; headers: Record<string, string> }>;
beforeEach(() => {
  setCsrfToken("tok");
  calls = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit = {}) => {
    calls.push({ url, method: init.method ?? "GET", body: init.body ? JSON.parse(String(init.body)) : null,
                 headers: (init.headers ?? {}) as Record<string, string> });
    return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
  });
});
afterEach(() => { vi.unstubAllGlobals(); setCsrfToken(null); });

describe("control auth methods", () => {
  it("reads the sign-in options without a session", async () => {
    await control.sessionOptions();
    expect(calls[0]).toMatchObject({ url: "/control/v1/session/options", method: "GET" });
  });
  it("changes the password with the current one", async () => {
    await control.changePassword("old old old old", "new new new new");
    expect(calls[0]).toMatchObject({ url: "/control/v1/account/password", method: "POST",
      body: { current: "old old old old", new: "new new new new" } });
    expect(calls[0].headers["X-CSRF-Token"]).toBe("tok");
  });
  it("lists and ends sessions, unlinks Google with the password", async () => {
    await control.accountSessions();
    await control.endOtherSessions();
    await control.unlinkGoogle("pw pw pw pw pw");
    expect(calls.map((c) => c.url)).toEqual(["/control/v1/account/sessions", "/control/v1/account/sessions/end-others", "/control/v1/account/google/unlink"]);
    expect(calls[2].body).toEqual({ password: "pw pw pw pw pw" });
  });
  it("manages people, always carrying the acting password", async () => {
    await control.people();
    await control.createPerson({ password: "me", id: "bob", name: "Bob", email: "b@x.org", role: "operator", temporary_password: "tmp tmp tmp tmp" });
    await control.personAct("bob", "disable", { password: "me" });
    await control.personAct("bob", "password", { password: "me", new_password: "tmp tmp tmp tmp" });
    expect(calls.map((c) => c.url)).toEqual(["/control/v1/people", "/control/v1/people", "/control/v1/people/bob/disable", "/control/v1/people/bob/password"]);
  });
  it("percent-encodes the person id", async () => {
    await control.personAct("a/b c", "enable", { password: "me" });
    expect(calls[0].url).toBe("/control/v1/people/a%2Fb%20c/enable");
  });
});
```
Run → FAIL.

- [ ] **Step 2: Implement.** In `control.ts` change the types:

```ts
export interface Operator {
  id: string;
  name: string;
  role: "operator" | "admin";
  must_change_password: boolean;
}

export interface Account extends Operator {
  email: string | null;
  google_linked: boolean;
}

export interface SessionRow {
  session_id: string;
  created_at: string;
  last_seen: string;
  method: "password" | "google";
  current: boolean;
}

export interface Person {
  id: string;
  name: string;
  role: "operator" | "admin";
  email: string | null;
  enabled: boolean;
  google_linked: boolean;
}

export type PersonAction = "password" | "disable" | "enable" | "email" | "role";
```
and, inside the `control` object (next to `signOut`), without an `Idempotency-Key` where the call is a re-authentication (a retry must not replay a password check):

```ts
  sessionOptions: () => get<{ google: boolean }>("/session/options"),
  account: () => get<{ operator: Account }>("/account"),
  changePassword: (current: string, next: string) =>
    post<{ changed: boolean }>("/account/password", { current, new: next }, { idempotent: false }),
  accountSessions: () => get<{ sessions: SessionRow[] }>("/account/sessions"),
  endOtherSessions: () => post<{ ended: number }>("/account/sessions/end-others", {}, { idempotent: false }),
  unlinkGoogle: (password: string) =>
    post<{ unlinked: boolean }>("/account/google/unlink", { password }, { idempotent: false }),
  people: () => get<{ people: Person[] }>("/people"),
  createPerson: (body: { password: string; id: string; name: string; email: string; role: string; temporary_password: string }) =>
    post<{ person: Person }>("/people", body, { idempotent: false }),
  personAct: (id: string, action: PersonAction, body: Record<string, string>) =>
    post<{ person?: Person; changed?: boolean }>(`/people/${enc(id)}/${action}`, body, { idempotent: false }),
```
Also export the Google start path as a constant used by pages: `export const GOOGLE_LOGIN_PATH = `${PREFIX}/login/google`;` and `GOOGLE_LINK_PATH` (`/login/google/link`). Check `parse()` in `control.ts` (`grep -n "ControlError" src/lib/control.ts`) so a 403 `REAUTH` is **not** treated as a sign-out (only 401 is) — it already is.

- [ ] **Step 3:** `npx vitest run tests/controlauth.test.ts` pass; `npm run typecheck` pass (fix any consumer of `Operator` that builds one by hand — `grep -rn "operator:" tests src | grep -v messages`; test fixtures gain `role: "admin", must_change_password: false`).
- [ ] **Step 4: Commit** `portal: typed account and people methods`.

---

### Task 2: The login page — catalogs, Google, the error code

**Files:** modify `web/src/pages/LoginPage.tsx`, `tests/login.test.tsx`, both catalogs.

- [ ] **Step 1: Catalog keys.** Add a top-level `"auth"` object to both files:

English:
```json
"auth": {
  "login": {
    "title": "Sign in",
    "lede": "Reading needs no session. Signing, deciding and exporting do.",
    "id": "Operator id", "password": "Password", "submit": "Sign in", "busy": "Signing in…",
    "checking": "checking the session…",
    "google": "Sign in with Google",
    "or": "or",
    "denied": "That Google account cannot sign in here. Ask an admin to add your email, or use your password.",
    "unavailable": "Google sign-in is not available right now. Use your password."
  }
}
```
Italian:
```json
"auth": {
  "login": {
    "title": "Accedi",
    "lede": "Per leggere non serve accedere. Per firmare, decidere ed esportare sì.",
    "id": "Identificativo", "password": "Password", "submit": "Accedi", "busy": "Accesso in corso…",
    "checking": "controllo la sessione…",
    "google": "Accedi con Google",
    "or": "oppure",
    "denied": "Questo account Google non può accedere qui. Chiedi a un amministratore di aggiungere la tua email, oppure usa la password.",
    "unavailable": "L'accesso con Google non è disponibile in questo momento. Usa la password."
  }
}
```
- [ ] **Step 2: Failing tests** — extend `tests/login.test.tsx` with a stub whose `/session/options` answers `{google: true}`:
  - the page shows an anchor named "Sign in with Google" whose `href` is `/control/v1/login/google`; when options answer `{google: false}` (or fail), no anchor is shown and the password form still works;
  - `?error=google_denied` shows the `auth.login.denied` text in a `role="alert"`; `?error=google_unavailable` shows the other; any other `error` value shows nothing (the code is never echoed);
  - with `?next=/admin` the Google anchor still points at the plain start path (the return path is not carried through Google; document this in the page comment: after Google the person lands on `/`);
  - in Italian (`LocaleProvider` initialised with `it`, as the wizard tests do — copy the way `tests/wizarditalian.test.tsx` sets it) the labels are the Italian ones.
- [ ] **Step 3: Implement.** In `LoginPage.tsx` replace the literals with `t("auth.login.…")`, call `control.sessionOptions()` in an effect (`.catch(() => setGoogle(false))`), and add above the form (when `google`):

```tsx
      {google ? (
        <>
          <a
            href={GOOGLE_LOGIN_PATH}
            className="flex min-h-11 items-center justify-center rounded-lg border border-border bg-card px-4 text-sm font-semibold"
          >
            {t("auth.login.google")}
          </a>
          <p className="text-center text-xs text-muted-foreground" aria-hidden="true">{t("auth.login.or")}</p>
        </>
      ) : null}
```
and, above the form:
```tsx
      {failure ? <p role="alert" className="rounded-lg border border-border bg-card p-3 text-sm">{failure}</p> : null}
```
where `const code = params.get("error"); const failure = code === "google_denied" ? t("auth.login.denied") : code === "google_unavailable" ? t("auth.login.unavailable") : null;`.
- [ ] **Step 4:** tests + typecheck pass. **Step 5: Commit** `portal: login page on the catalogs, with Google and its error codes`.

---

### Task 3: "My account"

**Files:** create `web/src/pages/AccountPage.tsx`, `tests/account.test.tsx`; catalogs.

The page, top to bottom (all inside the existing `Shell`, same `cardClass` look as the wizard — import the class strings from `@/components/wizard/stepTypes` rather than redefining):

1. **Who I am:** name, id, role, email, "Google: linked / not linked".
2. **Change password:** `current`, `new`, `again` (client-side match check only; the server owns every other rule). On success: clear the fields, show "Password changed. Your other sessions were signed out." and call `session.recheck()` so a forced change (`must_change_password`) clears. A 403 `REAUTH` shows "The current password did not match." under the field; a 422 shows the server's sentence.
3. **My sessions:** list from `accountSessions()` (when, how — "password" or "Google", "this session"), and a button "Sign out everywhere else" (`endOtherSessions`, then reload the list).
4. **Google:** when linked, "Unlink" opens an inline password field and calls `unlinkGoogle`; when not linked and Google is enabled (`sessionOptions().google`), an anchor "Link my Google account" to `GOOGLE_LINK_PATH`. The page reads `?google=linked|denied` and shows the matching one-line message (`denied` = "That Google account could not be linked. It must use the email an admin recorded for you.").

- [ ] **Step 1: Catalog keys** under `auth.account.*` in both languages. Required keys (write both texts; Italian in the register above): `title`, `who`, `role.operator`, `role.admin`, `email`, `emailNone`, `googleLinked`, `googleNotLinked`, `passwordTitle`, `current`, `new`, `again`, `mismatch`, `change`, `changed`, `reauth`, `mustChange` (banner: "You are using a temporary password. Choose your own to continue."), `sessionsTitle`, `sessionPassword`, `sessionGoogle`, `sessionThis`, `endOthers`, `endedOthers` (with `{n}`), `googleTitle`, `link`, `unlink`, `unlinkPassword`, `unlinkConfirm`, `linkedOk`, `linkedDenied`.
- [ ] **Step 2: Failing tests** (`tests/account.test.tsx`), `fetch` stubbed by URL:
  - renders name/role/email from `GET /account`;
  - a mismatching "again" blocks the request and shows `auth.account.mismatch` without calling `fetch`;
  - a successful change posts `{current, new}` once, clears the three fields, shows the success text and calls `GET /session` again;
  - a 403 `REAUTH` shows the `reauth` text and keeps the typed `new` value (the person fixes `current` only);
  - the sessions list marks the current one and "Sign out everywhere else" posts and reloads;
  - with `google_linked: true`, "Unlink" reveals a password field and posts `{password}`; with `false` and options `{google:true}`, the link anchor has `href="/control/v1/login/google/link"`; with options `{google:false}` neither control is shown;
  - `?google=linked` / `?google=denied` show the right line;
  - `must_change_password: true` shows the banner.
- [ ] **Step 3: Implement** the page with one `useApi`-style load (`useApi(() => control.account(), [version])` as the wizard pages do) and local state per section; no `window.confirm`; every error through `ErrorState` or the inline sentences above.
- [ ] **Step 4:** tests, typecheck. **Step 5: Commit** `portal: My account — password, sessions, Google link`.

---

### Task 4: "People" (admin)

**Files:** create `web/src/pages/PeoplePage.tsx`, `tests/people.test.tsx`; catalogs.

Behaviour:
- Reads `control.people()`; a non-admin (`operator.role !== "admin"`) sees a one-line "This page is for admins." (the server still refuses; this only spares a 403).
- A table: name, id, role, email, state (active / disabled), Google (linked / —), and per row actions: **Disable / Enable**, **Set temporary password**, **Change email**, **Make admin / Make operator**.
- Every action opens one inline form that asks for **your password** (the acting admin's) and, where relevant, the new value; submit calls `personAct`. A `REAUTH` shows "Your password did not match." The last-admin refusal (422 sentence) is shown as the server gave it.
- **Add a person** form: id, name, email, role (default operator), temporary password, your password → `createPerson`. After success the list reloads and a note says "Give them the temporary password in person; they must choose their own at first sign-in."
- No password is ever kept in state after a submit (clear on success and on failure).

- [ ] **Step 1: Catalog keys** under `auth.people.*`, both languages: `title`, `adminOnly`, columns (`name`, `id`, `role`, `email`, `state`, `google`), `active`, `disabled`, `linked`, `disable`, `enable`, `tempPassword`, `changeEmail`, `makeAdmin`, `makeOperator`, `yourPassword`, `reauth`, `add`, `newId`, `newName`, `newEmail`, `newRole`, `newTemp`, `created`, `save`, `cancel`.
- [ ] **Step 2: Failing tests** — admin sees the table and actions; non-admin sees `adminOnly` and no `fetch` to `/people`; "Disable" posts to `/people/<id>/disable` with `{password}` and reloads; `REAUTH` shows the message and clears the password field; the add form posts exactly `{password,id,name,email,role,temporary_password}`; the last-admin 422 sentence is shown verbatim; the acting person's own row hides "Disable" (the server also refuses; the UI does not offer a doomed button).
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** tests, typecheck. **Step 5: Commit** `portal: People — add, disable, enable, temporary password, email, role`.

---

### Task 5: Shell, routes, and the forced password change

**Files:** modify `web/src/components/Shell.tsx`, `web/src/App.tsx`, `tests/shell.test.tsx`; catalogs (`shell.account`, `shell.people`, `shell.signOut`, `shell.signIn`).

- [ ] **Step 1: Failing tests** (extend `tests/shell.test.tsx`):
  - signed in as an operator the rail shows a link "My account" → `/account`; no "People" link;
  - signed in as an admin it also shows "People" → `/people`;
  - signed out, neither is shown;
  - when the operator has `must_change_password: true`, rendering any route other than `/account` redirects to `/account` (assert `location.pathname`); `/account` itself stays;
  - "Sign out" and "Sign in" now come from the catalog (`shell.signOut`, `shell.signIn`).
- [ ] **Step 2: Implement.** In `App.tsx` add `{ path: "account", element: <AccountPage /> }` and `{ path: "people", element: <PeoplePage /> }`. In `Shell.tsx`: below the NAV block render the two links using the same `Link` styling as the NAV items (People only when `session.operator?.role === "admin"`); move the `Operator()` footer strings onto `t()`; add

```tsx
  const navigate = useNavigate();
  useEffect(() => {
    if (session.operator?.must_change_password && pathname !== "/account") {
      navigate("/account", { replace: true });
    }
  }, [session.operator?.must_change_password, pathname, navigate]);
```
The existing 401 handler already signs the context out, so a server-side `PASSWORD_CHANGE_REQUIRED` (403) on any other call is shown by that page's `ErrorState`, and the redirect makes it unreachable in practice.
- [ ] **Step 3:** `npm run typecheck && npm test && npm run build` — all green (the build also runs `check-csp`). **Step 4: Commit** `portal: account and people in the rail; forced password change`.

---

### Task 6: Try it in a browser, then publish nothing without the user

Not delegated: the controller does this with the user.

- [ ] **Step 1:** Start the control server on a throwaway state dir with two people (`claimstone operator add` ×2, one with `set-email`), start Vite from the worktree, and drive the flows in headless Chrome (the CDP script used for the wizard is the model): password sign-in, wrong password, change password, the sessions list, admin adds a person, that person signs in with the temporary password and is forced to `/account`, admin disables them, their session dies; in Italian too; at 420 px width no horizontal overflow on `/login`, `/account`, `/people`.
- [ ] **Step 2:** With the fake Google provider only if the user has no client yet; otherwise do backend Task 10's live run with the user (their consent screen) and watch the button, the redirect to `/`, the `?error=google_denied` message with an unlisted account, and the link/unlink on `/account`.
- [ ] **Step 3:** Report results to the user. Merge, push and redeploy only on the user's word; the deployed `web` image must be rebuilt (`docker compose up -d --build api control web`) and `.env` must carry the three Google variables from backend Task 9.

---

## Self-review (done)

- **Spec coverage:** login page with password + Google + the single denial text → T2; account (password, sessions, Google link/unlink) → T3; people (add, disable/enable, temporary password, email, role, re-auth) → T4; role-gated navigation and forced change → T5; bilingual → every task adds both catalogs; no `fetch` outside `control.ts` → T1/T2; Google as navigation → T2/T3.
- **Placeholders:** none; the catalog texts for T3/T4 are listed by key and written by the implementer in both languages to the stated register — the Italian copy is reviewed by the user at T6.
- **Types:** `Operator` gains `role` and `must_change_password` (T1) and every consumer is updated in the same task; `Account`, `SessionRow`, `Person`, `PersonAction` match the backend's API contract.
