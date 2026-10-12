"""The operators ledger — who may hold a control-API session (spec B4, D89).

`operators.jsonl` is installation-level, not per project: it lives in
`CLAIMSTONE_STATE_DIR` (default `.claimstone/`, gitignored) and is append-only like
every other ledger. Passwords are hashed with `hashlib.scrypt` (n=2^15, r=8, p=1) and
compared constant-time; the salt and the parameters travel inside the row, so
verification can never drift from what was recorded. No password, hash or salt is
printed, returned or logged by anything in this module — the CLI passes the password
in through `getpass`, and the control server only ever answers yes or no.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import pathlib
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

OPERATOR_VERSION = 2

LEDGER = "operators.jsonl"

# The spec's parameters (B4). `maxmem` exists because 128·r·n is exactly 32 MiB and
# OpenSSL's default ceiling sits under the row's own needs.
SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1}
KEY_LENGTH = 32
SALT_LENGTH = 16
MAXMEM = 64 * 1024 * 1024


class OperatorError(ValueError):
    """A refused operator command: the caller's error, printed as one sentence."""


def state_dir(explicit: str | pathlib.Path | None = None) -> pathlib.Path:
    """Where installation-level files live: the argument, the environment, or
    `.claimstone/` — never guessed beyond that."""
    if explicit is not None:
        return pathlib.Path(explicit)
    env = os.environ.get("CLAIMSTONE_STATE_DIR")
    return pathlib.Path(env) if env else pathlib.Path(".claimstone")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rows(directory: pathlib.Path) -> list[dict[str, Any]]:
    """Every complete row. A final line left half-written by an interrupted append is
    skipped, exactly as `Store.read` skips one: it was never accepted by any reader."""
    path = pathlib.Path(directory) / LEDGER
    if not path.exists():
        return []
    data = path.read_bytes()
    if not data.endswith(b"\n") and b"\n" in data:
        data = data[: data.rfind(b"\n") + 1]
    elif not data.endswith(b"\n"):
        data = b""
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def _append(directory: pathlib.Path, row: dict[str, Any]) -> None:
    """Owner-only: the ledger holds password hashes, which are offline-attackable."""
    path = pathlib.Path(directory) / LEDGER
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    os.chmod(path, 0o600)  # a file created earlier under a looser umask is tightened too
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _hash(password: str, salt: bytes, params: dict[str, int]) -> str:
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                            n=int(params["n"]), r=int(params["r"]), p=int(params["p"]),
                            maxmem=MAXMEM, dklen=KEY_LENGTH)
    return digest.hex()


def _check_id(operator_id: str) -> None:
    if (not operator_id.strip() or operator_id != operator_id.strip()
            or not operator_id.isprintable()):
        raise OperatorError("operator id must be non-empty printable text without padding or line breaks")


ROLES = ("operator", "admin")
PASSWORD_MIN, PASSWORD_MAX = 12, 256


def check_password(password: object, operator_id: str | None = None) -> str:
    """The one password rule. Length only: no composition rules, and an upper bound
    as hygiene (it keeps a request body sane), not as a cap on cost."""
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
    text = str(value).strip().casefold()
    if ("@" not in text or len(text) > 254
            or any(ch.isspace() or ord(ch) < 32 for ch in text)):
        raise OperatorError("email must look like an address")
    return text


@contextmanager
def _locked(directory: pathlib.Path):
    """One writer at a time across processes (the CLI and the control server share the file):
    every rule below reads then appends, and must not interleave with another writer."""
    directory = pathlib.Path(directory)
    created = not directory.exists()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if created:
        os.chmod(directory, 0o700)  # mkdir's mode is masked by the umask
    fd = os.open(directory / ".operators.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _fold(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Every person ever recorded, in their current state. Legacy rows (version 1) have no
    `kind`: a row with a hash is `created`, a row with `disabled` is `disabled`; a legacy
    `created` row has no role and reads as admin (only a shell could create one)."""
    people: dict[str, dict[str, Any]] = {}
    for row in rows:
        oid = str(row.get("id"))
        kind = row.get("kind")
        if not kind:  # legacy, version 1: only a hash makes a `created` row; anything else is noise
            kind = "disabled" if row.get("disabled") else ("created" if "hash" in row and "salt" in row else None)
        if kind is None:
            continue
        if kind == "created":
            if oid in people or "hash" not in row or "salt" not in row:
                continue  # an id is never reused (the first row wins); a row without a hash is noise
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


def add_operator(directory, operator_id: str, name: str, password: str, *,
                 role: str | None = None, email: str | None = None, must_change: bool = False,
                 by: str = "cli", now: str | None = None) -> dict[str, Any]:
    """Append a `created` row. An id with any row is refused for ever. With no `role`, while no
    active admin exists the new person is an admin; otherwise an operator."""
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
        stamp = now or _now()
        return _write(directory, "created", operator_id, by, stamp, name=name, role=role,
                      email=email, must_change_password=must_change, created_at=stamp,
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
        # `disabled: True` is what version-1 code reads: after a rollback it must still drop the id.
        return _write(directory, "disabled", operator_id, by, now, disabled=True)


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


# Verified against when the id is unknown, so a login costs one scrypt either way. No
# password hashes to this value: the salt and hash are fixed, not derived from any input.
DUMMY_ROW: dict[str, Any] = {"salt": "00" * SALT_LENGTH, "hash": "00" * KEY_LENGTH,
                             "scrypt": dict(SCRYPT)}


def verify(row: dict[str, Any], password: str) -> bool:
    """Constant-time password check against one enabling row."""
    try:
        salt = bytes.fromhex(str(row["salt"]))
        expected = str(row["hash"])
        candidate = _hash(password, salt, dict(row.get("scrypt") or SCRYPT))
    except (KeyError, ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)
