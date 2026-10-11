"""The new-project routes: sessions, CSRF, validation paths, idempotency, and no write to any
existing project."""

from __future__ import annotations

import hashlib
import pathlib
import shutil
import threading
import uuid
from contextlib import contextmanager

import pytest

from claimstone import control, operators
from tests.test_control import _cookie, _login, _request

REPO = pathlib.Path(__file__).resolve().parents[1]

STEP1 = {"name": "news-tone", "description": "scope", "topics": [{"label": "News", "terms": ["a b", "c d"]}]}
STEP2 = {"questions": [{"text": "Does news carry information?", "kind": "effect"},
                       {"text": "Which datasets exist?", "kind": "operational"}]}
STEP3 = {"template": "general", "classes": ["ACA"], "acquisition_floor": 0.8,
         "floor_rationale": "Set before the first measured round; below it coverage is uninterpretable.",
         "supplied_copies": "separate", "notation": "none", "custom_value_labels": [],
         "extra_excluded_hosts": []}


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "projects").mkdir()
    shutil.copytree(REPO / "projects" / "example-news-and-returns",
                    tmp_path / "projects" / "example-news-and-returns")
    shutil.copytree(REPO / "templates", tmp_path / "templates")
    state = tmp_path / "state"
    operators.add_operator(state, "op1", "Op One", "correct horse")
    operators.add_operator(state, "op2", "Op Two", "battery staple")
    return {"root": tmp_path, "projects": tmp_path / "projects", "store": tmp_path / "store",
            "state": state}


@contextmanager
def _served(ws):
    httpd = control.make_server(ws["projects"], ws["store"], host="127.0.0.1", port=0,
                                state_dir=ws["state"])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


class Client:
    def __init__(self, base, operator_id="op1", password="correct horse"):
        self.base = base
        status, headers, body = _login(base, operator_id, password)
        assert status == 200, body
        self.cookie, self.csrf = _cookie(headers), body["csrf_token"]

    def post(self, path, payload, key=None):
        sent = {"Cookie": self.cookie, "Origin": self.base, "X-CSRF-Token": self.csrf}
        if key:
            sent["Idempotency-Key"] = key
        return _request(f"{self.base}/control/v1{path}", method="POST", payload=payload, headers=sent)

    def get(self, path):
        return _request(f"{self.base}/control/v1{path}", headers={"Cookie": self.cookie})


def _create_body(client, draft):
    """What the review page sends: the confirmation and the digest it displayed."""
    return {"confirm": True, "protocol_sha256": client.get(f"/new/{draft}/preview")[2]["protocol_sha256"]}


def _tree(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _fill(client):
    _, _, started = client.post("/new", {})
    draft, rev = started["draft_id"], started["revision"]
    for step, data in ((1, STEP1), (2, STEP2), (3, STEP3)):
        status, _h, body = client.post(f"/new/{draft}/steps/{step}", {"base_revision": rev, "data": data})
        assert status == 200, body
        rev = body["revision"]
    return draft, rev


def test_every_new_project_route_refuses_an_anonymous_request(ws):
    with _served(ws) as base:
        for method, path in (("GET", "/new"), ("GET", "/new-templates"), ("GET", "/new/abc"),
                             ("GET", "/new/abc/preview")):
            assert _request(base + "/control/v1" + path)[0] == 401, path
        for path in ("/new", "/new/abc/steps/1", "/new/abc/advanced", "/new/abc/discard",
                     "/new/abc/create"):
            sent = {"Origin": base}
            assert _request(base + "/control/v1" + path, method="POST", payload={}, headers=sent)[0] == 401, path


def test_the_whole_wizard_creates_a_project_that_validates(ws):
    with _served(ws) as base:
        client = Client(base)
        draft, _rev = _fill(client)
        status, _h, preview = client.get(f"/new/{draft}/preview")
        assert status == 200 and preview["figures"]["questions_literature"] == 1
        status, _h, made = client.post(f"/new/{draft}/create", _create_body(client, draft), key=str(uuid.uuid4()))
    assert status == 201 and made["project"] == "news-tone"
    from claimstone.config import load_project
    assert load_project(ws["projects"] / "news-tone").registry_version == 1


def test_create_is_idempotent_for_one_key(ws):
    with _served(ws) as base:
        client = Client(base)
        draft, _ = _fill(client)
        key = str(uuid.uuid4())
        body = _create_body(client, draft)
        first = client.post(f"/new/{draft}/create", body, key=key)
        again = client.post(f"/new/{draft}/create", body, key=key)
    assert first[0] == again[0] == 201 and first[2] == again[2]


def test_a_validation_error_carries_field_paths(ws):
    with _served(ws) as base:
        client = Client(base)
        _, _, started = client.post("/new", {})
        status, _h, body = client.post(f"/new/{started['draft_id']}/steps/1",
                                       {"base_revision": 1, "data": {**STEP1, "name": "Bad Name"}})
    assert status == 422 and body["error"]["code"] == "VALIDATION"
    assert body["error"]["details"][0]["path"] == "name"


def test_create_needs_the_digest_the_page_showed(ws):
    with _served(ws) as base:
        client = Client(base)
        draft, _ = _fill(client)
        assert client.post(f"/new/{draft}/create", {"confirm": True})[0] == 422
        assert client.post(f"/new/{draft}/create", {"confirm": True, "protocol_sha256": "x"})[0] == 422
        status, _h, body = client.post(f"/new/{draft}/create", {"confirm": True, "protocol_sha256": "0" * 64})
    assert (status, body["error"]["code"]) == (409, "PREVIEW_CHANGED")
    assert not (ws["projects"] / "news-tone").exists()


def test_a_stale_revision_is_409(ws):
    with _served(ws) as base:
        client = Client(base)
        _, _, started = client.post("/new", {})
        draft = started["draft_id"]
        assert client.post(f"/new/{draft}/steps/1", {"base_revision": 1, "data": STEP1})[0] == 200
        status, _h, body = client.post(f"/new/{draft}/steps/1", {"base_revision": 1, "data": STEP1})
    assert (status, body["error"]["code"]) == (409, "STALE_REVISION")


def test_another_operators_draft_is_a_404(ws):
    with _served(ws) as base:
        mine, theirs = Client(base), Client(base, "op2", "battery staple")
        _, _, started = mine.post("/new", {})
        assert theirs.get(f"/new/{started['draft_id']}")[0] == 404
        assert theirs.get("/new")[2]["drafts"] == []


def test_unknown_keys_and_bad_bodies_are_400(ws):
    with _served(ws) as base:
        client = Client(base)
        _, _, started = client.post("/new", {})
        draft = started["draft_id"]
        assert client.post(f"/new/{draft}/steps/1", {"base_revision": 1, "data": STEP1, "x": 1})[0] == 400
        assert client.post(f"/new/{draft}/steps/1", {"base_revision": "1", "data": STEP1})[0] == 422
        assert client.post(f"/new/{draft}/steps/9", {"base_revision": 1, "data": {}})[0] == 404
        assert client.post(f"/new/{draft}/create", {"confirm": "yes"})[0] == 422


def test_no_route_changes_an_existing_project(ws):
    before = _tree(ws["projects"] / "example-news-and-returns")
    with _served(ws) as base:
        client = Client(base)
        draft, rev = _fill(client)
        client.post(f"/new/{draft}/advanced", {"base_revision": rev, "files": {}})
        client.get(f"/new/{draft}/preview")
        status, _h, body = client.post(f"/new/{draft}/create",
                                       {"confirm": True, "protocol_sha256": "0" * 64})
        assert (status, body["error"]["code"]) == (409, "PREVIEW_CHANGED")
        assert client.post(f"/new/{draft}/create", _create_body(client, draft))[0] == 201
        # a second draft aiming at the existing name is refused, then discarded
        _, _, second = client.post("/new", {})
        status, _h, _b = client.post(f"/new/{second['draft_id']}/steps/1",
                                     {"base_revision": 1, "data": {**STEP1, "name": "example-news-and-returns"}})
        assert status == 422
        assert client.post(f"/new/{second['draft_id']}/discard", {"base_revision": 1})[0] == 200
        # a name that becomes taken between review and creation
        _, _, third = client.post("/new", {})
        rev3 = 1
        for step, data in ((1, {**STEP1, "name": "late-name"}), (2, STEP2), (3, STEP3)):
            rev3 = client.post(f"/new/{third['draft_id']}/steps/{step}",
                               {"base_revision": rev3, "data": data})[2]["revision"]
        shown = _create_body(client, third["draft_id"])
        (ws["projects"] / "late-name").mkdir()
        status, _h, body = client.post(f"/new/{third['draft_id']}/create", shown)
        assert (status, body["error"]["code"]) == (409, "NAME_TAKEN")
    assert _tree(ws["projects"] / "example-news-and-returns") == before


def test_templates_are_served(ws):
    with _served(ws) as base:
        client = Client(base)
        assert [t["id"] for t in client.get("/new-templates")[2]["templates"]] == ["general"]
        assert client.get("/new-templates/general")[2]["default_floor"] == 0.8
        assert client.get("/new-templates/nope")[0] == 404


@pytest.mark.parametrize("step", ["01", "%C2%B2", "%E2%91%A0", "%D9%A3", "%EF%BC%91", "4", "0"])
def test_only_ascii_steps_one_to_three_are_routes(ws, step):
    with _served(ws) as base:
        client = Client(base)
        _, _, started = client.post("/new", {})
        draft = started["draft_id"]
        status, _h, body = client.post(f"/new/{draft}/steps/{step}", {"base_revision": 1, "data": STEP1})
        assert (status, body["error"]["code"]) == (404, "NOT_FOUND")
        assert client.get(f"/new/{draft}")[2]["revision"] == 1


def test_step_3_is_still_a_route(ws):
    with _served(ws) as base:
        client = Client(base)
        _, _, started = client.post("/new", {})
        status, _h, body = client.post(f"/new/{started['draft_id']}/steps/3",
                                       {"base_revision": 1, "data": STEP3})
        assert status == 200, body
