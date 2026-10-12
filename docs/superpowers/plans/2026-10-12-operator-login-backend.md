# Operator login — backend Implementation Plan (plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Operators can change their password, sign in with Google, and be managed from the portal; the ledger of operators stays append-only and every rule of `docs/superpowers/specs/2026-10-12-operator-login-design.md` is enforced in code.

**Architecture:** `operators.py` keeps the append-only `operators.jsonl` and gains row kinds plus every identity rule (one module, no rule elsewhere). `auth_events.py` is a second append-only ledger of sign-in events. `control.py` gets richer sessions (id, method, absolute lifetime, revocation), an address budget, and thin handlers; Google lives behind one lazily imported module, `google_login.py`. The CLI writes the same rows through the same functions.

**Tech Stack:** Python ≥ 3.11, stdlib + `requests`; Authlib (+ `cryptography`) as the optional extra `claimstone[login]`, imported only by `google_login.py`. Tests: pytest, one real server on a port-0 bind (as `tests/test_control.py`).

**Frontend is plan 2** (`2026-10-12-operator-login-frontend.md`); it consumes the API listed under "API contract" below. Do not start it before Task 6 of this plan is merged.

## Conventions every task follows

- Work in a worktree on branch `operator-login` (the spec is already committed there). Run `.venv/bin/pytest -q <file>` per task, the full suite at the end of Tasks 3, 6, 8.
- Commit trailer, every commit:
  ```
  Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE
  ```
- No secret (token, password, client secret) may appear in a ledger row, a log line, an error message or a response. Tests in Task 8 sweep for it.
- Existing tests call `operators.add_operator(..., "pw")` and similar short passwords. The new password rule (12–256 chars) applies inside `add_operator`; **Task 1 step 1 updates those tests** to a long password. Nothing else in them changes.

## API contract (what plan 2 builds against)

All under `/control/v1`. Errors use the existing envelope `{"error": {"code", "message", "details"?}}`.

| Method + path | Auth | Body → answer |
|---|---|---|
| `POST /session` | public | `{id, password}` → `{operator: {id, name, role, must_change_password}, csrf_token}` |
| `GET /session` | session | same shape |
| `GET /session/options` | public | `{google: bool}` |
| `GET /login/google` | public | `302` to Google (or to `PUBLIC_URL/login?error=google_unavailable` when off) |
| `GET /login/google/link` | session | `302` to Google, flow bound to the signed-in id |
| `GET /login/google/callback` | public | `302` to `PUBLIC_URL/` (signed in) or `PUBLIC_URL/login?error=google_denied`; link flow: `PUBLIC_URL/account?google=linked` or `?google=denied` |
| `GET /account` | session | `{operator: {id, name, role, email, google_linked, must_change_password}}` |
| `POST /account/password` | session | `{current, new}` → `{changed: true}` |
| `GET /account/sessions` | session | `{sessions: [{session_id, created_at, last_seen, method, current}]}` |
| `POST /account/sessions/end-others` | session | `{}` → `{ended: n}` |
| `POST /account/google/unlink` | session | `{password}` → `{unlinked: true}` |
| `GET /people` | admin | `{people: [{id, name, role, email, enabled, google_linked}]}` |
| `POST /people` | admin | `{password, id, name, email, role, temporary_password}` → `201 {person}` |
| `POST /people/{id}/password` | admin | `{password, new_password}` → `{changed: true}` (marks `must_change_password`) |
| `POST /people/{id}/disable`, `/enable` | admin | `{password}` → `{person}` |
| `POST /people/{id}/email` | admin | `{password, email}` → `{person}` |
| `POST /people/{id}/role` | admin | `{password, role}` → `{person}` |

`password` in an admin body is the **acting admin's** password (re-authentication, same budget as a failed login, 403 `REAUTH`). A non-admin gets 403 `FORBIDDEN`. While a session `must_change_password`, every route except `GET/POST /session…` and `POST /account/password` answers 403 `PASSWORD_CHANGE_REQUIRED`.

## File structure

- Modify `claimstone/operators.py` — row kinds, state fold, rules, flock. (T1)
- Create `claimstone/auth_events.py` — the sign-in event ledger. (T2)
- Modify `claimstone/control.py` — `Sessions`, `AddressBudget`, session routes, account and people handlers, redirect helper, Google routes. (T3–T6)
- Create `claimstone/account_service.py` — the rules the account/people handlers apply, free of HTTP. (T4–T5)
- Create `claimstone/google_login.py` — Authlib behind a seam. (T7)
- Modify `claimstone/cli.py` — `operator enable|set-password|set-email|set-role|list`. (T8)
- Modify `pyproject.toml`, `compose.yaml`, `Dockerfile`, `.env.example` (if present), `docs/contracts/control_api.md`, `docs/DESIGN_DECISIONS.md`. (T9–T10)
- Tests: `tests/test_operators_ledger.py`, `tests/test_auth_events.py`, `tests/test_control_accounts.py`, `tests/test_google_login.py`, `tests/test_login_security_sweep.py`.

---

### Task 0: Spike — does the library do what the spec assumes?

**Files:** create `docs/superpowers/notes/2026-10-12-google-login-spike.md` (findings only; no production code).

The spec lists three things to verify. Nothing past this task may assume them.

- [ ] **Step 1: Install and check the framework-free client**

```bash
.venv/bin/pip install "authlib>=1.3" "cryptography>=42"
.venv/bin/python - <<'PY'
from authlib.integrations.requests_client import OAuth2Session
from authlib.jose import JsonWebKey, jwt
s = OAuth2Session("id", "secret", scope="openid email profile",
                  redirect_uri="http://localhost:5173/control/v1/login/google/callback",
                  code_challenge_method="S256")
url, state = s.create_authorization_url("https://accounts.google.com/o/oauth2/v2/auth",
                                        nonce="n", code_verifier="v" * 64)
print(url)
key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
token = jwt.encode({"alg": "RS256", "kid": "k"}, {"iss": "x", "aud": "id", "sub": "1", "exp": 4102444800, "nonce": "n"}, key)
claims = jwt.decode(token, JsonWebKey.import_key_set({"keys": [key.as_dict(is_private=False)]}),
                    claims_options={"iss": {"values": ["x"]}, "aud": {"value": "id"}, "nonce": {"essential": True, "value": "n"}})
claims.validate(); print(dict(claims))
PY
```
Expected: an authorization URL containing `code_challenge=` and `code_challenge_method=S256`, then the claims dict. If the API differs (keyword names, `import_key_set`), record the correct calls — Task 7 uses them.

- [ ] **Step 2: Read Google's own documentation for redirect URIs**

Open https://developers.google.com/identity/protocols/oauth2/web-server and the "Authorized redirect URIs" rules in the Cloud Console help. Record, quoted briefly with the URL: is `http://localhost:<port>/path` accepted for a *Web application* client; is `http://127.0.0.1:<port>/path`; is a path allowed; is HTTPS required for anything else.

- [ ] **Step 3: Record and commit**

Write the three findings (works / does not, with the exact calls) in the note, and a line "Live end-to-end run: pending, done in Task 10". Commit:

```bash
git add docs/superpowers/notes/2026-10-12-google-login-spike.md
git commit -m "spike: Authlib outside a framework and Google's redirect rules"   # + trailer
```
If step 1 fails or step 2 says `localhost` is refused: **stop and report to the user**; Task 7 and the perimeter decision depend on it.

---

### Task 1: The ledger — row kinds and every identity rule

**Files:** modify `claimstone/operators.py`; create `tests/test_operators_ledger.py`; modify the existing tests that use short passwords (`grep -rn 'add_operator(' tests tools`).

- [ ] **Step 1: Make the existing tests use a valid password**

Replace the passwords `"pw"`, `"pw2"` and `"secret-password"` in the `add_operator(...)` calls found by the grep with `"long-enough-pass-1"` / `"long-enough-pass-2"` and the matching `verify(...)` arguments (`tests/test_control.py:85-86`). Run `.venv/bin/pytest -q tests/test_control.py` — expected: still green (nothing enforces the rule yet).

- [ ] **Step 2: Write the failing ledger tests**

`tests/test_operators_ledger.py`:

```python
"""The operators ledger's identity rules (design 2026-10-12). No socket, no server."""

from __future__ import annotations

import json

import pytest

from claimstone import operators
from claimstone.operators import OperatorError

PW = "correct horse battery"


@pytest.fixture()
def d(tmp_path):
    return tmp_path / "state"


def test_first_person_is_admin_later_ones_operators(d):
    assert operators.add_operator(d, "a", "Alpha", PW)["role"] == "admin"
    assert operators.add_operator(d, "b", "Beta", PW)["role"] == "operator"
    assert operators.people(d)["b"]["role"] == "operator"


def test_legacy_rows_read_as_admin_and_still_verify(d):
    d.mkdir()
    legacy = {"operator_version": 1, "id": "old", "name": "Old", "scrypt": operators.SCRYPT,
              "salt": "00" * 16, "hash": operators._hash("legacy password!", bytes(16), operators.SCRYPT),
              "created_at": "2026-10-01T00:00:00+00:00"}
    (d / "operators.jsonl").write_text(json.dumps(legacy) + "\n" + json.dumps(
        {"operator_version": 1, "id": "old", "disabled": True, "disabled_at": "x"}) + "\n")
    assert operators.people(d)["old"]["role"] == "admin"
    assert operators.load(d) == {}                       # disabled
    operators.enable_operator(d, "old", by="cli")
    assert operators.verify(operators.load(d)["old"], "legacy password!")


@pytest.mark.parametrize("password", ["short", "x" * 257, "alpha-user-id"])
def test_password_rule(d, password):
    with pytest.raises(OperatorError):
        operators.add_operator(d, "alpha-user-id", "Alpha", password)


def test_an_id_is_never_reused(d):
    operators.add_operator(d, "a", "Alpha", PW)
    operators.disable_operator(d, "a", by="cli")
    with pytest.raises(OperatorError, match="already recorded"):
        operators.add_operator(d, "a", "Again", PW)


def test_email_is_unique_among_enabled_people_and_case_folded(d):
    operators.add_operator(d, "a", "Alpha", PW, email="Ann@Example.org")
    with pytest.raises(OperatorError, match="email"):
        operators.add_operator(d, "b", "Beta", PW, email="ann@example.org")
    operators.add_operator(d, "b", "Beta", PW, email="bob@example.org")
    with pytest.raises(OperatorError, match="email"):
        operators.set_email(d, "b", "ANN@example.org", by="a")


def test_last_admin_cannot_be_disabled_or_demoted(d):
    operators.add_operator(d, "a", "Alpha", PW)
    with pytest.raises(OperatorError, match="last admin"):
        operators.disable_operator(d, "a", by="a")
    with pytest.raises(OperatorError, match="last admin"):
        operators.set_role(d, "a", "operator", by="a")
    operators.add_operator(d, "b", "Beta", PW, role="admin")
    operators.set_role(d, "a", "operator", by="b")        # now allowed
    with pytest.raises(OperatorError, match="last admin"):
        operators.disable_operator(d, "b", by="b")


def test_password_change_replaces_the_hash_and_can_demand_a_change(d):
    operators.add_operator(d, "a", "Alpha", PW)
    operators.set_password(d, "a", "a brand new password", by="a", must_change=True)
    person = operators.load(d)["a"]
    assert operators.verify(person, "a brand new password") and not operators.verify(person, PW)
    assert person["must_change_password"] is True
    operators.set_password(d, "a", "yet another password", by="a")
    assert operators.load(d)["a"]["must_change_password"] is False


def test_google_link_rules(d):
    operators.add_operator(d, "a", "Alpha", PW, email="a@example.org")
    operators.add_operator(d, "b", "Beta", PW, email="b@example.org")
    operators.link_google(d, "a", sub="sub-1", email="A@example.org", by="a")
    assert operators.find_by_sub(d, "sub-1")["id"] == "a"
    with pytest.raises(OperatorError, match="already linked"):
        operators.link_google(d, "b", sub="sub-1", email="b@example.org", by="b")
    with pytest.raises(OperatorError, match="already has"):
        operators.link_google(d, "a", sub="sub-2", email="a@example.org", by="a")
    with pytest.raises(OperatorError, match="email"):
        operators.link_google(d, "b", sub="sub-3", email="other@example.org", by="b")
    operators.unlink_google(d, "a", by="a")
    assert operators.find_by_sub(d, "sub-1") is None
    operators.link_google(d, "b", sub="sub-1", email="b@example.org", by="b")   # free again


def test_find_by_email_returns_enabled_people_only(d):
    operators.add_operator(d, "a", "Alpha", PW, email="a@example.org")
    operators.add_operator(d, "b", "Beta", PW, email="b@example.org")
    operators.disable_operator(d, "b", by="a")
    assert operators.find_by_email(d, "A@example.org")["id"] == "a"
    assert operators.find_by_email(d, "b@example.org") is None


def test_new_rows_say_who_and_when_and_hold_no_plaintext(d):
    operators.add_operator(d, "a", "Alpha", PW, by="cli")
    operators.set_password(d, "a", "a brand new password", by="a")
    text = (d / "operators.jsonl").read_text()
    assert "correct horse" not in text and "brand new" not in text
    rows = [json.loads(line) for line in text.splitlines()]
    assert [r["kind"] for r in rows] == ["created", "password_set"]
    assert all(r["operator_version"] == 2 and r["by"] and r["at"] for r in rows)
```

Run: `.venv/bin/pytest -q tests/test_operators_ledger.py` → FAIL (`people`, `enable_operator`… not defined).

- [ ] **Step 3: Implement in `claimstone/operators.py`**

Keep `LEDGER`, `SCRYPT`, `_rows`, `_append`, `_hash`, `DUMMY_ROW`, `verify`, `state_dir`, `_now`, `_check_id` as they are. Change `OPERATOR_VERSION = 2`, add near the top:

```python
import fcntl
from contextlib import contextmanager

ROLES = ("operator", "admin")
PASSWORD_MIN, PASSWORD_MAX = 12, 256


def check_password(password: object, operator_id: str | None = None) -> str:
    """The one password rule. Length only: no composition rules, and an upper bound because
    scrypt's cost grows with the input."""
    if not isinstance(password, str) or len(password) < PASSWORD_MIN:
        raise OperatorError(f"password must have at least {PASSWORD_MIN} characters")
    if len(password) > PASSWORD_MAX:
        raise OperatorError(f"password must have at most {PASSWORD_MAX} characters")
    if operator_id is not None and password == operator_id:
        raise OperatorError("password must not be the id")
    return password


def _email(value: object) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip().lower()
    if "@" not in text or " " in text or "\n" in text or len(text) > 254:
        raise OperatorError("email must look like an address")
    return text


@contextmanager
def _locked(directory: pathlib.Path):
    """One writer at a time across processes (the CLI and the control server share the file):
    every rule below reads then appends, and must not interleave with another writer."""
    directory = pathlib.Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(directory / ".operators.lock", "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _fold(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Every person ever recorded, in their current state. Legacy rows (version 1) have no
    `kind`: a row with a hash is `created`, a row with `disabled` is `disabled`; a legacy
    `created` row has no role and reads as admin (only a shell could create one)."""
    people: dict[str, dict[str, Any]] = {}
    for row in rows:
        oid = str(row.get("id"))
        kind = row.get("kind") or ("disabled" if row.get("disabled") else "created")
        if kind == "created":
            people[oid] = {
                "id": oid, "name": row.get("name") or "", "role": row.get("role") or "admin",
                "email": _email(row.get("email")), "scrypt": dict(row.get("scrypt") or SCRYPT),
                "salt": row["salt"], "hash": row["hash"], "enabled": True, "google_sub": None,
                "must_change_password": bool(row.get("must_change_password")),
                "created_at": row.get("created_at") or row.get("at")}
            continue
        person = people.get(oid)
        if person is None:
            continue
        if kind == "password_set":
            person.update(scrypt=dict(row.get("scrypt") or SCRYPT), salt=row["salt"], hash=row["hash"],
                          must_change_password=bool(row.get("must_change_password")))
        elif kind == "email_set":
            person["email"] = _email(row.get("email"))
        elif kind == "role_set":
            person["role"] = row["role"]
        elif kind == "google_linked":
            person["google_sub"] = row["sub"]
        elif kind == "google_unlinked":
            if person["google_sub"] == row.get("sub"):
                person["google_sub"] = None
        elif kind == "disabled":
            person["enabled"] = False
        elif kind == "enabled":
            person["enabled"] = True
    return people


def people(directory: str | pathlib.Path) -> dict[str, dict[str, Any]]:
    """Everyone ever recorded, enabled or not, in their current state."""
    return _fold(_rows(pathlib.Path(directory)))


def load(directory: str | pathlib.Path) -> dict[str, dict[str, Any]]:
    """Who may sign in: the enabled people. The returned rows carry `salt`/`hash`/`scrypt`, so
    `verify(row, password)` works on them exactly as before."""
    return {oid: p for oid, p in people(directory).items() if p["enabled"]}


def _write(directory: pathlib.Path, kind: str, oid: str, by: str, now: str | None,
           **fields: Any) -> dict[str, Any]:
    row = {"operator_version": OPERATOR_VERSION, "kind": kind, "id": oid,
           "at": now or _now(), "by": by, **fields}
    _append(directory, row)
    return row


def _active_admins(everyone: dict[str, dict[str, Any]], excluding: str | None = None) -> int:
    return sum(1 for oid, p in everyone.items()
               if p["enabled"] and p["role"] == "admin" and oid != excluding)


def _taken_email(everyone: dict[str, dict[str, Any]], email: str | None, owner: str | None) -> bool:
    return email is not None and any(
        p["enabled"] and p["email"] == email and oid != owner for oid, p in everyone.items())


def _hashed(password: str) -> dict[str, Any]:
    salt = secrets.token_bytes(SALT_LENGTH)
    return {"scrypt": dict(SCRYPT), "salt": salt.hex(), "hash": _hash(password, salt, SCRYPT)}


def _person(everyone: dict[str, dict[str, Any]], oid: str) -> dict[str, Any]:
    if oid not in everyone:
        raise OperatorError(f"unknown operator: {oid}")
    return everyone[oid]
```

Replace `add_operator` and `disable_operator`, and add the rest:

```python
def add_operator(directory, operator_id: str, name: str, password: str, *,
                 role: str | None = None, email: str | None = None, must_change: bool = False,
                 by: str = "cli", now: str | None = None) -> dict[str, Any]:
    """Append a `created` row. An id with any row is refused for ever. With no `role`, the first
    person recorded is an admin and later ones are operators."""
    _check_id(operator_id)
    if not name.strip():
        raise OperatorError("operator name must be non-empty")
    check_password(password, operator_id)
    directory = pathlib.Path(directory)
    with _locked(directory):
        everyone = people(directory)
        if operator_id in everyone:
            raise OperatorError(f"operator already recorded: {operator_id}")
        email = _email(email)
        if _taken_email(everyone, email, None):
            raise OperatorError("that email already belongs to another active operator")
        role = role or ("admin" if _active_admins(everyone) == 0 else "operator")
        if role not in ROLES:
            raise OperatorError(f"role must be one of {', '.join(ROLES)}")
        return _write(directory, "created", operator_id, by, now, name=name, role=role,
                      email=email, must_change_password=must_change, created_at=now or _now(),
                      **_hashed(password))


def disable_operator(directory, operator_id: str, *, by: str = "cli",
                     now: str | None = None) -> dict[str, Any]:
    _check_id(operator_id)
    directory = pathlib.Path(directory)
    with _locked(directory):
        everyone = people(directory)
        person = _person(everyone, operator_id)
        if not person["enabled"]:
            raise OperatorError(f"operator already disabled: {operator_id}")
        if person["role"] == "admin" and _active_admins(everyone, operator_id) == 0:
            raise OperatorError("refused: this is the last admin")
        return _write(directory, "disabled", operator_id, by, now)


def enable_operator(directory, operator_id: str, *, by: str = "cli",
                    now: str | None = None) -> dict[str, Any]:
    directory = pathlib.Path(directory)
    with _locked(directory):
        everyone = people(directory)
        person = _person(everyone, operator_id)
        if person["enabled"]:
            raise OperatorError(f"operator already enabled: {operator_id}")
        if _taken_email(everyone, person["email"], operator_id):
            raise OperatorError("that email now belongs to another active operator")
        return _write(directory, "enabled", operator_id, by, now)


def set_password(directory, operator_id: str, new_password: str, *, by: str,
                 must_change: bool = False, now: str | None = None) -> dict[str, Any]:
    check_password(new_password, operator_id)
    directory = pathlib.Path(directory)
    with _locked(directory):
        _person(people(directory), operator_id)
        return _write(directory, "password_set", operator_id, by, now,
                      must_change_password=must_change, **_hashed(new_password))


def set_email(directory, operator_id: str, email: str | None, *, by: str,
              now: str | None = None) -> dict[str, Any]:
    directory = pathlib.Path(directory)
    with _locked(directory):
        everyone = people(directory)
        _person(everyone, operator_id)
        clean = _email(email)
        if _taken_email(everyone, clean, operator_id):
            raise OperatorError("that email already belongs to another active operator")
        return _write(directory, "email_set", operator_id, by, now, email=clean)


def set_role(directory, operator_id: str, role: str, *, by: str,
             now: str | None = None) -> dict[str, Any]:
    if role not in ROLES:
        raise OperatorError(f"role must be one of {', '.join(ROLES)}")
    directory = pathlib.Path(directory)
    with _locked(directory):
        everyone = people(directory)
        person = _person(everyone, operator_id)
        if (person["enabled"] and person["role"] == "admin" and role != "admin"
                and _active_admins(everyone, operator_id) == 0):
            raise OperatorError("refused: this is the last admin")
        return _write(directory, "role_set", operator_id, by, now, role=role)


def link_google(directory, operator_id: str, *, sub: str, email: str, by: str,
                now: str | None = None) -> dict[str, Any]:
    """Bind a Google account to an id. The address must be the id's allowlisted email; the `sub`
    must be free and the id must not already have a link."""
    if not sub or not isinstance(sub, str):
        raise OperatorError("a Google account needs a subject")
    directory = pathlib.Path(directory)
    with _locked(directory):
        everyone = people(directory)
        person = _person(everyone, operator_id)
        if not person["enabled"]:
            raise OperatorError("operator is disabled")
        if person["google_sub"]:
            raise OperatorError("operator already has a Google account linked")
        if any(p["google_sub"] == sub for p in everyone.values()):
            raise OperatorError("that Google account is already linked")
        if person["email"] is None or _email(email) != person["email"]:
            raise OperatorError("the Google email is not this operator's email")
        return _write(directory, "google_linked", operator_id, by, now, sub=sub, email=_email(email))


def unlink_google(directory, operator_id: str, *, by: str, now: str | None = None) -> dict[str, Any]:
    directory = pathlib.Path(directory)
    with _locked(directory):
        person = _person(people(directory), operator_id)
        if not person["google_sub"]:
            raise OperatorError("no Google account is linked")
        return _write(directory, "google_unlinked", operator_id, by, now, sub=person["google_sub"])


def find_by_sub(directory, sub: str) -> dict[str, Any] | None:
    return next((p for p in load(directory).values() if p["google_sub"] == sub), None)


def find_by_email(directory, email: str) -> dict[str, Any] | None:
    try:
        clean = _email(email)
    except OperatorError:
        return None
    return next((p for p in load(directory).values() if clean and p["email"] == clean), None)
```
Delete the old `load` (superseded) — the new one above replaces it. `verify` and `DUMMY_ROW` stay.

- [ ] **Step 4:** `.venv/bin/pytest -q tests/test_operators_ledger.py tests/test_control.py` → all pass.
- [ ] **Step 5: Commit** `operators: row kinds, identity rules, one writer at a time` (+ trailer).

---

### Task 2: The sign-in event ledger

**Files:** create `claimstone/auth_events.py`, `tests/test_auth_events.py`.

- [ ] **Step 1: Failing test**

```python
import json, os, stat
from claimstone import auth_events


def test_records_are_owner_only_single_lines_without_control_characters(tmp_path):
    auth_events.record(tmp_path, "login_failed", id="a\nb" + "x" * 300, method="password",
                       remote="127.0.0.1", detail="bad_password", now="2026-10-12T00:00:00+00:00")
    path = tmp_path / "auth_events.jsonl"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    (line,) = path.read_text().splitlines()
    row = json.loads(line)
    assert row["event"] == "login_failed" and "\n" not in row["id"] and len(row["id"]) <= 200
    assert row["at"] == "2026-10-12T00:00:00+00:00"


def test_an_unknown_event_name_is_refused(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        auth_events.record(tmp_path, "something_else")
```
Run → FAIL.

- [ ] **Step 2: Implement**

```python
"""auth_events.jsonl — who tried to sign in, how, and what came of it (design 2026-10-12).

Append-only, owner-only, in the same state directory as `operators.jsonl`. It never holds a
password, a token or a Google claim beyond the subject: `detail` is a short fixed code. A failed
attempt records the *id typed*, because that is what an investigation needs; it is cut to 200
characters and stripped of control characters so a hostile id cannot forge a second line.
"""

from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime, timezone

LEDGER = "auth_events.jsonl"
EVENTS = frozenset({
    "login_ok", "login_failed", "login_blocked", "logout", "google_ok", "google_denied",
    "google_linked", "google_unlinked", "password_changed", "password_set_by_admin",
    "sessions_revoked", "person_created", "person_disabled", "person_enabled",
    "person_email_set", "person_role_set", "reauth_failed"})


def _clean(value: object, limit: int = 200) -> str | None:
    if value is None:
        return None
    text = "".join(ch for ch in str(value) if ch.isprintable())
    return text[:limit]


def record(directory: str | pathlib.Path, event: str, *, id: object = None,
           method: str | None = None, remote: object = None, detail: str | None = None,
           by: object = None, now: str | None = None) -> None:
    if event not in EVENTS:
        raise ValueError(f"unknown auth event: {event}")
    row = {"at": now or datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "event": event, "id": _clean(id), "method": _clean(method, 20),
           "remote": _clean(remote, 64), "detail": _clean(detail, 60), "by": _clean(by)}
    path = pathlib.Path(directory) / LEDGER
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
```

- [ ] **Step 3:** run the test → pass. **Step 4: Commit** `auth_events: an append-only ledger of sign-in events`.

---

### Task 3: Sessions — id, method, absolute lifetime, revocation; the address budget

**Files:** modify `claimstone/control.py` (`Session`, `Sessions`, `LoginBudget` use, constants, `make_server`); create `tests/test_control_accounts.py` (session part).

- [ ] **Step 1: Failing tests** (unit level, a fake clock — mirror how `tests/test_control.py` tests `Sessions`; find it with `grep -n "Sessions(" tests/test_control.py`)

```python
from claimstone import control


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now


def test_sessions_have_ids_methods_and_an_absolute_lifetime():
    clock = Clock()
    sessions = control.Sessions(idle_seconds=100, absolute_seconds=1000, clock=clock)
    token, s = sessions.create("a", "Alpha", role="admin", method="password")
    assert s.session_id and s.session_id != token and s.method == "password" and s.role == "admin"
    for _ in range(12):                      # activity keeps it alive past the idle window...
        clock.now += 90
        if clock.now > 1000: break
        assert sessions.get(token) is not None
    clock.now = 1001                         # ...but never past the absolute one
    assert sessions.get(token) is None


def test_list_end_others_and_end_operator():
    sessions = control.Sessions()
    t1, _ = sessions.create("a", "Alpha", role="operator", method="password")
    t2, _ = sessions.create("a", "Alpha", role="operator", method="google")
    t3, _ = sessions.create("b", "Beta", role="operator", method="password")
    listed = sessions.list_for("a", current_token=t1)
    assert {x["method"] for x in listed} == {"password", "google"}
    assert [x["current"] for x in listed].count(True) == 1
    assert sessions.end_others("a", keep_token=t1) == 1
    assert sessions.get(t2) is None and sessions.get(t1) is not None and sessions.get(t3) is not None
    assert sessions.end_operator("a") == 1 and sessions.get(t1) is None


def test_must_change_password_can_be_cleared():
    sessions = control.Sessions()
    token, s = sessions.create("a", "Alpha", role="operator", method="password", must_change=True)
    assert s.must_change_password is True
    sessions.clear_must_change(token)
    assert sessions.get(token).must_change_password is False
```

- [ ] **Step 2: Implement.** Replace `Session` and `Sessions` in `control.py`:

```python
SESSION_ABSOLUTE_SECONDS = 7 * 24 * 60 * 60   # a session never outlives a week, activity or not
ADDRESS_FAILURE_LIMIT = 20                    # failed logins per remote address per window


@dataclass(frozen=True)
class Session:
    operator_id: str
    operator_name: str
    csrf_token: str
    session_id: str = ""
    role: str = "operator"
    method: str = "password"
    must_change_password: bool = False
    created_at: str = ""


class Sessions:
    """In-memory sessions: an inactivity timeout and an absolute lifetime. No token ever touches
    a disk. `session_id` is public (listed to its owner); the token is the secret."""

    def __init__(self, idle_seconds: int = SESSION_IDLE_SECONDS,
                 absolute_seconds: int = SESSION_ABSOLUTE_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._idle = float(idle_seconds)
        self._absolute = float(absolute_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._expires: dict[str, float] = {}
        self._dies: dict[str, float] = {}
        self._rows: dict[str, Session] = {}
        self._seen: dict[str, str] = {}

    def _drop(self, token: str) -> None:
        for table in (self._expires, self._dies, self._rows, self._seen):
            table.pop(token, None)

    def create(self, operator_id: str, operator_name: str, *, role: str = "operator",
               method: str = "password", must_change: bool = False) -> tuple[str, Session]:
        """(cookie token, session). A new token every time: no session fixation."""
        token = secrets.token_hex(32)
        session = Session(operator_id, operator_name, secrets.token_hex(32),
                          session_id=secrets.token_hex(8), role=role, method=method,
                          must_change_password=must_change, created_at=_now_iso())
        with self._lock:
            now = self._clock()
            for held in [t for t, until in self._expires.items()
                         if until <= now or self._dies[t] <= now]:
                self._drop(held)
            self._expires[token] = now + self._idle
            self._dies[token] = now + self._absolute
            self._rows[token] = session
            self._seen[token] = session.created_at
        return token, session

    def get(self, token: str) -> Session | None:
        with self._lock:
            until = self._expires.get(token)
            if until is None:
                return None
            now = self._clock()
            if now > until or now > self._dies[token]:
                self._drop(token)
                return None
            self._expires[token] = now + self._idle   # activity refreshes the idle window only
            self._seen[token] = _now_iso()
            return self._rows[token]

    def end(self, token: str) -> None:
        with self._lock:
            self._drop(token)

    def clear_must_change(self, token: str) -> None:
        with self._lock:
            if token in self._rows:
                self._rows[token] = replace(self._rows[token], must_change_password=False)

    def list_for(self, operator_id: str, current_token: str | None) -> list[dict[str, Any]]:
        with self._lock:
            return [{"session_id": s.session_id, "created_at": s.created_at,
                     "last_seen": self._seen.get(t, s.created_at), "method": s.method,
                     "current": t == current_token}
                    for t, s in self._rows.items() if s.operator_id == operator_id]

    def end_others(self, operator_id: str, keep_token: str | None) -> int:
        return self._end_where(operator_id, keep_token)

    def end_operator(self, operator_id: str) -> int:
        return self._end_where(operator_id, None)

    def _end_where(self, operator_id: str, keep: str | None) -> int:
        with self._lock:
            doomed = [t for t, s in self._rows.items() if s.operator_id == operator_id and t != keep]
            for token in doomed:
                self._drop(token)
            return len(doomed)
```
Add `from dataclasses import dataclass, replace`. In `make_server` add `"address_budget": LoginBudget(limit=ADDRESS_FAILURE_LIMIT),` next to `login_budget`, and declare `address_budget: LoginBudget` on `_Handler`.

- [ ] **Step 3:** `.venv/bin/pytest -q tests/test_control_accounts.py tests/test_control.py` pass. **Step 4: Commit** `control: sessions get an id, a method, an absolute lifetime and revocation`.

---

### Task 4: Login hardening, session options, account routes

**Files:** modify `claimstone/control.py`; create `claimstone/account_service.py`; extend `tests/test_control_accounts.py`.

- [ ] **Step 1: Failing tests** — add to `tests/test_control_accounts.py` (reuse the helpers by importing them: `from tests.test_control import _served, _request, _login, _cookie` is **not** possible if `tests` is not a package — copy the four helpers (`_served`, `_request`, `_login`, `_cookie`) into a new `tests/control_helpers.py` and make both test modules import from it; `tests/test_control.py` keeps working by `from control_helpers import …` only if pytest's rootdir puts `tests/` on `sys.path` — check with the other `test_control_*.py` files, which already share helpers, and copy their import style).

```python
import pytest
from claimstone import operators, auth_events

PW = "correct horse battery"


@pytest.fixture()
def state(tmp_path):
    d = tmp_path / "state"
    operators.add_operator(d, "adm", "Admin", PW, email="adm@example.org")
    operators.add_operator(d, "ann", "Ann", PW, email="ann@example.org")
    return d


def _signed(base, who="adm"):
    status, headers, body = _login(base, who, PW)
    assert status == 200, body
    return {"Cookie": _cookie(headers), "Origin": base, "X-CSRF-Token": body["csrf_token"]}, body


def test_login_answers_role_and_must_change(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        _headers, body = _signed(base)
        assert body["operator"] == {"id": "adm", "name": "Admin", "role": "admin",
                                    "must_change_password": False}


def test_a_new_token_at_every_login(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        assert _cookie(_login(base, "adm", PW)[1]) != _cookie(_login(base, "adm", PW)[1])


def test_the_address_budget_blocks_many_ids(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        for n in range(20):
            assert _login(base, f"nobody{n}", "wrong wrong wrong")[0] == 401
        assert _login(base, "adm", PW)[0] == 429


def test_login_events_are_recorded_without_the_password(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        _login(base, "adm", "wrong wrong wrong"); _login(base, "adm", PW)
    text = (state / "auth_events.jsonl").read_text()
    assert "login_failed" in text and "login_ok" in text and "wrong wrong" not in text and PW not in text


def test_session_options_is_public_and_says_google_is_off_by_default(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        assert _request(f"{base}/control/v1/session/options") [2] == {"google": False}


def test_change_password_ends_other_sessions_and_keeps_this_one(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        mine, _ = _signed(base)
        other, _ = _signed(base)
        status, _, body = _request(f"{base}/control/v1/account/password", "POST",
                                   {"current": PW, "new": "a brand new password"}, headers=mine)
        assert status == 200 and body == {"changed": True}
        assert _request(f"{base}/control/v1/session", headers=mine)[0] == 200
        assert _request(f"{base}/control/v1/session", headers=other)[0] == 401
        assert _login(base, "adm", PW)[0] == 401
        assert _login(base, "adm", "a brand new password")[0] == 200


def test_change_password_refuses_wrong_current_and_weak_new(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        mine, _ = _signed(base)
        url = f"{base}/control/v1/account/password"
        assert _request(url, "POST", {"current": "nope nope nope!", "new": "a brand new password"}, headers=mine)[0] == 403
        assert _request(url, "POST", {"current": PW, "new": "short"}, headers=mine)[0] == 422


def test_sessions_listing_and_end_others(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        mine, _ = _signed(base); other, _ = _signed(base)
        listed = _request(f"{base}/control/v1/account/sessions", headers=mine)[2]["sessions"]
        assert len(listed) == 2 and [s["current"] for s in listed].count(True) == 1
        assert "token" not in json.dumps(listed)
        assert _request(f"{base}/control/v1/account/sessions/end-others", "POST", {}, headers=mine)[2] == {"ended": 1}
        assert _request(f"{base}/control/v1/session", headers=other)[0] == 401


def test_account_read_shows_email_and_link_state(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        mine, _ = _signed(base)
        body = _request(f"{base}/control/v1/account", headers=mine)[2]
        assert body["operator"]["email"] == "adm@example.org" and body["operator"]["google_linked"] is False
```
Run → FAIL.

- [ ] **Step 2: `account_service.py`** — the rules, no HTTP:

```python
"""What an account or people route does once it is allowed to: the ledger calls and the
session revocations that must go with them. HTTP, cookies and the envelope stay in control.py."""

from __future__ import annotations

import pathlib
from typing import Any

from claimstone import auth_events, operators


class AccountError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def public(person: dict[str, Any]) -> dict[str, Any]:
    """A person as the portal may see them: never a salt, a hash or a subject."""
    return {"id": person["id"], "name": person["name"], "role": person["role"],
            "email": person["email"], "enabled": person["enabled"],
            "google_linked": bool(person["google_sub"])}


def _refuse(exc: operators.OperatorError) -> AccountError:
    return AccountError(422, "VALIDATION", str(exc))


def change_own_password(state: pathlib.Path, operator_id: str, current: object, new: object) -> None:
    row = operators.load(state).get(operator_id)
    if row is None or not isinstance(current, str) or not operators.verify(row, current):
        raise AccountError(403, "REAUTH", "the current password is required, and it did not match")
    try:
        operators.set_password(state, operator_id, new, by=operator_id)
    except operators.OperatorError as exc:
        raise _refuse(exc) from None
    auth_events.record(state, "password_changed", id=operator_id, by=operator_id)


def create_person(state: pathlib.Path, actor: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        operators.add_operator(state, str(body.get("id") or ""), str(body.get("name") or ""),
                               body.get("temporary_password"), role=body.get("role") or "operator",
                               email=body.get("email"), must_change=True, by=actor)
    except operators.OperatorError as exc:
        raise _refuse(exc) from None
    auth_events.record(state, "person_created", id=body.get("id"), by=actor)
    return public(operators.people(state)[body["id"]])


def apply_to_person(state: pathlib.Path, actor: str, person_id: str, action: str,
                    body: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """(person, sessions_must_end). `action` is password | disable | enable | email | role."""
    try:
        if action == "password":
            operators.set_password(state, person_id, body.get("new_password"), by=actor, must_change=True)
            auth_events.record(state, "password_set_by_admin", id=person_id, by=actor)
            ends = True
        elif action == "disable":
            operators.disable_operator(state, person_id, by=actor)
            auth_events.record(state, "person_disabled", id=person_id, by=actor)
            ends = True
        elif action == "enable":
            operators.enable_operator(state, person_id, by=actor)
            auth_events.record(state, "person_enabled", id=person_id, by=actor)
            ends = False
        elif action == "email":
            operators.set_email(state, person_id, body.get("email"), by=actor)
            auth_events.record(state, "person_email_set", id=person_id, by=actor)
            ends = False
        elif action == "role":
            operators.set_role(state, person_id, str(body.get("role") or ""), by=actor)
            auth_events.record(state, "person_role_set", id=person_id, by=actor)
            ends = False
        else:  # the route table makes this unreachable
            raise AccountError(404, "NOT_FOUND", "no such action")
    except operators.OperatorError as exc:
        if str(exc).startswith("unknown operator"):
            raise AccountError(404, "NOT_FOUND", str(exc)) from None
        raise _refuse(exc) from None
    return public(operators.people(state)[person_id]), ends
```

- [ ] **Step 3: Handlers and routes in `control.py`.** Add to `_Handler`: `address_budget: LoginBudget`, and a `_remote()` helper (`return self.client_address[0]`). Modify `_session_create`:

```python
        remote = self._remote()
        if self.address_budget.blocked(remote) or self.login_budget.blocked(operator_id):
            auth_events.record(self.state_dir, "login_blocked", id=operator_id, method="password", remote=remote)
            raise ControlError(429, "RATE_LIMITED", "too many failed logins; wait 15 minutes")
        row = operators.load(self.state_dir).get(operator_id)
        verified = operators.verify(row if row is not None else operators.DUMMY_ROW, password)
        if row is None or not verified:
            self.login_budget.record_failure(operator_id)
            self.address_budget.record_failure(remote)
            auth_events.record(self.state_dir, "login_failed", id=operator_id, method="password", remote=remote)
            raise ControlError(401, "UNAUTHORIZED", BAD_LOGIN_TEXT)
        token, session = self.sessions.create(str(row["id"]), str(row.get("name") or ""),
                                              role=row["role"], method="password",
                                              must_change=bool(row["must_change_password"]))
        auth_events.record(self.state_dir, "login_ok", id=session.operator_id, method="password", remote=remote)
        self._json({"operator": _operator_view(session), "csrf_token": session.csrf_token},
                   cookies=(self._session_cookie(token),))
```
with, module level: `def _operator_view(session): return {"id": session.operator_id, "name": session.operator_name, "role": session.role, "must_change_password": session.must_change_password}`; `_session_read` uses it too. Add `from claimstone import auth_events, account_service` to the import list.

Public `GET /session/options` → `{"google": bool(self.google)}` where `google` is a handler attribute set in `make_server` (None until Task 7). Route: `Route("GET", ("session", "options"), "_session_options", public=True)`. Because `_match` iterates in order and `("session",)` has a different length, no clash.

Enforce `must_change_password` in `_require_session`: it cannot know the route, so do it in `do_GET`/`do_POST` after `_match`: add

```python
    ALLOWED_WHILE_CHANGING = frozenset({"_session_read", "_session_end", "_account_password",
                                        "_session_options", "_account_read"})

    def _guard_change_required(self, route: Route) -> None:
        if route.public or route.handler in self.ALLOWED_WHILE_CHANGING:
            return
        if self._require_session().must_change_password:
            raise ControlError(403, "PASSWORD_CHANGE_REQUIRED", "set a new password first")
```
and call it right after `_require_session()` in both `do_GET` and `do_POST` (non-public branch).

Handlers (module level, attached with the same `setattr` loop as the others):

```python
def _reauth(self: _Handler, session: Session, password: object) -> None:
    """The password again, on the login's own budget: no side door for guessing."""
    if self.login_budget.blocked(session.operator_id):
        raise ControlError(429, "RATE_LIMITED", "too many failed attempts; wait 15 minutes")
    row = operators.load(self.state_dir).get(session.operator_id)
    if not isinstance(password, str) or row is None or not operators.verify(row, password):
        self.login_budget.record_failure(session.operator_id)
        auth_events.record(self.state_dir, "reauth_failed", id=session.operator_id, remote=self._remote())
        raise ControlError(403, "REAUTH", "the password is required again, and it did not match")


def _require_admin(self: _Handler) -> Session:
    session = self._require_session()
    row = operators.load(self.state_dir).get(session.operator_id)
    if row is None or row["role"] != "admin":
        raise ControlError(403, "FORBIDDEN", "this needs an admin")
    return session


def _account_call(function: Callable[..., Any], *args: Any) -> Any:
    try:
        return function(*args)
    except account_service.AccountError as exc:
        raise ControlError(exc.status, exc.code, exc.message) from None


def _account_read(self, params, query, body):
    session = self._require_session()
    person = operators.load(self.state_dir)[session.operator_id]
    return {"operator": {**_operator_view(session), "email": person["email"],
                         "google_linked": bool(person["google_sub"])}}, 200


def _account_password(self, params, query, body):
    self._only_keys(body, frozenset({"current", "new"}))
    session = self._require_session()
    _account_call(account_service.change_own_password, self.state_dir, session.operator_id,
                  body.get("current"), body.get("new"))
    self.sessions.end_others(session.operator_id, self._session_token())
    self.sessions.clear_must_change(self._session_token())
    return {"changed": True}, 200


def _account_sessions(self, params, query, body):
    session = self._require_session()
    return {"sessions": self.sessions.list_for(session.operator_id, self._session_token())}, 200


def _account_end_others(self, params, query, body):
    self._only_keys(body, frozenset())
    session = self._require_session()
    n = self.sessions.end_others(session.operator_id, self._session_token())
    auth_events.record(self.state_dir, "sessions_revoked", id=session.operator_id, detail=f"{n}")
    return {"ended": n}, 200
```
Routes: `GET account`, `POST account/password`, `GET account/sessions`, `POST account/sessions/end-others`. (The Google unlink and `/people` routes come in Tasks 5 and 7.)

- [ ] **Step 4:** run `tests/test_control_accounts.py tests/test_control.py` and the anonymous sweep → pass. Fix `tests/test_control.py` assertions on the login body shape if any fail (the operator object gained `role` and `must_change_password`).
- [ ] **Step 5: Commit** `control: hardened login, session options, account routes`.

---

### Task 5: People routes (admin) and revocation on disable

**Files:** modify `claimstone/control.py`; extend `tests/test_control_accounts.py`.

- [ ] **Step 1: Failing tests**

```python
def test_people_listing_is_admin_only_and_exposes_no_secrets(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base); ann, _ = _signed(base, "ann")
        assert _request(f"{base}/control/v1/people", headers=ann)[0] == 403
        people = _request(f"{base}/control/v1/people", headers=adm)[2]["people"]
        assert {p["id"] for p in people} == {"adm", "ann"}
        text = json.dumps(people)
        assert "hash" not in text and "salt" not in text and "sub" not in text


def test_admin_creates_a_person_who_must_change_the_temporary_password(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base)
        status, _, body = _request(f"{base}/control/v1/people", "POST", {
            "password": PW, "id": "bob", "name": "Bob", "email": "bob@example.org",
            "role": "operator", "temporary_password": "temporary secret 1"}, headers=adm)
        assert status == 201 and body["person"]["id"] == "bob"
        bob, login = _signed_as(base, "bob", "temporary secret 1")
        assert login["operator"]["must_change_password"] is True
        assert _request(f"{base}/control/v1/today", headers=bob)[2]["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
        assert _request(f"{base}/control/v1/account/password", "POST",
                        {"current": "temporary secret 1", "new": "my own long password"}, headers=bob)[0] == 200
        assert _request(f"{base}/control/v1/today", headers=bob)[0] == 200


def test_admin_actions_need_the_admins_password_again(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base)
        status, _, body = _request(f"{base}/control/v1/people/ann/disable", "POST",
                                   {"password": "not my password!"}, headers=adm)
        assert status == 403 and body["error"]["code"] == "REAUTH"


def test_disabling_a_person_ends_their_sessions_at_once(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base); ann, _ = _signed(base, "ann")
        assert _request(f"{base}/control/v1/people/ann/disable", "POST", {"password": PW}, headers=adm)[0] == 200
        assert _request(f"{base}/control/v1/session", headers=ann)[0] == 401
        assert _login(base, "ann", PW)[0] == 401
        assert _request(f"{base}/control/v1/people/ann/enable", "POST", {"password": PW}, headers=adm)[0] == 200
        assert _login(base, "ann", PW)[0] == 200


def test_the_last_admin_cannot_be_disabled_through_the_portal(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base)
        status, _, body = _request(f"{base}/control/v1/people/adm/disable", "POST", {"password": PW}, headers=adm)
        assert status == 422 and "last admin" in body["error"]["message"]


def test_an_admin_set_password_ends_the_persons_sessions_and_demands_a_change(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base); ann, _ = _signed(base, "ann")
        assert _request(f"{base}/control/v1/people/ann/password", "POST",
                        {"password": PW, "new_password": "temporary secret 2"}, headers=adm)[0] == 200
        assert _request(f"{base}/control/v1/session", headers=ann)[0] == 401
        assert _login(base, "ann", "temporary secret 2")[2]["operator"]["must_change_password"] is True
```
(`_signed_as(base, id, password)` is `_signed` generalised: add a `password` parameter to `_signed`.) Run → FAIL.

- [ ] **Step 2: Handlers**

```python
def _people_list(self, params, query, body):
    _require_admin(self)
    return {"people": [account_service.public(p) for p in operators.people(self.state_dir).values()]}, 200


def _people_create(self, params, query, body):
    self._only_keys(body, frozenset({"password", "id", "name", "email", "role", "temporary_password"}))
    session = _require_admin(self)
    _reauth(self, session, body.get("password"))
    person = _account_call(account_service.create_person, self.state_dir, session.operator_id, body)
    return {"person": person}, 201


def _people_act(action: str, keys: frozenset[str]):
    def handler(self, params, query, body):
        self._only_keys(body, frozenset({"password"}) | keys)
        session = _require_admin(self)
        _reauth(self, session, body.get("password"))
        person, ends = _account_call(account_service.apply_to_person, self.state_dir,
                                     session.operator_id, params["person_id"], action, body)
        if ends:
            self.sessions.end_operator(params["person_id"])
        return ({"changed": True} if action == "password" else {"person": person}), 200
    return handler
```
Routes: `GET ("people",)`, `POST ("people",)`, and `POST ("people","{person_id}", "password"|"disable"|"enable"|"email"|"role")` each with handler `_people_password`, `_people_disable`, `_people_enable`, `_people_email`, `_people_role`; attach with `setattr(_Handler, name, _people_act(action, keys))` where keys = `{"new_password"}` for password, `{"email"}`, `{"role"}`, `frozenset()` otherwise. Note the admin's own `password` key is also in `_only_keys`.

- [ ] **Step 3:** tests pass; run `tests/test_control.py` (anonymous sweep includes the new POST routes). **Step 4: Commit** `control: people routes for admins`.

---

### Task 6: Full-suite checkpoint and the GET sweep

**Files:** extend `tests/test_control.py`.

- [ ] **Step 1:** Add next to `test_every_post_route_refuses_an_anonymous_request` a twin for GET routes:

```python
def test_every_non_public_get_route_refuses_an_anonymous_request(tmp_path, state):
    with _served(tmp_path, state) as (_httpd, base):
        for route in control.ROUTES:
            if route.method != "GET" or route.public:
                continue
            status, headers, body = _request(base + _path(route))
            assert status == 401, (route, status, body)
```
- [ ] **Step 2:** `.venv/bin/pytest -q` (full) → green; `.venv/bin/claimstone validate --all-projects` → OK.
- [ ] **Step 3: Commit** `control: an anonymous GET sweep over the route registry`.

---

### Task 7: Google sign-in

**Files:** create `claimstone/google_login.py`, `tests/test_google_login.py`; modify `claimstone/control.py` (redirect helper, flows store, routes, `make_server`), `pyproject.toml`.

Use the exact Authlib calls recorded in the Task 0 note wherever they differ from the code below.

- [ ] **Step 1: `pyproject.toml`** — add under `[project]`: `optional-dependencies = { login = ["authlib>=1.3", "cryptography>=42"] }` and `.[dev]`-style test environments must install it (`.venv/bin/pip install -e ".[login]"`).

- [ ] **Step 2: Failing tests** — `tests/test_google_login.py`. The fake provider signs ID tokens with a generated RSA key and is injected through the same seam production uses:

```python
"""Google sign-in, offline: a local key signs the tokens, the provider is a seam (no network)."""

from __future__ import annotations

import time

import pytest

pytest.importorskip("authlib")
from authlib.jose import JsonWebKey, jwt  # noqa: E402

from claimstone import google_login  # noqa: E402

CLIENT = "client-id"


class FakeProvider:
    authorization_endpoint = "https://accounts.example/auth"
    issuer = "https://accounts.google.com"

    def __init__(self):
        self.key = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "k1"})
        self.claims: dict = {}

    def jwks(self):
        return {"keys": [self.key.as_dict(is_private=False)]}

    def mint(self, nonce, **over):
        claims = {"iss": self.issuer, "aud": CLIENT, "sub": "sub-1", "email": "ann@example.org",
                  "email_verified": True, "exp": int(time.time()) + 300, "nonce": nonce, **over}
        return jwt.encode({"alg": "RS256", "kid": "k1"}, claims, self.key).decode()

    def exchange(self, code, verifier, redirect_uri):
        return {"id_token": self.claims["token"]}


@pytest.fixture()
def flow():
    provider = FakeProvider()
    client = google_login.GoogleClient(CLIENT, "secret", "http://localhost:5173/control/v1/login/google/callback", provider)
    return client, provider


def _start(client):
    url, pending = client.start()
    assert "code_challenge_method=S256" in url and f"state={pending.state}" in url
    return pending


def test_a_good_token_yields_the_identity(flow):
    client, provider = flow
    pending = _start(client)
    provider.claims["token"] = provider.mint(pending.nonce)
    identity = client.finish("code", pending.state, pending)
    assert (identity.sub, identity.email) == ("sub-1", "ann@example.org")


@pytest.mark.parametrize("over,code", [
    ({"iss": "https://evil.example"}, "bad_token"),
    ({"aud": "someone-else"}, "bad_token"),
    ({"exp": 1}, "bad_token"),
    ({"nonce": "wrong"}, "bad_token"),
    ({"email_verified": False}, "email_unverified"),
    ({"email_verified": None}, "email_unverified"),
])
def test_bad_tokens_are_refused_with_a_fixed_code(flow, over, code):
    client, provider = flow
    pending = _start(client)
    provider.claims["token"] = provider.mint(pending.nonce, **over)
    with pytest.raises(google_login.GoogleError) as raised:
        client.finish("code", pending.state, pending)
    assert raised.value.code == code


def test_a_token_signed_by_another_key_is_refused(flow):
    client, provider = flow
    pending = _start(client)
    other = FakeProvider()
    provider.claims["token"] = other.mint(pending.nonce)
    with pytest.raises(google_login.GoogleError):
        client.finish("code", pending.state, pending)


def test_a_wrong_state_is_refused_before_anything_is_exchanged(flow):
    client, provider = flow
    pending = _start(client)
    provider.exchange = lambda *a: pytest.fail("must not exchange")
    with pytest.raises(google_login.GoogleError) as raised:
        client.finish("code", "not-the-state", pending)
    assert raised.value.code == "bad_state"
```
Run → FAIL (module missing).

- [ ] **Step 3: `claimstone/google_login.py`**

```python
"""Google sign-in: the one place Authlib is imported (design 2026-10-12, D7's boundary).

`GoogleClient` knows the protocol; `Provider` is the seam to Google (endpoints, key set, code
exchange) so tests sign tokens locally and nothing here reaches the network from a test. The
module imports Authlib at call time, so an install without the `login` extra still starts: the
control server simply reports Google as off.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

import requests

DISCOVERY = "https://accounts.google.com/.well-known/openid-configuration"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
TIMEOUT = 10
USER_AGENT = "claimstone-control (login)"


class GoogleError(Exception):
    """A refused sign-in. `code` is a short fixed string for the event ledger; the browser never
    sees it."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Pending:
    state: str
    nonce: str
    verifier: str


@dataclass(frozen=True)
class Identity:
    sub: str
    email: str


class Provider:
    """Google, for real: endpoints from the discovery document, keys fetched when needed."""

    def __init__(self) -> None:
        self._doc: dict[str, Any] | None = None

    def _discovery(self) -> dict[str, Any]:
        if self._doc is None:
            response = requests.get(DISCOVERY, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            self._doc = response.json()
        return self._doc

    @property
    def authorization_endpoint(self) -> str:
        return str(self._discovery()["authorization_endpoint"])

    def jwks(self) -> dict[str, Any]:
        response = requests.get(self._discovery()["jwks_uri"], timeout=TIMEOUT,
                                headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        return response.json()

    def exchange(self, code: str, verifier: str, redirect_uri: str, *, client_id: str,
                 client_secret: str) -> dict[str, Any]:
        response = requests.post(self._discovery()["token_endpoint"], timeout=TIMEOUT,
                                 headers={"User-Agent": USER_AGENT}, data={
                                     "grant_type": "authorization_code", "code": code,
                                     "redirect_uri": redirect_uri, "client_id": client_id,
                                     "client_secret": client_secret, "code_verifier": verifier})
        response.raise_for_status()
        return response.json()


class GoogleClient:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str,
                 provider: Any = None) -> None:
        self.client_id, self._secret, self.redirect_uri = client_id, client_secret, redirect_uri
        self.provider = provider or Provider()

    def start(self) -> tuple[str, Pending]:
        from authlib.integrations.requests_client import OAuth2Session
        pending = Pending(secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(64))
        session = OAuth2Session(self.client_id, self._secret, scope="openid email profile",
                                redirect_uri=self.redirect_uri, code_challenge_method="S256")
        url, _state = session.create_authorization_url(
            self.provider.authorization_endpoint, state=pending.state, nonce=pending.nonce,
            code_verifier=pending.verifier, prompt="select_account")
        return url, pending

    def finish(self, code: str, state: str, pending: Pending) -> Identity:
        """Exchange the code and verify the ID token completely. Every refusal is a GoogleError
        with a fixed code; nothing about the token is echoed."""
        from authlib.jose import JsonWebKey, jwt
        if not state or not secrets.compare_digest(state, pending.state):
            raise GoogleError("bad_state")
        if not code:
            raise GoogleError("no_code")
        try:
            exchanged = (self.provider.exchange(code, pending.verifier, self.redirect_uri,
                                                client_id=self.client_id, client_secret=self._secret)
                         if isinstance(self.provider, Provider)
                         else self.provider.exchange(code, pending.verifier, self.redirect_uri))
            raw = exchanged["id_token"]
            claims = jwt.decode(raw, JsonWebKey.import_key_set(self.provider.jwks()), claims_options={
                "iss": {"essential": True, "values": list(ISSUERS)},
                "aud": {"essential": True, "value": self.client_id},
                "exp": {"essential": True},
                "nonce": {"essential": True, "value": pending.nonce}})
            claims.validate()
        except GoogleError:
            raise
        except Exception:  # noqa: BLE001 - one fixed refusal; the cause goes nowhere a browser reads
            raise GoogleError("bad_token") from None
        if claims.get("email_verified") is not True:
            raise GoogleError("email_unverified")
        sub, email = claims.get("sub"), claims.get("email")
        if not sub or not email:
            raise GoogleError("bad_token")
        return Identity(str(sub), str(email))


def from_environment(env: dict[str, str]) -> tuple[GoogleClient, str] | None:
    """The configured client and the public base URL, or None when Google is off (a key missing,
    or Authlib not installed)."""
    client_id = env.get("CLAIMSTONE_GOOGLE_CLIENT_ID", "").strip()
    secret = env.get("CLAIMSTONE_GOOGLE_CLIENT_SECRET", "").strip()
    public = env.get("CLAIMSTONE_PUBLIC_URL", "").strip().rstrip("/")
    if not (client_id and secret and public):
        return None
    try:
        import authlib  # noqa: F401
    except ImportError:
        return None
    return GoogleClient(client_id, secret, f"{public}/control/v1/login/google/callback"), public
```
Adjust `exchange`'s signature in `FakeProvider` accordingly (it takes three positional arguments — the code above passes keyword args only to the real `Provider`).

- [ ] **Step 4:** `.venv/bin/pytest -q tests/test_google_login.py` → pass.

- [ ] **Step 5: Routes and flow store — failing tests first** (in `tests/test_control_accounts.py`; `_served` gains an optional `google=` argument that is passed to `make_server(..., google=…)`, `google = (client, public_url)`):

```python
def test_google_off_means_no_button_and_no_flow(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        status, headers, _ = _request(f"{base}/control/v1/login/google")
        assert status == 302 and "error=google_unavailable" in headers["Location"]


def test_google_signs_in_a_linked_or_allowlisted_person(tmp_path, state, google):
    client, provider, public = google
    with _served(tmp_path, state, google=(client, public)) as (_h, base):
        assert _request(f"{base}/control/v1/session/options")[2] == {"google": True}
        cookie, pending = _begin(base, client)                     # follows /login/google
        provider.claims["token"] = provider.mint(pending.nonce)    # ann@example.org, sub-1
        status, headers, _ = _callback(base, cookie, pending.state)
        assert status == 302 and headers["Location"] == f"{public}/"
        assert "claimstone_control=" in headers["Set-Cookie"]
        assert operators.find_by_sub(state, "sub-1")["id"] == "ann"
        # the second time the subject alone is enough, even if the email changed upstream
        cookie, pending = _begin(base, client)
        provider.claims["token"] = provider.mint(pending.nonce, email="renamed@example.org")
        assert _callback(base, cookie, pending.state)[1]["Location"] == f"{public}/"


@pytest.mark.parametrize("over", [{"email": "stranger@example.org"}, {"email_verified": False}])
def test_google_denies_everyone_else_with_one_response(tmp_path, state, google, over):
    client, provider, public = google
    with _served(tmp_path, state, google=(client, public)) as (_h, base):
        cookie, pending = _begin(base, client)
        provider.claims["token"] = provider.mint(pending.nonce, **over)
        status, headers, _ = _callback(base, cookie, pending.state)
        assert status == 302 and headers["Location"] == f"{public}/login?error=google_denied"
        assert "claimstone_control=" not in headers.get("Set-Cookie", "")


def test_google_denies_a_disabled_person_and_a_replayed_callback(tmp_path, state, google):
    client, provider, public = google
    operators.disable_operator(state, "ann", by="cli")
    with _served(tmp_path, state, google=(client, public)) as (_h, base):
        cookie, pending = _begin(base, client)
        provider.claims["token"] = provider.mint(pending.nonce)
        assert "google_denied" in _callback(base, cookie, pending.state)[1]["Location"]
    operators.enable_operator(state, "ann", by="cli")
    with _served(tmp_path, state, google=(client, public)) as (_h, base):
        cookie, pending = _begin(base, client)
        provider.claims["token"] = provider.mint(pending.nonce)
        assert "claimstone_control" in _callback(base, cookie, pending.state)[1]["Set-Cookie"]
        assert "google_denied" in _callback(base, cookie, pending.state)[1]["Location"]   # one use only


def test_a_callback_without_the_flow_cookie_or_with_the_wrong_state_is_denied(tmp_path, state, google):
    client, provider, public = google
    with _served(tmp_path, state, google=(client, public)) as (_h, base):
        cookie, pending = _begin(base, client)
        provider.claims["token"] = provider.mint(pending.nonce)
        assert "google_denied" in _callback(base, None, pending.state)[1]["Location"]
        assert "google_denied" in _callback(base, cookie, "wrong")[1]["Location"]


def test_linking_from_the_account_page_and_unlinking_with_the_password(tmp_path, state, google):
    client, provider, public = google
    with _served(tmp_path, state, google=(client, public)) as (_h, base):
        ann, _ = _signed(base, "ann")
        cookie, pending = _begin(base, client, path="/control/v1/login/google/link", headers=ann)
        provider.claims["token"] = provider.mint(pending.nonce)
        assert _callback(base, cookie, pending.state)[1]["Location"] == f"{public}/account?google=linked"
        assert _request(f"{base}/control/v1/account", headers=ann)[2]["operator"]["google_linked"] is True
        bad = _request(f"{base}/control/v1/account/google/unlink", "POST", {"password": "not it at all!"}, headers=ann)
        assert bad[0] == 403
        assert _request(f"{base}/control/v1/account/google/unlink", "POST", {"password": PW}, headers=ann)[0] == 200
```
Fixture `google` builds `FakeProvider` + `GoogleClient` as in `tests/test_google_login.py` (move `FakeProvider` into `tests/google_fake.py`, imported by both). `_begin(base, client, path=..., headers=None)` does a GET with redirects disabled (urllib: use an opener whose `HTTPRedirectHandler.redirect_request` returns `None`), asserts 302, parses `claimstone_oauth=` out of `Set-Cookie`, and recovers `Pending` by reading the `state` and `nonce` from the `Location` query (`parse_qs`) — and the verifier is not needed by the fake. `_callback(base, cookie, state)` GETs `/control/v1/login/google/callback?code=c&state=<state>` with `Cookie: claimstone_oauth=<value>` when given. Run → FAIL.

- [ ] **Step 6: Implement in `control.py`**

Constants and store (module level):
```python
OAUTH_COOKIE = "claimstone_oauth"
OAUTH_FLOW_SECONDS = 10 * 60


class OAuthFlows:
    """In-memory, single-use sign-in flows. The cookie carries only a random id; state, nonce and
    verifier never leave the server."""

    def __init__(self, ttl: float = OAUTH_FLOW_SECONDS, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl, self._clock, self._lock = ttl, clock, threading.Lock()
        self._held: dict[str, tuple[float, Any, str | None]] = {}

    def begin(self, pending: Any, link_for: str | None) -> str:
        flow_id = secrets.token_urlsafe(32)
        with self._lock:
            now = self._clock()
            for k in [k for k, (until, _, _) in self._held.items() if until <= now]:
                self._held.pop(k)
            self._held[flow_id] = (now + self._ttl, pending, link_for)
        return flow_id

    def take(self, flow_id: str | None) -> tuple[Any, str | None] | None:
        """Pop: a flow answers once."""
        with self._lock:
            found = self._held.pop(flow_id, None) if flow_id else None
        if found is None or found[0] <= self._clock():
            return None
        return found[1], found[2]
```
`_Handler` gets `google: Any` (a `(client, public_url)` tuple or `None`) and `oauth_flows: OAuthFlows`; `make_server(..., google=None)` sets `"google": google if google is not None else google_login.from_environment(os.environ)`, `"oauth_flows": OAuthFlows()`. `_respond` gains `location: str | None = None` which sends `Location` and uses `Content-Length: 0` for a 302; add `_redirect(self, location, cookies=())` calling `_respond(b"", 302, "text/plain", cookies, location=location)`.

Cookie helper:
```python
    def _oauth_cookie(self, value: str = "", *, expire: bool = False) -> str:
        parts = [f"{OAUTH_COOKIE}={'' if expire else value}", "Path=/control/v1/login",
                 "HttpOnly", "SameSite=Lax", f"Max-Age={0 if expire else OAUTH_FLOW_SECONDS}"]
        if self._secure_request():
            parts.append("Secure")
        return "; ".join(parts)

    def _oauth_cookie_value(self) -> str | None:
        cookie = SimpleCookie(); cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get(OAUTH_COOKIE)
        return morsel.value if morsel else None
```
Handlers:
```python
def _session_options(self, params, query, body):
    return {"google": self.google is not None}, 200


def _google_begin(self, link_for: str | None):
    if self.google is None:
        self._redirect("/login?error=google_unavailable")      # relative: the browser's own origin
        return None
    client, _public = self.google
    url, pending = client.start()
    flow_id = self.oauth_flows.begin(pending, link_for)
    self._redirect(url, cookies=(self._oauth_cookie(flow_id),))
    return None


def _google_login(self, params, query, body):
    return _google_begin(self, None)


def _google_link(self, params, query, body):
    session = self._require_session()
    return _google_begin(self, session.operator_id)


def _google_callback(self, params, query, body):
    remote = self._remote()
    client, public = self.google if self.google is not None else (None, "")
    query = urllib.parse.parse_qs(urlparse(self.path).query)
    code = (query.get("code") or [""])[0]
    state = (query.get("state") or [""])[0]
    taken = self.oauth_flows.take(self._oauth_cookie_value())
    expire = (self._oauth_cookie(expire=True),)
    link_for = taken[1] if taken else None
    where_denied = f"{public}/account?google=denied" if link_for else f"{public}/login?error=google_denied"

    def deny(detail: str):
        auth_events.record(self.state_dir, "google_denied", id=link_for, method="google",
                           remote=remote, detail=detail)
        self._redirect(where_denied, cookies=expire)
        return None

    if client is None or taken is None:
        return deny("no_flow")
    try:
        identity = client.finish(code, state, taken[0])
    except google_login.GoogleError as exc:
        return deny(exc.code)
    if link_for:
        try:
            operators.link_google(self.state_dir, link_for, sub=identity.sub, email=identity.email, by=link_for)
        except operators.OperatorError:
            return deny("link_refused")
        auth_events.record(self.state_dir, "google_linked", id=link_for, method="google", remote=remote)
        self._redirect(f"{public}/account?google=linked", cookies=expire)
        return None
    person = operators.find_by_sub(self.state_dir, identity.sub)
    if person is None:
        candidate = operators.find_by_email(self.state_dir, identity.email)
        if candidate is None or candidate["google_sub"]:
            return deny("not_allowed")
        try:
            operators.link_google(self.state_dir, candidate["id"], sub=identity.sub,
                                  email=identity.email, by=candidate["id"])
        except operators.OperatorError:
            return deny("link_refused")
        person = operators.find_by_sub(self.state_dir, identity.sub)
    token, session = self.sessions.create(person["id"], person["name"], role=person["role"],
                                          method="google", must_change=False)
    auth_events.record(self.state_dir, "google_ok", id=person["id"], method="google", remote=remote)
    self._redirect(f"{public}/", cookies=(self._session_cookie(token),) + expire)
    return None
```
Routes: `GET ("session","options")` public; `GET ("login","google")` public; `GET ("login","google","link")` session; `GET ("login","google","callback")` public; `POST ("account","google","unlink")`:
```python
def _account_google_unlink(self, params, query, body):
    self._only_keys(body, frozenset({"password"}))
    session = self._require_session()
    _reauth(self, session, body.get("password"))
    try:
        operators.unlink_google(self.state_dir, session.operator_id, by=session.operator_id)
    except operators.OperatorError as exc:
        raise ControlError(422, "VALIDATION", str(exc)) from None
    auth_events.record(self.state_dir, "google_unlinked", id=session.operator_id)
    return {"unlinked": True}, 200
```
`do_GET` for a public route whose handler returns `None` already writes nothing more — correct for redirects. `_match` order: put `session/options` before nothing special; lengths differ from `session`.

Note on `find_by_email` + "no Google link yet" = rule 2 of the spec; an id already linked to another `sub` is denied (`not_allowed`).

- [ ] **Step 7:** `.venv/bin/pytest -q tests/test_google_login.py tests/test_control_accounts.py tests/test_control.py` → pass. **Step 8: Commit** `login: Google sign-in behind one module, with link and unlink`.

---

### Task 8: CLI and the security sweep

**Files:** modify `claimstone/cli.py`; create `tests/test_login_security_sweep.py`.

- [ ] **Step 1: CLI.** In `_operator` (`claimstone/cli.py:1368`) pass `by="cli"` and extend:

```python
        if args.operator_command == "add":
            password = getpass.getpass("password: ")
            if password != getpass.getpass("again: "):
                print("passwords do not match", file=sys.stderr); return 2
            row = operators.add_operator(directory, args.id, args.name, password,
                                         role=args.role, email=args.email, by="cli")
            print(f"operator recorded: {args.id} ({args.name}, {row['role']}) in {directory}/")
        elif args.operator_command == "disable":
            operators.disable_operator(directory, args.id, by="cli"); print(f"operator disabled: {args.id}")
        elif args.operator_command == "enable":
            operators.enable_operator(directory, args.id, by="cli"); print(f"operator enabled: {args.id}")
        elif args.operator_command == "set-password":
            password = getpass.getpass("new password: ")
            if password != getpass.getpass("again: "):
                print("passwords do not match", file=sys.stderr); return 2
            operators.set_password(directory, args.id, password, by="cli", must_change=args.must_change)
            print(f"password replaced: {args.id}")
        elif args.operator_command == "set-email":
            operators.set_email(directory, args.id, args.email, by="cli"); print(f"email set: {args.id}")
        elif args.operator_command == "set-role":
            operators.set_role(directory, args.id, args.role, by="cli"); print(f"role set: {args.id} {args.role}")
        elif args.operator_command == "list":
            for p in operators.people(directory).values():
                print(f"{p['id']}\t{p['name']}\t{p['role']}\t{'enabled' if p['enabled'] else 'disabled'}"
                      f"\t{p['email'] or '-'}\t{'google' if p['google_sub'] else '-'}")
```
Parser: `add` gains `--role {operator,admin}` (default none) and `--email`; add subparsers `enable ID`, `set-password ID [--must-change]`, `set-email ID EMAIL`, `set-role ID {operator,admin}`, `list`. Note a CLI password change does not end live sessions of the running server (separate process): print "sessions of a running control server end at their idle limit; restart it to end them now" in `set-password` and `disable`.

Tests (`tests/test_control.py` has `cli` imports: mirror how it drives `cli.main` for `operator add`, monkeypatching `getpass.getpass`): one test per new subcommand asserting the printed line and the ledger effect; `list` prints the roles.

- [ ] **Step 2: Security sweep** — `tests/test_login_security_sweep.py`:

```python
"""No secret in a ledger, a response or a log line (design 2026-10-12 §Security checks)."""
```
Drive one server through: login, wrong login, password change, admin create, Google sign-in (fake), link, unlink, disable. Collect every response body and header, the text of `operators.jsonl` and `auth_events.jsonl`, and the server's stderr (capture with `capsys`/`caplog`; `BaseHandler` logging goes to stderr — assert on it too). Assert none contains: any plaintext password used in the test, the session cookie token values, the CSRF tokens (except in the login/session response bodies that return them to their owner — exclude those two fields from the search), the Google client secret `"secret"` replaced by a long random one for this test, the fake `id_token` strings, or `"hash"`/`"salt"` in any response. Also assert the Google callback's response is identical (status, `Location`) for: unknown email, unverified email, disabled person, wrong state.

- [ ] **Step 3:** full suite `.venv/bin/pytest -q` and `.venv/bin/claimstone validate --all-projects` → green. **Step 4: Commit** `cli: operator enable, set-password, set-email, set-role, list; a no-secrets sweep`.

---

### Task 9: Deployment wiring and docs

**Files:** `compose.yaml`, `Dockerfile`, `.env.example` (if it exists: `ls -a`), `docs/contracts/control_api.md`, `docs/contracts/operators.md` (new).

- [ ] **Step 1:** In `compose.yaml`, service `control`, `environment:` add
```yaml
      CLAIMSTONE_GOOGLE_CLIENT_ID: ${CLAIMSTONE_GOOGLE_CLIENT_ID:-}
      CLAIMSTONE_GOOGLE_CLIENT_SECRET: ${CLAIMSTONE_GOOGLE_CLIENT_SECRET:-}
      CLAIMSTONE_PUBLIC_URL: ${CLAIMSTONE_PUBLIC_URL:-http://127.0.0.1:${CLAIMSTONE_PORTAL_PORT:-8788}}
```
Read the `Dockerfile` (`grep -n "pip install" Dockerfile`) and change the project install to `.[login]`. Add the three variables, empty, with a comment to `.env.example` if present. Rebuild is not part of this task.
- [ ] **Step 2:** `docs/contracts/control_api.md` §Sessions: replace the operator paragraph with a pointer to the new `docs/contracts/operators.md`, and add the routes of "API contract" above with their error codes (`FORBIDDEN`, `REAUTH`, `PASSWORD_CHANGE_REQUIRED`). `docs/contracts/operators.md`: the row kinds table, the rules (copy from the spec §Identity model), the `auth_events.jsonl` format, the configuration variables, how to create a Google client (Cloud Console → Credentials → OAuth client ID → Web application → authorized redirect URI exactly `${CLAIMSTONE_PUBLIC_URL}/control/v1/login/google/callback`), and "opening the portal beyond this computer" as explicitly **not** covered.
- [ ] **Step 3:** `.venv/bin/pytest -q tests/test_docs*.py` if such tests exist (`ls tests | grep -i doc`); full suite. **Step 4: Commit** `docs: operators contract, control API routes, deployment variables`.

---

### Task 10: The live run, and D128

This task needs the owner at the keyboard (a Google consent screen) and is **not** delegated to a subagent.

- [ ] **Step 1:** With the user: create the OAuth client (Web application, redirect URI per Task 9), put `CLAIMSTONE_GOOGLE_CLIENT_ID/SECRET` in `.env`, set `CLAIMSTONE_PUBLIC_URL=http://localhost:5173` or the portal URL actually used (per the Task 0 note), start the control server with `.[login]` installed.
- [ ] **Step 2:** Registers the user's email with `claimstone operator set-email <id> <address>`, press the Google button on the portal login (plan 2) or open `/control/v1/login/google` by hand; confirm: signed in; `operators.jsonl` has one `google_linked` row and no token; `auth_events.jsonl` has `google_ok`; a second sign-in works; an account not on the list is refused with the single message.
- [ ] **Step 3:** Add D128 to `docs/DESIGN_DECISIONS.md` (after D127), in the file's own format: the decision (append-only ledger extended; Google via Authlib behind `google_login.py`; loopback perimeter), **the measurement** (the live run of Step 2: what was shown, the Task 0 findings), what was rejected (SQLite for users, an external identity provider — with the reasons from the spec) and what is deliberately left open (opening the portal; the named-id lockout). Update `docs/superpowers/notes/2026-10-12-google-login-spike.md` "Live end-to-end run" line.
- [ ] **Step 4: Commit** `D128: operator login — password management and Google sign-in`. Push the branch only on the user's word.

---

## Self-review (done)

- **Spec coverage:** row kinds and rules → T1; events ledger → T2; session id/method/absolute lifetime/revocation, address budget → T3–T4; password change, sessions list, end-others, account read → T4; people create/disable/enable/email/role/password, admin re-auth, last admin, session revocation → T5; Google flow, cookie, outcomes, link/unlink, off-by-default, optional extra → T7; CLI parity → T8; no-secret sweep and identical denial responses → T8; configuration and docs → T9; the three "to verify" items → T0 and T10; D128 → T10. The spec's "cookie `claimstone_oauth` with state, nonce, verifier" is implemented as a cookie carrying only an opaque id with the values server-side (T7): the same cookie, smaller trust surface; note this in D128.
- **Placeholders:** none; the one deliberate deferral is T0's exact Authlib calls, which the spike pins before T7.
- **Types:** `Sessions.create(..., role, method, must_change)`, `list_for(operator_id, current_token)`, `end_others(operator_id, keep_token)`, `end_operator`, `clear_must_change(token)`; `operators.*` signatures take `by=`; `account_service.apply_to_person → (person, ends)`; handler names match the route table in T4/T5/T7.
