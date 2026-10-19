"""Starting research from the portal: the first flow of a project, and its first network batch.

Both routes only *record*: a flow binds a round to the protocol, a batch freezes plans in
`planned` state. Neither contacts a host. Authorizing stays the separate, exact act of a person.
"""

from __future__ import annotations

import shutil
import threading
from contextlib import contextmanager

import pytest

from claimstone import control, flows, operations, operators
from claimstone.config import load_project
from claimstone.store import Store
from tests.test_control import _cookie, _login, _request


@pytest.fixture()
def ws(tmp_path):
    root = tmp_path / "example-news-and-returns"
    shutil.copytree("projects/example-news-and-returns", root)
    state = tmp_path / "state"
    operators.add_operator(state, "op1", "Op One", "correct horse")
    project = load_project(root)
    return {"projects": tmp_path, "store_dir": tmp_path / "store", "project": project,
            "store": Store(project.name, base=tmp_path / "store"), "state": state}


@contextmanager
def _served(ws):
    httpd = control.make_server(ws["projects"], ws["store_dir"], host="127.0.0.1", port=0,
                                state_dir=ws["state"])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        _status, headers, body = _login(base)
        yield base, f"/control/v1/p/{ws['project'].name}", {
            "Cookie": _cookie(headers), "Origin": base, "X-CSRF-Token": body["csrf_token"]}
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _start(base, prefix, headers, **overrides):
    payload = {"title": "First search", "round": "first-2026-10-16"} | overrides
    return _request(base + prefix + "/flows", method="POST", headers=headers, payload=payload)


def test_the_first_flow_binds_a_named_round_and_a_repeat_is_not_a_second_flow(ws):
    with _served(ws) as (base, prefix, headers):
        status, _h, body = _start(base, prefix, headers)
        again = _start(base, prefix, headers)
    assert status == 201 and body["created"] is True
    assert again[0] == 200 and again[2]["created"] is False
    assert again[2]["flow_id"] == body["flow_id"]
    held = flows.flows(ws["store"])
    assert list(held) == [body["flow_id"]]
    assert held[body["flow_id"]]["binding"]["selector"]["round"] == "first-2026-10-16"


@pytest.mark.parametrize("overrides", [
    {"round": ""}, {"round": "has space"}, {"round": "../escape"}, {"round": "x" * 200},
    {"title": ""}, {"title": "t" * 500}, {"title": 7}, {"round": None},
])
def test_a_bad_title_or_round_name_is_refused_and_records_nothing(ws, overrides):
    with _served(ws) as (base, prefix, headers):
        status, _h, body = _start(base, prefix, headers, **overrides)
    assert status == 422 and body["error"]["code"] == "VALIDATION"
    assert flows.flows(ws["store"]) == {}


def test_unknown_fields_and_unknown_projects_are_refused(ws):
    with _served(ws) as (base, prefix, headers):
        extra = _request(base + prefix + "/flows", method="POST", headers=headers,
                         payload={"title": "t", "round": "r-1", "manifest_only": True})
        missing = _request(base + "/control/v1/p/nope/flows", method="POST", headers=headers,
                           payload={"title": "t", "round": "r-1"})
    assert extra[0] in (400, 422) and missing[0] == 404
    assert flows.flows(ws["store"]) == {}


def _plan(base, prefix, headers, flow_id, **overrides):
    payload = {"stage": "discover", "apis": ["openalex"], "allowed_hosts": ["api.openalex.org"],
               "max_units": 1, "max_requests_each": 3, "per_query": 10} | overrides
    return _request(f"{base}{prefix}/flows/{flow_id}/batches", method="POST", headers=headers,
                    payload=payload)


def test_a_discovery_batch_is_frozen_planned_and_contacts_no_host(ws):
    with _served(ws) as (base, prefix, headers):
        flow_id = _start(base, prefix, headers)[2]["flow_id"]
        status, _h, batch = _plan(base, prefix, headers, flow_id)
        listed = _request(f"{base}{prefix}/flows/{flow_id}/batches",
                          headers={"Cookie": headers["Cookie"]})[2]["batches"]
    assert status == 201 and batch["selected"] == 1 and batch["max_total_requests"] == 3
    assert [item["batch_id"] for item in listed] == [batch["batch_id"]]
    assert listed[0]["awaiting_approval"] == 1
    events = [row["event"] for row in ws["store"].read(operations.LEDGER)]
    assert events == ["planned"]
    assert not ws["store"].path("requests.jsonl").exists()


def test_planning_needs_exact_hosts_and_a_known_flow(ws):
    with _served(ws) as (base, prefix, headers):
        flow_id = _start(base, prefix, headers)[2]["flow_id"]
        no_hosts = _plan(base, prefix, headers, flow_id, allowed_hosts=[])
        bad_stage = _plan(base, prefix, headers, flow_id, stage="extract")
        unknown = _plan(base, prefix, headers, "0" * 64)
        extra = _plan(base, prefix, headers, flow_id, use_apis=True)
    assert no_hosts[0] == 422 and bad_stage[0] == 422
    assert unknown[0] == 404 and extra[0] in (400, 422)
    assert not ws["store"].path(operations.LEDGER).exists()


def test_planning_and_starting_require_a_session(ws):
    with _served(ws) as (base, prefix, _headers):
        started = _request(base + prefix + "/flows", method="POST",
                           payload={"title": "t", "round": "r-1"})
    assert started[0] in (401, 403)
    assert flows.flows(ws["store"]) == {}


def test_use_apis_is_optional_boolean_and_acquire_only(ws):
    with _served(ws) as (base, prefix, headers):
        flow_id = _start(base, prefix, headers)[2]["flow_id"]
        on_discover = _plan(base, prefix, headers, flow_id, use_apis=True)
        not_boolean = _plan(base, prefix, headers, flow_id, use_apis="yes")
    assert on_discover[0] == 422 and not_boolean[0] == 422
    assert not ws["store"].path(operations.LEDGER).exists()


def test_acquire_hosts_are_suggested_from_the_record_and_never_include_excluded_hosts(ws):
    excluded = ws["project"].excluded_hosts[0]
    with _served(ws) as (base, prefix, headers):
        flow_id = _start(base, prefix, headers)[2]["flow_id"]
        for key, url in [("doi:1", "https://doi.org/10.1/a"), ("doi:2", "https://doi.org/10.1/b"),
                         ("doi:3", "https://repo.example.org/x.pdf"),
                         ("doi:4", f"https://{excluded}/x.pdf"), ("doi:5", "https://seen.example.org/p.pdf")]:
            ws["store"].append("candidates.jsonl", {
                "candidate_key": key, "round": "first-2026-10-16", "url": url,
                "source_class": ws["project"].classes[0].id, "title": key,
                "found_at": "2026-10-16T00:00:00+00:00"})
        ws["store"].append("acquisitions.jsonl", {
            "candidate_key": "doi:5", "failure_class": "EXCLUDED_HOST",
            "attempts": [{"failure_class": "EXCLUDED_HOST", "detail": "pmc.ncbi.nlm.nih.gov is outside this plan"},
                         {"failure_class": "EXCLUDED_HOST", "detail": f"{excluded} is outside this plan"},
                         {"failure_class": "EXCLUDED_HOST", "detail": "other.example.org is excluded"}]})
        got = _request(f"{base}{prefix}/flows/{flow_id}/acquire-hosts",
                       headers={"Cookie": headers["Cookie"]})
    assert got[0] == 200
    assert got[2]["pending_candidates"] == 3
    assert got[2]["candidate_hosts"] == [{"host": "doi.org", "candidates": 2},
                                         {"host": "repo.example.org", "candidates": 1}]
    assert got[2]["refused_hosts"] == [{"host": "pmc.ncbi.nlm.nih.gov", "candidates": 1,
                                        "sources": ["unknown"], "open_access_candidates": 0}]


def test_refused_hosts_say_who_named_them_and_only_open_access_sources_count_as_a_proposal(ws):
    def refusal(host, request_host, provenance, oa_status):
        return {"failure_class": "EXCLUDED_HOST", "detail": f"{host} is outside this plan",
                "request_url": f"https://{request_host}/x", "provenance": provenance, "oa_status": oa_status}

    with _served(ws) as (base, prefix, headers):
        flow_id = _start(base, prefix, headers)[2]["flow_id"]
        for key in ("doi:1", "doi:2"):
            _candidate(ws, key, "https://seen.example.org/p.pdf")
            ws["store"].append("acquisitions.jsonl", {
                "candidate_key": key, "failure_class": "EXCLUDED_HOST", "attempts": [
                    refusal("pmc.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov", "unpaywall", "gold"),
                    refusal("publisher.example.org", "doi.org", "candidate", "closed"),
                    refusal("closed.example.org", "closed.example.org", "unpaywall", "closed"),
                    # the resolver named doi.org; the publisher was only reached by redirect
                    refusal("viaredirect.example.org", "doi.org", "unpaywall", "gold")]})
        got = _request(f"{base}{prefix}/flows/{flow_id}/acquire-hosts",
                       headers={"Cookie": headers["Cookie"]})
    by_host = {item["host"]: item for item in got[2]["refused_hosts"]}
    assert by_host["pmc.ncbi.nlm.nih.gov"] == {"host": "pmc.ncbi.nlm.nih.gov", "candidates": 2,
                                               "sources": ["unpaywall"], "open_access_candidates": 2}
    for host in ("publisher.example.org", "closed.example.org", "viaredirect.example.org"):
        assert by_host[host]["open_access_candidates"] == 0


def _candidate(ws, key, url):
    ws["store"].append("candidates.jsonl", {
        "candidate_key": key, "round": "first-2026-10-16", "url": url,
        "source_class": ws["project"].classes[0].id, "title": key,
        "found_at": "2026-10-16T00:00:00+00:00"})


def test_acquire_hosts_report_retryable_classes_and_a_higher_ceiling_for_plain_http(ws):
    with _served(ws) as (base, prefix, headers):
        flow_id = _start(base, prefix, headers)[2]["flow_id"]
        _candidate(ws, "doi:1", "http://old.example.org/a.pdf")
        _candidate(ws, "doi:2", "https://repo.example.org/b.pdf")
        ws["store"].append("acquisitions.jsonl", {
            "candidate_key": "doi:2", "failure_class": "REQUEST_LIMIT_REACHED", "attempts": []})
        got = _request(f"{base}{prefix}/flows/{flow_id}/acquire-hosts",
                       headers={"Cookie": headers["Cookie"]})[2]
    assert got["plain_http_candidates"] == 1 and got["suggested_max_requests_each"] == 5
    assert got["retryable_classes"] == [{"failure_class": "REQUEST_LIMIT_REACHED", "candidates": 1}]


def test_a_retry_needs_a_reason_and_applies_only_to_acquire(ws):
    with _served(ws) as (base, prefix, headers):
        flow_id = _start(base, prefix, headers)[2]["flow_id"]
        no_reason = _plan(base, prefix, headers, flow_id, stage="acquire", apis=[],
                          retry_classes=["REQUEST_LIMIT_REACHED"])
        orphan = _plan(base, prefix, headers, flow_id, stage="acquire", apis=[],
                       retry_reason="why")
        on_discover = _plan(base, prefix, headers, flow_id, retry_classes=["REDIRECT_ERROR"],
                            retry_reason="again")
    assert no_reason[0] == 422 and orphan[0] == 422 and on_discover[0] == 422
    assert not ws["store"].path(operations.LEDGER).exists()


def test_a_retry_plan_is_frozen_for_the_candidate_that_hit_the_ceiling(ws):
    with _served(ws) as (base, prefix, headers):
        flow_id = _start(base, prefix, headers)[2]["flow_id"]
        _candidate(ws, "doi:2", "https://repo.example.org/b.pdf")
        ws["store"].append("acquisitions.jsonl", {
            "candidate_key": "doi:2", "failure_class": "REQUEST_LIMIT_REACHED", "attempts": []})
        status, _h, batch = _plan(base, prefix, headers, flow_id, stage="acquire", apis=[],
                                  allowed_hosts=["repo.example.org"], max_requests_each=5,
                                  retry_classes=["REQUEST_LIMIT_REACHED"],
                                  retry_reason="ceiling was 3; http redirect used one")
    assert status == 201 and batch["selected"] == 1 and batch["max_total_requests"] == 5
    assert batch["units"][0]["retry_classes"] == ["REQUEST_LIMIT_REACHED"]


def test_a_failed_operation_states_its_cause_in_the_state_note(ws):
    from claimstone import operations_view
    with _served(ws) as (base, prefix, headers):
        flow_id = _start(base, prefix, headers)[2]["flow_id"]
        batch = _plan(base, prefix, headers, flow_id)[2]
    operation_id = batch["operation_ids"][0]
    operations.authorize(ws["store"], operation_id, identity={"operator": "op1"})
    operations._append(ws["store"], operation_id, flow_id, "failed", "worker",
                       failure_class="OperationError",
                       detail="project or code identity changed; prepare a new plan")
    [item] = operations_view.for_flow(ws["store"], flow_id)
    assert item["state"] == "FAILED"
    assert "prepare a new plan" in item["state_note"] and "OperationError" in item["state_note"]
