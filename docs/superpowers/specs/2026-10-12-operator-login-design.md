# Operator login: password management, Google sign-in, people — design

Status: proposed, 2026-10-12. Decision: D### (to be recorded with the live Google run that decides it). D### = the next free decision number at the time of recording (D128–D130 were taken while this was designed).

## Why

Today an operator is declared on the CLI and can never change a password, be re-enabled or sign in any
other way (`claimstone/operators.py`, `docs/contracts/control_api.md` §Sessions). That was right for one
person. The portal now has collaborators, and a signature is the project's one irreversible act:
`actor` (the operator id) is written into every adjudicated verdict. The identity behind an id must stay
unambiguous for ever, and the people who may hold one must be manageable without a shell.

## Decisions taken with the user (2026-10-12)

- Users: the owner and a few collaborators (about ten at most). No self-registration, no public sign-up.
- **Google sign-in is added next to the local password**, not instead of it. The password is the access
  of last resort when Google or the network is unavailable.
- **Approach A**: the append-only `operators.jsonl` stays the source of truth and gains row kinds. No
  database. Google is handled with [Authlib](https://docs.authlib.org/), behind one module.
- **Perimeter: this computer only, for now.** The control server stays bound to loopback. Opening the
  portal to other machines (reverse proxy, HTTPS, a real domain) is a separate piece of work and is
  *not* part of this design. The security rules below are written so that opening it later does not
  change them.

## Identity model

`operators.jsonl` keeps its meaning: installation-level, `CLAIMSTONE_STATE_DIR`, mode 0600, append-only,
a half-written last line is skipped. The state of an id is derived from its rows in order.

Existing rows stay valid and are read as before: a row with `hash` is a `created` row; a row with
`disabled: true` is a `disabled` row. New rows carry `operator_version: 2`, `kind`, `at` (UTC) and `by`
(the actor's operator id, or `cli` for a shell command). Kinds:

| kind | fields besides the common ones | effect |
|---|---|---|
| `created` | `id`, `name`, `role`, `email` (optional), scrypt parameters, `salt`, `hash` | the id exists |
| `password_set` | scrypt parameters, `salt`, `hash` | replaces the password |
| `email_set` | `email` | the address allowed to sign in with Google for this id |
| `role_set` | `role` | `operator` or `admin` |
| `google_linked` | `sub`, `email` | binds a Google account to the id |
| `google_unlinked` | `sub` | removes that binding |
| `disabled` | — | the id cannot sign in; sessions end |
| `enabled` | — | the id can sign in again; the password is unchanged |

Rules, enforced in `operators.py` and nowhere else:

1. **An id is a person and is never reused.** `created` for an id that has any row is refused.
2. **Roles.** `operator` reads and signs. `admin` additionally manages people. Legacy `created` rows
   carry no `role` and are read as `admin`: until now only someone with a shell could create one.
3. **Email is an allowlist entry, not an identity.** At most one active id per address (case-folded).
   Google is bound to an id by `sub`, which Google never reuses; the address is only the gate.
4. **The last active admin cannot be disabled or demoted.** The command is refused, not warned about.
5. **Passwords:** 12 to 256 characters, not equal to the id. No composition rules. scrypt exactly as
   today; parameters travel in the row.
6. **A password change, a disable, or an unlink ends every session of that id** except, for a
   self-service password change, the session making it.
7. The ledger never contains a session token, a Google token or the client secret.

`auth_events.jsonl` (same directory, same rules) records `{at, event, id, method, remote}` for sign-in
success and failure, sign-out, link, unlink and session revocation. It holds no secrets and no
passwords; a failed attempt records the *id typed*, because that is what an investigation needs.

## Google sign-in

Authorization Code flow with PKCE, `openid email profile`, confidential client.

- `GET /control/v1/login/google` (anonymous): creates `state`, `nonce` and a PKCE verifier, stores them in
  a **separate cookie** `claimstone_oauth` — `HttpOnly`, `SameSite=Lax`, `Path=/control/v1/login`,
  10-minute `Max-Age`, `Secure` when the request was TLS. (The session cookie is `SameSite=Strict`,
  which a browser does not send on the redirect back from Google, so the flow cannot ride on it.)
  Answers `302` to Google.
- `GET /control/v1/login/google/callback`: refuses without a matching `state`; exchanges the code;
  verifies the ID token completely — signature against Google's published keys, `iss`, `aud` equal to our
  client id, `exp`, `nonce` — and refuses when `email_verified` is not true. The `hd` claim is never used
  to grant anything. The OAuth cookie is expired in every outcome.
- Outcome rules, in order:
  1. a `sub` already linked to an active id → sign that id in;
  2. else the verified email equals the allowlisted email of exactly one active id that has **no**
     Google link → write `google_linked`, sign in;
  3. anything else → no session, redirect to `/login?error=google_denied`.
  The error code is one fixed value. Unknown address, disabled id, unverified email, id already linked
  to a different Google account and a bad token are indistinguishable to the browser; `auth_events`
  records which one it was.
- A signed-in person can link or unlink their Google account from "My account". Linking runs the same
  flow with `intent=link` recorded in the OAuth cookie and requires the session; the Google address must
  equal the id's allowlisted email. Unlinking asks for the password again.
- Configuration: `CLAIMSTONE_GOOGLE_CLIENT_ID`, `CLAIMSTONE_GOOGLE_CLIENT_SECRET` (from `.env` or the
  environment, never the repository, which is public) and `CLAIMSTONE_PUBLIC_URL` (the base URL
  the browser uses, from which the redirect URI is derived). When any is missing, or when Authlib is not
  installed, Google sign-in is **off**: `GET /control/v1/session/options` (anonymous) answers
  `{"google": false}` and the login page shows no button. Nothing else changes.
- Authlib is installed as an optional extra (`claimstone[login]`) and imported only by
  `claimstone/google_login.py`, lazily. The base install keeps its dependency list; the module is the
  process-or-file-boundary D7 asks for, applied to a library.

## Sessions

- Opaque token, 32 random bytes, a **new token at every sign-in** (no fixation).
- Idle timeout 12 hours as today, plus an **absolute lifetime of 7 days**.
- Each session has a public `session_id` (random, distinct from the token), `created_at`, `last_seen`,
  `method` (`password` or `google`). `GET /control/v1/account/sessions` lists the caller's own;
  `POST /control/v1/account/sessions/end-others` ends the rest. Still in memory only; a restart ends all.
- Login failures: the existing 5 per id per 15 minutes stays; **a second budget of 20 per remote
  address per 15 minutes** is added. Known limit, accepted for a loopback-only perimeter and listed
  under "when the portal is opened": anyone who can reach the login can lock out a *named* id for 15
  minutes.

## Routes

All POST routes keep the existing guards (same-origin `Origin`, CSRF header, `Idempotency-Key` where the
route mutates, the `ROUTES` registry and the anonymous-access sweep).

Anonymous: `GET …/session/options`, `GET …/login/google`, `GET …/login/google/callback`, and the
existing `POST …/session`.

Signed in: `POST …/account/password {current, new}`; `GET …/account/sessions`;
`POST …/account/sessions/end-others`; `POST …/account/google/unlink {password}`; the link flow above.

Admin only, each requiring `password` of the acting admin in the body (`GET …/people` is the one
exception: it has no body):
`GET …/people`; `POST …/people {id, name, email, role, password}`;
`POST …/people/{id}/password {new_password}` (a temporary password the person must change at first
sign-in — the session is limited to changing it until then);
`POST …/people/{id}/disable`, `…/enable`, `…/email`, `…/role`.

The CLI keeps `operator add` and `operator disable` and gains `enable`, `set-password`, `set-email`,
`set-role` and `list`. It writes the same rows through the same functions, so there is no path that
bypasses the rules.

## Portal

Pages built with the i18n infrastructure the wizard introduced, in English and Italian from the start:
the login page (password form, "Sign in with Google" when enabled, the single error text), "My account"
(change password, my sessions, Google link), "People" for admins (list, add, disable/enable, set
temporary password). Navigation shows "People" only to admins; the server does not trust that — every
route checks the role.

## Security checks (tests, not intentions)

Google callback with: bad signature, wrong `iss`, wrong `aud`, expired, wrong `nonce`, wrong or missing
`state`, missing OAuth cookie, `email_verified: false`, an address on no allowlist, a disabled id, a `sub`
linked elsewhere, an id already linked to another `sub` — each yields no session and the same browser
response. Registry tests: id reuse, last admin, disable ends sessions, password change ends other
sessions, absolute lifetime, rate budgets, password length bounds. A sweep asserting no response, log line
or ledger row contains a token, a client secret or a password. Every new route is in `ROUTES` and passes
the anonymous-access sweep. The Google test double signs tokens with a locally generated key and serves
it through the same key-lookup seam the real code uses; no test reaches the network.

## To verify before building (a spike, first task of the plan)

1. Authlib's OAuth2 client and JWT verification work outside a web framework, on `requests`.
2. Google accepts `http://localhost:<port>/…` as a redirect URI for a web client in the form used here,
   and what happens with `127.0.0.1`.
3. The live sign-in with the owner's Google account succeeds end to end. That run is the measurement
   D### records.

## Out of scope

Opening the portal beyond this computer (reverse proxy, HTTPS, domain) — when done it must also revisit
the named-id lockout above and add the `Secure` cookie requirement as a hard check. Password reset by
email, two-factor authentication, providers other than Google, translating the rest of the portal.

### When the portal is opened (recorded 2026-10-12, from the security review of Tasks 4-6)

- `claimstone control --trust-forwarded` exists: the login address budget then keys on `X-Real-IP`,
  which the portal's nginx overwrites from the socket. It is correct only when the reverse proxy is the
  single peer that can reach the control server; it must stay off for any published port.
- The B11 admin routes (`/admin`, `/admin/check`, `/admin/credential`, `/admin/paid-test`) are
  admin-only. Decision of 2026-10-12: credentials and outbound checks are admin powers; operators read
  and sign.
- A failed-login event records whatever was typed as the id. A person who types a password into the id
  field leaves it in `auth_events.jsonl`. Accepted; the Task 9 contract doc says so.
- `login_blocked` rows are unbounded while a block lasts. Revisit when the portal is opened.
