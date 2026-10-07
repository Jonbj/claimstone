"""B10: export from the web — create and verify are explicit actions; copies only by licence."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager

import pytest

from claimstone import control, export, flows, operators
from tests.test_control import _cookie, _login, _request
from tests.test_portal_state import build_workspace


@pytest.fixture()
def ws(tmp_path):
    projects_dir, store_dir, project, store = build_workspace(tmp_path)
    state = tmp_path / "state"
    operators.add_operator(state, "op1", "Op One", "correct horse")
    flow_id = next(iter(flows.flows(store)))
    return {"projects": projects_dir, "store_dir": store_dir, "project": project,
            "store": store, "state": state, "flow_id": flow_id}


@contextmanager
def _served(ws):
    httpd = control.make_server(ws["projects"], ws["store_dir"], host="127.0.0.1", port=0,
                                state_dir=ws["state"])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        status, headers, body = _login(base)
        prefix = f"/control/v1/p/{ws['project'].name}/flows/{ws['flow_id']}/exports"
        yield base, prefix, {"Cookie": _cookie(headers), "Origin": base,
                             "X-CSRF-Token": body["csrf_token"]}
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _post(base, path, headers, payload=None):
    return _request(base + path, method="POST", payload=payload or {}, headers=headers)


def test_create_twice_is_one_export_and_names_the_operator(ws):
    with _served(ws) as (base, prefix, headers):
        status, _h, first = _post(base, prefix, headers)
        again = _post(base, prefix, headers)
    assert status == 201 and first["created_now"] is True and first["copies"] is None
    assert again[0] == 200 and again[2] == {**first, "created_now": False}
    [row] = list(ws["store"].read(export.EXPORTS_LEDGER))
    assert row["actor"] == "op1"
    manifest = json.loads((ws["store"].root / "exports" / first["export_id"] / "manifest.json")
                          .read_text(encoding="utf-8"))
    assert manifest["actor"] == "op1" and "copies" not in manifest
    # The CLI path computes the same identity: the web adds no field to it.
    directory, created = export.export(ws["project"], ws["store"], ws["flow_id"])
    assert directory.name == first["export_id"] and created is False


def test_verify_is_an_action_that_reports_tampering(ws):
    with _served(ws) as (base, prefix, headers):
        export_id = _post(base, prefix, headers)[2]["export_id"]
        ws["store"].append("candidates.jsonl", {"candidate_key": "later", "round": "r9",
                                                "discovered_at": "2026-10-07T10:00:00+00:00"})
        status, _h, held = _post(base, f"{prefix}/{export_id}/verify", headers)
        assert status == 200 and held == {"export_id": export_id, "holds": True, "problems": []}
        (ws["store"].root / "exports" / export_id / "report.md").write_text("edited\n")
        _s, _h, broken = _post(base, f"{prefix}/{export_id}/verify", headers)
        assert broken["holds"] is False and "OUTPUT_DIFFERS report.md" in broken["problems"]
        assert _post(base, f"{prefix}/{'0' * 64}/verify", headers)[0] == 404
        assert _post(base, f"{prefix}/not-an-id/verify", headers)[0] == 404


def test_copies_are_included_only_under_a_redistributable_licence(ws):
    store = ws["store"]
    for key, licence, payload in (("r1-a", "cc-by", b"%PDF-1.4 a" + b"x" * 100),
                                  ("r1-b", None, b"%PDF-1.4 b" + b"y" * 100)):
        held = store.latest_by("acquisitions.jsonl", "candidate_key")[key]
        digest, path = store.store_bytes(payload, ".pdf")
        store.append("acquisitions.jsonl", {**held, "sha256": digest, "stored_path": str(path),
                                            "licence": licence, "attempt_no": 2})
    with _served(ws) as (base, prefix, headers):
        status, _h, made = _post(base, prefix, headers, {"include_copies": True})
        assert status == 201
        copies = made["copies"]
        assert [c["candidate_key"] for c in copies["included"]] == ["r1-a"]
        assert copies["excluded"] == [{**copies["excluded"][0], "candidate_key": "r1-b",
                                       "reason": "licence unknown"}]
        directory = store.root / "exports" / made["export_id"]
        assert (directory / copies["included"][0]["file"]).exists()
        assert "stored_path" not in json.dumps(copies)  # no filesystem path leaves the server
        plain = _post(base, prefix, headers)[2]
        assert plain["export_id"] != made["export_id"]  # the option is part of the identity
        assert _post(base, f"{prefix}/{made['export_id']}/verify", headers)[2]["holds"] is True
        (directory / copies["included"][0]["file"]).write_bytes(b"swapped")
        problems = _post(base, f"{prefix}/{made['export_id']}/verify", headers)[2]["problems"]
        assert problems == [f"COPY_DIFFERS {copies['included'][0]['file']}"]


def test_the_option_is_a_boolean_and_routes_need_a_session(ws):
    with _served(ws) as (base, prefix, headers):
        assert _post(base, prefix, headers, {"include_copies": "yes"})[0] == 422
        assert _post(base, prefix, headers, {"include_pdfs": True})[0] == 400
        assert _request(base + prefix, method="POST", payload={},
                        headers={"Origin": base})[0] == 401
