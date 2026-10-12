# Operators — the ledger of who may hold a session

Status: built 2026-10-12 (password management, sessions, people). Design:
`docs/superpowers/specs/2026-10-12-operator-login-design.md`. Code: `claimstone/operators.py` (every
identity rule, and no rule elsewhere), `claimstone/auth_events.py`, `claimstone/account_service.py`,
`claimstone/control.py`.

A signature is the project's one irreversible act: the operator id is written into every adjudicated
verdict as `actor`. The identity behind an id must therefore stay unambiguous for ever. This contract is
what keeps it so.

## Files

Both live in `CLAIMSTONE_STATE_DIR` (default `.claimstone/`, gitignored), are installation-level (not per
project), owner-only (`0600`, directory `0700`) and append-only. A half-written last line is skipped, as
`Store.read` skips one. Writers take one lock (`.operators.lock`), so the CLI and the control server may
write concurrently.

| File | Written by | Contains |
|---|---|---|
| `operators.jsonl` | the CLI and the control server, through `operators.py` | one row per change to who may sign in; password hashes |
| `auth_events.jsonl` | the control server | one row per sign-in event; no secret, no hash |

## `operators.jsonl` row kinds

Every `operator_version: 2` row carries `operator_version`, `kind`, `id`, `at` (UTC) and `by` (the actor's
operator id, or `cli` for a shell command). The state of an id is derived from its rows, in order.

| kind | fields besides the common ones | effect |
|---|---|---|
| `created` | `name`, `role`, `email` (optional), `must_change_password`, `created_at`, `scrypt` parameters, `salt`, `hash` | the id exists |
| `password_set` | `must_change_password`, `scrypt` parameters, `salt`, `hash` | replaces the password |
| `email_set` | `email` (or null) | the address allowlisted for this id |
| `role_set` | `role` | `operator` or `admin` |
| `disabled` | `disabled: true` | the id cannot sign in; its sessions end |
| `enabled` | — | the id can sign in again; the password is unchanged |
| `google_linked` | `sub`, `email` | reserved: written only by a future Google sign-in |
| `google_unlinked` | `sub` | reserved: written only by a future Google sign-in |

The two `google_*` kinds are already read (`operators.link_google`, `unlink_google` and `find_by_sub`
exist and are tested) so that adding Google sign-in later changes no file format. **Nothing writes them
today**, and no route or command exists for them: `GET /control/v1/session/options` answers
`{"google": false}`.

### Legacy rows

`operator_version: 1` rows stay valid and are never rewritten. They are read as follows:

- A row with `hash` and `salt` and no `kind` is a `created` row. It has no `role` and is read as `admin`:
  until this change only someone with a shell could create an operator.
- A row with `disabled: true` and no `kind` is a `disabled` row.
- Any other row without a `kind` is ignored.
- A `created` row for an id that already has a `created` row is ignored (the first row wins), and so is
  a `created` row without `hash` and `salt`.
- `disabled: true` is also written on new `disabled` rows, so that code reading only version 1 still
  drops the id after a rollback.

## Rules

Enforced in `operators.py` and nowhere else; the CLI and the portal call the same functions.

1. **An id is a person and is never reused.** `created` for an id that has any row is refused.
2. **Roles.** `operator` reads and signs. `admin` additionally manages people and the B11 administration
   routes. Legacy `created` rows carry no `role` and are read as `admin`. With no `--role`, a new person
   is an admin while no active admin exists, otherwise an operator.
3. **Email is an allowlist entry, not an identity.** At most one active id per address (case-folded). It
   is for a future Google sign-in; a password sign-in does not use it. Google would be bound to an id by
   `sub`, which Google never reuses; the address would only be the gate.
4. **The last active admin cannot be disabled or demoted.** The command is refused, not warned about.
5. **Passwords:** 12 to 256 characters, not equal to the id. No composition rules. `hashlib.scrypt`
   (n=2^15, r=8, p=1); the parameters travel in the row.
6. **A password change, a disable, or an unlink ends every session of that id**, except, for a
   self-service password change, the session making it.
7. The ledger never contains a session token, a Google token or a client secret.

### Ids

New ids match `[a-z0-9][a-z0-9._-]{0,63}`: ASCII, so two ids never look alike. Ids already in the ledger
are never re-validated against it.

## The credential stamp and revocation

`operators.stamp(person)` is a 16-hex fingerprint (SHA-256 of the current salt and hash). A session
records the stamp it was minted under. **Every request re-reads the ledger** and ends the session unless
the person is still enabled and the stamp still matches. A disable, a password change or a reset made by
any process, the CLI included, therefore ends the session on its next request; no signal between
processes is needed. A login that verified an old credential and created its session after the change is
caught by the same comparison. The change of password a person makes themselves re-stamps the session
that made it, so it stays signed in; every other session of that id ends.

An admin's role is read from the ledger at each request too: a demoted or disabled admin loses the power
at once.

## `auth_events.jsonl`

One JSON object per line: `{at, event, id, method, remote, detail, by}`. `id` is the id typed (failed
attempts) or the id concerned; `method` is `password`; `remote` is the address the budgets key on;
`detail` is a short fixed code (at most 60 characters); `by` is the acting admin where there is one.
`id` and `remote` are cut (200 and 64 characters) and stripped of control characters, so a hostile value
cannot forge a second line. It holds no password, no token and no hash.

Events written today: `login_ok`, `login_failed`, `login_blocked`, `reauth_failed`, `password_changed`,
`password_set_by_admin`, `person_created`, `person_disabled`, `person_enabled`, `person_email_set`,
`person_role_set`, `sessions_revoked`, `logout`.
Names defined and not written yet: `google_ok`, `google_denied`, `google_linked`,
`google_unlinked`. A shell command writes `operators.jsonl` only; it leaves no `auth_events` row.

## Command line

```
claimstone operator add ID --name NAME [--role operator|admin] [--email ADDRESS]   # prompts for a password twice
claimstone operator disable ID
claimstone operator enable ID
claimstone operator set-password ID [--must-change]                                # prompts twice
claimstone operator set-email ID ADDRESS
claimstone operator set-role ID operator|admin
claimstone operator list      # id, name, role, enabled|disabled, email or '-' — tab-separated
```

Every command writes with `by: "cli"`. A refusal prints its one sentence on stderr and exits 2. No
password is ever an argument. `set-password` and `disable` also print `sessions of a running control
server end on their next request`, which is true because of the credential stamp above.
`--must-change` makes the person's next session limited to changing the password.

## The portal's routes

The routes, their bodies and error codes are in `docs/contracts/control_api.md` §Sessions. The shape in
one paragraph: a signed-in person changes their own password (`current`, `new`), lists their sessions and
ends the others; an admin lists, creates and disables/enables people, sets a temporary password (the
person must change it at first sign-in) and sets email and role, each time sending **their own**
password again (`password`), which counts against the same failure budget as a login.

## When the portal is opened

Opening the portal beyond this computer (reverse proxy exposed to a network, HTTPS, a real domain) is
**not covered by this contract or by what was built**. The perimeter today is this computer. The notes
below are what is already known, so that the work, when it is done, starts from them.

- `claimstone control --trust-forwarded` makes the per-address login budget key on `X-Real-IP`, which the
  portal's nginx overwrites from the socket. It is correct only when that reverse proxy is the single peer
  that can reach the control server. **It must stay off for any published port**; with it on, anyone who
  can reach the port chooses their own address and the budget means nothing.
- A failed-login event records whatever was typed as the id. A person who types their password into the
  id field leaves it in `auth_events.jsonl`. Accepted: an investigation needs the id as typed. What is
  promised is narrower: a password sent in the `password` field, a session token and a CSRF token appear
  in no ledger, response or log line (`tests/test_login_security_sweep.py`).
- `login_blocked` rows are unbounded while a block lasts: every refused attempt during the 15 minutes
  appends one. Revisit when the portal is opened.
- Anyone who can reach the login can lock out a *named* id for 15 minutes (5 failures per id per 15
  minutes). Accepted for a loopback perimeter; it must be revisited, and the `Secure` cookie requirement
  made a hard check, before any wider opening.
- The B11 administration routes (`/admin`, `/admin/check`, `/admin/credential`, `/admin/paid-test`) are
  open to every operator (decision of 2026-10-12, revising an earlier admin-only choice the same day): an
  admin differs from an operator in one thing, managing people. Every `/people` route is admin-only, and
  the server checks the role in the ledger on each request; the portal hiding a menu entry is a
  convenience, not a control.
