"""Administration actions the control server performs on request (spec B11).

Nothing here runs because a page was opened. A reachability check is one unpaid request to a
service whose address the configuration fixes; the operator chooses which service, never the
address. A credential is written to `.env` and never read back: the response names the variable,
and nothing returns its value. Both leave a row in `admin_checks.jsonl` in the state directory, so
who checked or replaced what, and when, is on record.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import tempfile
import time
import urllib.parse
from typing import Any, Callable

from claimstone import net, portal_state

ADMIN_CHECK_VERSION = 1

LEDGER = "admin_checks.jsonl"

TIMEOUT_SECONDS = 5
MAX_CREDENTIAL_CHARS = 4096


class AdminRefused(ValueError):
    """A request the administration rules refuse; the message is the reason."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def targets() -> dict[str, str]:
    """The services a check may reach, with the address the configuration gives each."""
    from claimstone.cli import grobid_url_default
    from claimstone.runners.llamacpp import ENDPOINT as LLAMACPP

    parts = urllib.parse.urlsplit(LLAMACPP)
    return {
        "llamacpp": f"{parts.scheme}://{parts.netloc}/health",
        # The model list: unpaid, and it proves the key is accepted without spending anything.
        "ollama-cloud": "https://ollama.com/api/tags",
        "grobid": grobid_url_default().rstrip("/") + "/api/isalive",
    }


def _append(state_dir: pathlib.Path, row: dict[str, Any]) -> None:
    state_dir = pathlib.Path(state_dir)
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(state_dir / LEDGER, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def rows(state_dir: pathlib.Path) -> list[dict[str, Any]]:
    path = pathlib.Path(state_dir) / LEDGER
    if not path.exists():
        return []
    data = path.read_bytes()
    data = data[: data.rfind(b"\n") + 1] if not data.endswith(b"\n") else data
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def _default_get(url: str, headers: dict[str, str], timeout: float) -> int:
    import requests

    return requests.get(url, headers=headers, timeout=timeout, allow_redirects=False).status_code


def check(state_dir: pathlib.Path, *, target: Any, actor: str,
          http_get: Callable[[str, dict[str, str], float], int] | None = None) -> dict[str, Any]:
    """One unpaid request to one configured service, recorded whatever its outcome."""
    known = targets()
    if target not in known:
        raise AdminRefused(f"target must be one of {', '.join(sorted(known))}")
    try:
        agent = net.USER_AGENT.format(contact=net.contact_email())
    except net.ContactNotConfigured as exc:
        raise AdminRefused(str(exc)) from None
    headers = {"User-Agent": agent}
    if target == "ollama-cloud" and os.environ.get("OLLAMA_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['OLLAMA_API_KEY']}"
    started = time.monotonic()
    status: int | None = None
    detail = ""
    try:
        status = (http_get or _default_get)(known[target], headers, TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - recorded by class, never swallowed (CLAUDE.md)
        detail = type(exc).__name__
    row = {"admin_check_version": ADMIN_CHECK_VERSION, "kind": "reachability", "target": target,
           "url": known[target], "ok": status is not None and 200 <= status < 300,
           "status": status, "detail": detail,
           "latency_ms": round((time.monotonic() - started) * 1000), "actor": actor,
           "recorded_at": _now()}
    _append(state_dir, row)
    return row


def latest_checks(state_dir: pathlib.Path) -> dict[str, dict[str, Any]]:
    return {str(row["target"]): row for row in rows(state_dir)
            if row.get("kind") == "reachability"}


def replace_credential(env_file: pathlib.Path, state_dir: pathlib.Path, *, name: Any, value: Any,
                       actor: str) -> dict[str, Any]:
    """Write one credential into `.env`, keeping every other line, owner-only, atomically. The
    value is never returned, logged or recorded: the ledger row names the variable and the actor."""
    if name not in portal_state.CREDENTIAL_NAMES:
        raise AdminRefused(f"name must be one of {', '.join(portal_state.CREDENTIAL_NAMES)}")
    if (not isinstance(value, str) or not value.strip() or len(value) > MAX_CREDENTIAL_CHARS
            or any(ch in value for ch in "\r\n\x00")):
        raise AdminRefused("value must be one line of text, at most 4096 characters")
    env_file = pathlib.Path(env_file)
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    written = [f"{name}={value}" if line.split("=", 1)[0].strip() == name else line
               for line in lines]
    if f"{name}={value}" not in written:
        written.append(f"{name}={value}")
    handle, temp = tempfile.mkstemp(dir=env_file.parent, prefix=".env.", suffix=".tmp")
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write("\n".join(written) + "\n")
        os.replace(temp, env_file)
    except BaseException:
        if os.path.exists(temp):
            os.unlink(temp)
        raise
    row = {"admin_check_version": ADMIN_CHECK_VERSION, "kind": "credential", "name": name,
           "actor": actor, "recorded_at": _now(),
           "note": "takes effect when the services that read .env restart"}
    _append(state_dir, row)
    return row
