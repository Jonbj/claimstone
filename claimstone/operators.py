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

import hashlib
import hmac
import json
import os
import pathlib
import secrets
from datetime import datetime, timezone
from typing import Any

OPERATOR_VERSION = 1

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
    if not operator_id.strip() or "\n" in operator_id or "\r" in operator_id:
        raise OperatorError("operator id must be non-empty text without line breaks")


def add_operator(directory: str | pathlib.Path, operator_id: str, name: str,
                 password: str, *, now: str | None = None) -> dict[str, Any]:
    """Append an enabling row. An id with any row already — enabled or disabled — is
    refused: re-enabling after a disable is a deliberate act this ledger does not
    silently perform."""
    _check_id(operator_id)
    if not name.strip():
        raise OperatorError("operator name must be non-empty")
    if not password:
        raise OperatorError("password must not be empty")
    directory = pathlib.Path(directory)
    if any(str(row.get("id")) == operator_id for row in _rows(directory)):
        raise OperatorError(f"operator already recorded: {operator_id}")
    salt = secrets.token_bytes(SALT_LENGTH)
    row = {
        "operator_version": OPERATOR_VERSION,
        "id": operator_id,
        "name": name,
        "scrypt": dict(SCRYPT),
        "salt": salt.hex(),
        "hash": _hash(password, salt, SCRYPT),
        "created_at": now or _now(),
    }
    _append(directory, row)
    return row


def disable_operator(directory: str | pathlib.Path, operator_id: str,
                     *, now: str | None = None) -> dict[str, Any]:
    """Append a disabling row. The latest row per id is the id's state."""
    _check_id(operator_id)
    directory = pathlib.Path(directory)
    rows = [row for row in _rows(directory) if str(row.get("id")) == operator_id]
    if not rows:
        raise OperatorError(f"unknown operator: {operator_id}")
    if rows[-1].get("disabled"):
        raise OperatorError(f"operator already disabled: {operator_id}")
    row = {
        "operator_version": OPERATOR_VERSION,
        "id": operator_id,
        "disabled": True,
        "disabled_at": now or _now(),
    }
    _append(directory, row)
    return row


def load(directory: str | pathlib.Path) -> dict[str, dict[str, Any]]:
    """The active enabling row per operator id: the ledger's last word on who may
    log in. A disable row removes the id; nothing re-adds it but `add_operator`."""
    active: dict[str, dict[str, Any]] = {}
    for row in _rows(pathlib.Path(directory)):
        operator_id = str(row.get("id"))
        if row.get("disabled"):
            active.pop(operator_id, None)
        elif "hash" in row:
            active[operator_id] = row
    return active


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
