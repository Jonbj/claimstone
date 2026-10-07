"""B5: signing from the web, and the drafts that survive a changed profile.

Every refusal a signature can meet is the engine's own (`synthesize.adjudicate`), reached
through the control server with the operator the session authenticated. What the route adds
is the request rules, the literal attestation, the flow's binding check and idempotency.
"""

from __future__ import annotations

import json

import pytest

from claimstone import control, drafts, evidence, export, flows, operators, synthesize
from tests.test_control import _cookie, _login, _request
from tests.test_portal_state import build_workspace

RATIONALE = ("The evidence profile shows one verified result whose quote supports the "
             "question, read against the passage; the coverage is two of two sources.")


@pytest.fixture()
def workspace(tmp_path):
    projects_dir, store_dir, project, store = build_workspace(tmp_path)
    state = tmp_path / "state"
    operators.add_operator(state, "op1", "Op One", "correct horse")
    operators.add_operator(state, "op2", "Op Two", "battery staple")
    flow_id = next(iter(flows.flows(store)))
    question = next(q for q in project.questions if q.kind != "operational")
    return {"projects": projects_dir, "store_dir": store_dir, "project": project,
            "store": store, "state": state, "flow_id": flow_id, "qid": question.id}


class _Client:
    """A logged-in operator: cookie, CSRF token and the base URL."""

    def __init__(self, base: str, operator_id: str = "op1", password: str = "correct horse"):
        self.base = base
        status, headers, body = _login(base, operator_id, password)
        assert status == 200, body
        self.cookie = _cookie(headers)
        self.csrf = body["csrf_token"]

    def post(self, path: str, payload: dict, headers: dict | None = None):
        sent = {"Cookie": self.cookie, "Origin": self.base, "X-CSRF-Token": self.csrf}
        sent.update(headers or {})
        return _request(self.base + path, method="POST", payload=payload, headers=sent)

    def get(self, path: str):
        return _request(self.base + path, headers={"Cookie": self.cookie})


def _served(ws):
    from contextlib import contextmanager
    import threading

    @contextmanager
    def run():
        httpd = control.make_server(ws["projects"], ws["store_dir"], host="127.0.0.1",
                                    port=0, state_dir=ws["state"])
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}"
        finally:
            httpd.shutdown()
            thread.join(timeout=5)
    return run()


def _q(ws, qid: str | None = None, flow_id: str | None = None, project: str | None = None):
    return (f"/control/v1/p/{project or ws['project'].name}/flows/{flow_id or ws['flow_id']}"
            f"/q/{qid or ws['qid']}")


def _current(ws, qid: str | None = None) -> str:
    return synthesize.latest_profiles(ws["store"], round_name="r1")[qid or ws["qid"]][
        "profile_sha256"]


def _signature(ws, **overrides):
    payload = {"verdict": "UNANSWERED_IN_LITERATURE", "rationale": RATIONALE,
               "profile_sha256": _current(ws), "attest": True}
    payload.update(overrides)
    return payload


def _rows(ws):
    return list(ws["store"].read(synthesize.ADJUDICATIONS))


# --- signing ---------------------------------------------------------------------------------------


def test_a_portal_signature_names_the_session_operator(workspace):
    ws = workspace
    with _served(ws) as base:
        status, _h, body = _Client(base).post(_q(ws) + "/adjudicate", _signature(ws))
    assert status == 201, body
    row = _rows(ws)[-1]
    assert row["signer_auth"] == "portal-session"
    assert row["actor"] == "op1"
    assert row["adjudicated_by"] == "Op One"
    assert row["verdict"] == "UNANSWERED_IN_LITERATURE"
    assert row["profile_sha256"] == _current(ws)
    assert body["adjudication"] == row


def test_a_stale_hash_is_the_engines_refusal_and_writes_nothing(workspace):
    ws = workspace
    with _served(ws) as base:
        status, _h, body = _Client(base).post(_q(ws) + "/adjudicate",
                                              _signature(ws, profile_sha256="0" * 64))
    assert status == 409 and body["error"]["code"] == "STALE_PROFILE"
    assert _rows(ws) == []


def test_a_provisional_profile_cannot_be_signed(workspace):
    ws = workspace
    latest = dict(synthesize.latest_profiles(ws["store"], round_name="r1")[ws["qid"]])
    latest.update(provisional=True, blocking=["review still arriving"],
                  profile_sha256="a" * 64)
    ws["store"].append(synthesize.PROFILES, latest)
    with _served(ws) as base:
        status, _h, body = _Client(base).post(_q(ws) + "/adjudicate",
                                              _signature(ws, profile_sha256="a" * 64))
    assert status == 409 and body["error"]["code"] == "PROVISIONAL"
    assert _rows(ws) == []


def test_an_operational_question_receives_no_verdict(workspace):
    """The engine's refusal reaches the operator as 409 with its own sentence. The example
    project has no operational question, so the profile row the engine writes for one
    (state NOT_APPLICABLE) is appended directly; `test_adjudicate` covers the engine side."""
    ws = workspace
    profile = dict(synthesize.latest_profiles(ws["store"], round_name="r1")[ws["qid"]])
    profile.update(state=evidence.NOT_APPLICABLE, kind="operational")
    ws["store"].append(synthesize.PROFILES, profile)
    with _served(ws) as base:
        status, _h, body = _Client(base).post(_q(ws) + "/adjudicate", _signature(ws))
    assert status == 409 and body["error"]["code"] == "REFUSED"
    assert "receives no verdict" in body["error"]["message"]
    assert _rows(ws) == []


@pytest.mark.parametrize("overrides, fragment", [
    ({"rationale": "too short"}, "below the declared minimum"),
    ({"rationale": " " * 200 + "x"}, "below the declared minimum"),  # trimmed, not raw
    ({"attest": False}, "attest must be the literal true"),
    ({"attest": "true"}, "attest must be the literal true"),
    ({"verdict": None}, "verdict must be one of"),              # nothing is preselected
    ({"verdict": "NO_VERIFIED_CLAIM"}, "verdict must be one of"),  # an engine state, not a verdict
    ({"profile_sha256": "abc"}, "64-hex"),
])
def test_request_rules_refuse_before_the_engine(workspace, overrides, fragment):
    ws = workspace
    with _served(ws) as base:
        status, _h, body = _Client(base).post(_q(ws) + "/adjudicate",
                                              _signature(ws, **overrides))
    assert status == 422, body
    assert fragment in body["error"]["message"]
    assert _rows(ws) == []


def test_a_missing_attestation_key_is_refused_too(workspace):
    ws = workspace
    payload = _signature(ws)
    del payload["attest"]
    with _served(ws) as base:
        status, _h, _b = _Client(base).post(_q(ws) + "/adjudicate", payload)
    assert status == 422 and _rows(ws) == []


def test_unknown_ids_are_404_and_nothing_is_written(workspace):
    ws = workspace
    with _served(ws) as base:
        client = _Client(base)
        assert client.post(_q(ws, qid="Q999") + "/adjudicate", _signature(ws))[0] == 404
        assert client.post(_q(ws, flow_id="f" * 64) + "/adjudicate", _signature(ws))[0] == 404
        assert client.post(_q(ws, flow_id="not-a-flow") + "/adjudicate", _signature(ws))[0] == 404
        assert client.post(_q(ws, project="nope") + "/adjudicate", _signature(ws))[0] == 404
    assert _rows(ws) == []


def test_a_drifted_flow_cannot_carry_a_signature(workspace, monkeypatch):
    ws = workspace
    monkeypatch.setattr(flows, "binding_state", lambda *_a, **_k: {
        "state": "PROTOCOL_DRIFTED", "differences": ["protocol_sha256"],
        "bound_after_data": False})
    with _served(ws) as base:
        status, _h, body = _Client(base).post(_q(ws) + "/adjudicate", _signature(ws))
    assert status == 409 and body["error"]["code"] == "FLOW_DRIFTED"
    assert "PROTOCOL_DRIFTED" in body["error"]["message"]
    assert _rows(ws) == []


def test_csrf_and_session_are_required(workspace):
    ws = workspace
    with _served(ws) as base:
        client = _Client(base)
        status, _h, body = client.post(_q(ws) + "/adjudicate", _signature(ws),
                                       headers={"X-CSRF-Token": "wrong"})
        assert status == 403 and body["error"]["code"] == "CSRF"
        status, _h, _b = _request(base + _q(ws) + "/adjudicate", method="POST",
                                  payload=_signature(ws), headers={"Origin": base})
        assert status == 401
    assert _rows(ws) == []


# --- idempotency -----------------------------------------------------------------------------------


def test_the_same_key_signs_once_and_replays_the_answer(workspace):
    ws = workspace
    with _served(ws) as base:
        client = _Client(base)
        first = client.post(_q(ws) + "/adjudicate", _signature(ws),
                            headers={"Idempotency-Key": "k-1"})
        second = client.post(_q(ws) + "/adjudicate", _signature(ws),
                             headers={"Idempotency-Key": "k-1"})
        changed = client.post(_q(ws) + "/adjudicate",
                              _signature(ws, verdict="CONTESTED_IN_LITERATURE"),
                              headers={"Idempotency-Key": "k-1"})
    assert first[0] == 201 and second[0] == 201
    assert first[2] == second[2]
    assert changed[0] == 409 and changed[2]["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert len(_rows(ws)) == 1


def test_a_refused_request_leaves_its_key_free(workspace):
    ws = workspace
    with _served(ws) as base:
        client = _Client(base)
        refused = client.post(_q(ws) + "/adjudicate", _signature(ws, profile_sha256="0" * 64),
                              headers={"Idempotency-Key": "k-2"})
        assert refused[0] == 409
        corrected = client.post(_q(ws) + "/adjudicate", _signature(ws),
                                headers={"Idempotency-Key": "k-2"})
    # The second body differs from the first: had the refusal been kept, this would be a
    # conflict. A refusal executed nothing, so the key is free for the corrected request.
    assert corrected[0] == 201
    assert len(_rows(ws)) == 1


def test_keys_belong_to_one_operator():
    held = control.Idempotency()
    assert held.begin("op1", "k", "fp-a") is None
    held.finish("op1", "k", ({"ok": 1}, 201))
    assert held.begin("op2", "k", "fp-b") is None  # another operator's key space
    with pytest.raises(control.ControlError) as raised:
        held.begin("op2", "k", "fp-b")  # still running
    assert raised.value.code == "IDEMPOTENCY_IN_PROGRESS"
    assert held.begin("op1", "k", "fp-a") == ({"ok": 1}, 201)


# --- drafts ----------------------------------------------------------------------------------------


def test_a_draft_survives_a_profile_change_and_says_so(workspace):
    ws = workspace
    shown = _current(ws)
    with _served(ws) as base:
        client = _Client(base)
        status, _h, saved = client.post(_q(ws) + "/draft",
                                        {"rationale": "half a thought", "profile_sha256": shown})
        assert status == 201 and saved["current"] is True
        assert saved["draft"]["signer_auth"] == "portal-session"

        newer = dict(synthesize.latest_profiles(ws["store"], round_name="r1")[ws["qid"]])
        newer["profile_sha256"] = "c" * 64
        ws["store"].append(synthesize.PROFILES, newer)

        status, _h, read = client.get(_q(ws) + "/draft")
    assert status == 200
    assert read["draft"]["rationale"] == "half a thought"
    assert read["draft"]["profile_sha256"] == shown
    assert read["current"] is False
    assert read["current_profile_sha256"] == "c" * 64
    assert _rows(ws) == []  # a draft is never a signature


def test_drafts_are_private_to_their_operator(workspace):
    ws = workspace
    with _served(ws) as base:
        _Client(base).post(_q(ws) + "/draft",
                           {"rationale": "op1's text", "profile_sha256": _current(ws)})
        status, _h, other = _Client(base, "op2", "battery staple").get(_q(ws) + "/draft")
    assert status == 200
    assert other == {"draft": None, "current": None,
                     "current_profile_sha256": _current(ws)}


def test_drafts_never_enter_an_export_snapshot(workspace):
    ws = workspace
    drafts.append(ws["store"], actor="op1", flow_id=ws["flow_id"], question_id=ws["qid"],
                  rationale="private", profile_sha256=_current(ws), code_revision=None)
    prefixes, _torn = export.snapshot(ws["store"])
    assert drafts.LEDGER not in {prefix["path"] for prefix in prefixes}
    assert "private" not in json.dumps([p["path"] for p in prefixes])


def test_a_draft_needs_text_and_a_hash(workspace):
    ws = workspace
    with _served(ws) as base:
        client = _Client(base)
        assert client.post(_q(ws) + "/draft", {"rationale": 3,
                                               "profile_sha256": _current(ws)})[0] == 422
        assert client.post(_q(ws) + "/draft", {"rationale": "x"})[0] == 422
        assert client.post(_q(ws) + "/draft", {"rationale": "x", "profile_sha256": "0" * 64,
                                               "extra": 1})[0] == 400
