#!/usr/bin/env python
"""Write `web/tests/fixtures/*.json`: deterministic snapshots of every `/api/v1` route
over the `build_workspace` fixture, for the frontend's vitest (spec §4.4).

The fixtures must be byte-stable, so the tool owns a fixed clock for everything the
workspace build or the server would stamp "now": flow rows (`created_at`, `created_by`),
profile rows (`built_at`), ledger mtimes (the `poll` and unscoped `activity` readings), and
the server's `started_at`. Environment values are scrubbed for the collection, so `admin`
reports presence booleans that depend on no machine's secrets and `meta`'s code identity
reads the tmp workspace, never a leftover variable. The workspace path inside command
strings is normalized to `<workspace>`; everything else is the payload exactly as served.

Run from the repository root:

    .venv/bin/python tools/build_portal_fixtures.py

`tests/test_portal_fixtures.py` regenerates in memory and compares, byte for byte.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import threading
from contextlib import contextmanager
from datetime import datetime
from tempfile import TemporaryDirectory

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from claimstone import api, flows  # noqa: E402
from tests.test_api import _get_json, _q02_sha, _routes  # noqa: E402
from tests.test_portal_state import build_workspace  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent
TARGET = REPO / "web" / "tests" / "fixtures"

# The fixtures' clock: every timestamp the build or the server would stamp "now" is pinned
# to this instant, so the committed files change only when meaning changes.
FIXED_STAMP = "2026-10-06T00:00:00+00:00"
FIXED_USER = "fixture"
WORKSPACE_TOKEN = "<workspace>"

# Names the collection must not see: credentials decide `admin`'s presence booleans,
# `CLAIMSTONE_CODE_REVISION` would decide `meta`'s code identity, and `CLAIMSTONE_ROOT`
# would move the instrument checker.
SCRUBBED_ENV = ("CLAIMSTONE_CONTACT_EMAIL", "OLLAMA_API_KEY", "OPENALEX_API_KEY",
                "CLAIMSTONE_CODE_REVISION", "CLAIMSTONE_ROOT")


@contextmanager
def _scrubbed_env():
    held = {name: os.environ.pop(name, None) for name in SCRUBBED_ENV}
    try:
        yield
    finally:
        os.environ.update({name: value for name, value in held.items() if value is not None})


def _pin_rows(path: pathlib.Path, fixes) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    for row in rows:
        fixes(row)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                   encoding="utf-8")


def _sanitize(store) -> None:
    """Pin what the build stamped "now": the flow and profile rows, then every mtime the
    `poll` and unscoped `activity` readings would otherwise read from the clock."""
    _pin_rows(store.path("flows.jsonl"),
              lambda row: row.update(created_at=FIXED_STAMP, created_by=FIXED_USER))
    _pin_rows(store.path("profiles.jsonl"), lambda row: row.update(built_at=FIXED_STAMP))
    stamp = datetime.fromisoformat(FIXED_STAMP).timestamp()
    for path in store.root.rglob("*"):
        if path.is_file():
            os.utime(path, (stamp, stamp))


def _normalize(value, workspace: str):
    if isinstance(value, dict):
        return {key: _normalize(item, workspace) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item, workspace) for item in value]
    if isinstance(value, str):
        return value.replace(workspace, WORKSPACE_TOKEN)
    return value


def _fixture_name(route: str) -> str:
    path, _, query = route.partition("?")
    parts = [part for part in path.split("/") if part]
    assert parts[:2] == ["api", "v1"], route
    if len(parts) >= 3 and parts[-1] == "profile-diff" and parts[-3] == "questions":
        # The question's own fixture is `Q02.json`; the diff must not become a `Q02/`
        # directory beside the file it extends.
        parts = parts[:-1]
        parts[-1] = f"{parts[-1]}.profile-diff"
    name = "/".join(parts[2:])
    if query:
        name += "." + query.replace("=", "-")
    return name + ".json"


def snapshot() -> dict[str, str]:
    """fixture relative path -> file text, deterministic across runs.

    The route list is `tests.test_api._routes` — the same §3.2 list tests A1 and A2 walk —
    so the fixtures cannot drift from the contract tests.
    """
    with TemporaryDirectory() as tmp:
        projects_dir, store_dir, _project, store = build_workspace(pathlib.Path(tmp))
        _sanitize(store)
        with _scrubbed_env():
            httpd = api.make_server(projects_dir, store_dir, host="127.0.0.1", port=0)
            httpd.RequestHandlerClass.started_at = FIXED_STAMP
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{httpd.server_address[1]}"
                flow_id = next(iter(flows.flows(store)))
                out: dict[str, str] = {}
                for route in _routes(flow_id, _q02_sha(store)):
                    status, _headers, payload = _get_json(base + route)
                    assert status == 200, route
                    body = _normalize(payload, str(projects_dir.resolve()))
                    out[_fixture_name(route)] = json.dumps(
                        body, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
                return out
            finally:
                httpd.shutdown()
                thread.join(timeout=5)


def main() -> int:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    files = snapshot()
    for name, text in sorted(files.items()):
        path = TARGET / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    total = sum(len(text.encode("utf-8")) for text in files.values())
    print(f"wrote {len(files)} fixture(s) under web/tests/fixtures/ ({total} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())