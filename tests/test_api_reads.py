"""the two BR read routes: a question's stored profiles, and a flow's exports.

Both are read-only listings through the real server over the `build_workspace` fixture
(spec BR). Profile generations are produced by the real instruments — `review.build`, an
answered call, `review.harvest`, `synthesize.build` — because a list of hashes the engine
never wrote would prove nothing about what the diff panel offers. Rows that exist only to
pin the scope (another round's profile, another flow's export, a later export id) are
hand-appended like the workspace's own fixture rows: they are scope data, not engine
output, and each says so where it is appended.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from claimstone import evidence, export, flows, scope
from tests.test_api import PROJECT, _error_json, _get_json, _served
from tests.test_api_profile_diff import _build, _review_claims
from tests.test_portal_state import build_workspace


@pytest.fixture()
def workspace(tmp_path):
    return build_workspace(tmp_path)


def _profiles_url(base: str, flow_id: str, question_id: str = "Q02") -> str:
    return (f"{base}/api/v1/projects/{PROJECT}/flows/{flow_id}/questions/{question_id}"
            f"/profiles")


def _exports_url(base: str, flow_id: str) -> str:
    return f"{base}/api/v1/projects/{PROJECT}/flows/{flow_id}/exports"


def _q02_rows(store, *, round_name: str = "r1") -> list[dict]:
    return [row for row in store.read("profiles.jsonl")
            if str(row.get("question_id")) == "Q02" and row.get("round") == round_name]


# --- stored profiles of one question ---------------------------------------------------------------


def test_two_builds_with_different_hashes_list_newest_first_with_one_current(workspace):
    """The two contents the ledger holds appear newest first, and `current` marks exactly
    the row `latest_profiles` returns — the newest, which is also the one a diff should
    default its `to` end to."""
    _review_claims(workspace, "rb1",
                   {"c1": ("SUPPORTED", "the quote carries the claim in context")})
    _build(workspace)
    with _served(workspace) as (_httpd, base, store):
        flow_id = next(iter(flows.flows(store)))
        status, _headers, payload = _get_json(_profiles_url(base, flow_id))
        rows = _q02_rows(store)
    assert status == 200
    entries = payload["profiles"]
    assert len(entries) == 2
    assert entries[0]["profile_sha256"] == str(rows[-1]["profile_sha256"])
    assert entries[1]["profile_sha256"] == str(rows[0]["profile_sha256"])
    assert entries[0]["profile_sha256"] != entries[1]["profile_sha256"]
    assert [entry["current"] for entry in entries] == [True, False]
    # The counts are the profile's own: the first build held no usable result, the
    # reviewed one records exactly the claim whose review said USABLE.
    assert entries[1]["state"] == evidence.NO_VERIFIED_CLAIM
    assert entries[1]["usable_results"] == 0
    assert entries[0]["state"] is None
    assert entries[0]["usable_results"] == 1


def test_a_rebuild_with_the_same_hash_collapses_to_one_entry(workspace):
    """A rebuild appends a row with the same content hash (`built_at` is not part of the
    digest); the list offers contents, not appends, so it still shows one entry."""
    _build(workspace)
    with _served(workspace) as (_httpd, base, store):
        flow_id = next(iter(flows.flows(store)))
        status, _headers, payload = _get_json(_profiles_url(base, flow_id))
        rows = _q02_rows(store)
    assert status == 200
    assert len(rows) == 2  # the ledger really holds both appends
    assert rows[0]["profile_sha256"] == rows[1]["profile_sha256"]
    [entry] = payload["profiles"]
    assert entry["profile_sha256"] == str(rows[-1]["profile_sha256"])
    assert entry["current"] is True


def test_a_row_of_another_round_is_excluded(workspace):
    """The flow's selector decides which rows are its: an r2 row of the same question —
    appended by hand, as scope data the engine's own r2 refuses to build — never enters
    the r1 flow's list."""
    store = workspace[3]
    store.append("profiles.jsonl", {
        "question_id": "Q02", "kind": "effect", "round": "r2", "manifest_only": False,
        "profile_version": 5, "profile_sha256": "f" * 64,
        "built_at": "2026-10-06T10:00:00+00:00", "provisional": True, "state": None,
        "results": [{"claim_id": "c9"}]})
    with _served(workspace) as (_httpd, base, served_store):
        flow_id = next(iter(flows.flows(served_store)))
        status, _headers, payload = _get_json(_profiles_url(base, flow_id))
    assert status == 200
    assert payload["profiles"]  # the r1 rows are still listed
    assert all(entry["profile_sha256"] != "f" * 64 for entry in payload["profiles"])


def test_an_empty_scope_is_an_empty_list_not_a_404(workspace):
    """The whole-store selector holds no profile rows for Q02 (every row names a round):
    an unbuilt history in this scope is a state the panel renders, so the answer is an
    empty list."""
    with _served(workspace) as (_httpd, base, _store):
        status, _headers, payload = _get_json(
            f"{base}/api/v1/projects/{PROJECT}/unbound/-/questions/Q02/profiles")
    assert status == 200
    assert payload["profiles"] == []


def test_an_unknown_question_is_404(workspace):
    """The list belongs to a question the registry knows: an invented id names nothing."""
    with _served(workspace) as (_httpd, base, store):
        flow_id = next(iter(flows.flows(store)))
        status, payload = _error_json(_profiles_url(base, flow_id, question_id="Q99"))
    assert status == 404
    assert payload["error"]["code"] == "NOT_FOUND"
    assert "unknown question id" in payload["error"]["message"]


# --- exports of one flow ----------------------------------------------------------------------------


def test_two_flows_exports_are_kept_apart_and_no_path_leaves_the_server(workspace):
    """A real export of the r1 flow beside a hand-appended row of a new r2 flow (scope
    data: the engine's export of an inadmissible round is another route's concern). Each
    flow sees only its own rows, `actor` appears only when the row records one, and the
    server-side `path` — which both ledger rows carry — is in neither response."""
    _projects_dir, _store_dir, project, store = workspace
    flow_one = next(iter(flows.flows(store)))
    export.export(project, store, flow_one)
    flow_two = flows.create(project, store, selector=scope.Selector("r2"),
                            title="round two")[0]["flow_id"]
    store.append("exports.jsonl", {
        "export_id": "b" * 64, "flow_id": str(flow_two), "path": "/nowhere/b",
        "created_at": "2026-10-06T12:00:00+00:00", "actor": "op-7"})
    with _served(workspace) as (_httpd, base, _served_store):
        status_one, _headers, one = _get_json(_exports_url(base, flow_one))
        status_two, _headers, two = _get_json(_exports_url(base, flow_two))
    assert status_one == 200 and status_two == 200
    [entry_one] = one["exports"]
    assert entry_one["export_id"] != "b" * 64
    assert "actor" not in entry_one  # the CLI row records none
    [entry_two] = two["exports"]
    assert entry_two["export_id"] == "b" * 64
    assert entry_two["actor"] == "op-7"
    for payload in (one, two):
        assert "path" not in json.dumps(payload)


def test_exports_of_one_flow_list_newest_first(workspace):
    """Append order reversed: the later row of the same flow is listed first."""
    _projects_dir, _store_dir, project, store = workspace
    flow_id = next(iter(flows.flows(store)))
    export.export(project, store, flow_id)
    first = next(str(row["export_id"]) for row in store.read("exports.jsonl"))
    store.append("exports.jsonl", {
        "export_id": "c" * 64, "flow_id": str(flow_id), "path": "/nowhere/c",
        "created_at": "2026-10-06T12:00:01+00:00"})
    with _served(workspace) as (_httpd, base, _served_store):
        status, _headers, payload = _get_json(_exports_url(base, flow_id))
    assert status == 200
    assert [entry["export_id"] for entry in payload["exports"]] == ["c" * 64, first]


def test_no_exports_is_an_empty_list(workspace):
    """A flow that was never exported lists nothing, and that is not an error."""
    with _served(workspace) as (_httpd, base, store):
        flow_id = next(iter(flows.flows(store)))
        status, _headers, payload = _get_json(_exports_url(base, flow_id))
    assert status == 200
    assert payload["exports"] == []


def test_both_routes_are_get_only(workspace):
    """The read API's wire rule, checked on the two new routes themselves: every non-GET
    verb is refused by the transport before any routing happens."""
    with _served(workspace) as (_httpd, base, store):
        flow_id = next(iter(flows.flows(store)))
        for path in (f"/api/v1/projects/{PROJECT}/flows/{flow_id}/questions/Q02/profiles",
                     f"/api/v1/projects/{PROJECT}/flows/{flow_id}/exports"):
            for verb in ("POST", "PUT", "DELETE"):
                request = urllib.request.Request(base + path, data=b"x", method=verb)
                with pytest.raises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(request, timeout=10)
                assert raised.value.code == 405, (verb, path)
