"""B8: identity answers, retry campaigns, purchase offers, defer and decline.

Nothing here executes work or contacts anything: an approved campaign is a record, a purchase
happens outside Claimstone, and possession comes only from a file that passes intake.
"""

from __future__ import annotations

import datetime as dt
import threading
from contextlib import contextmanager

import pytest

from claimstone import admissibility, control, decisions, flows, intake, operators
from tests.test_control import _cookie, _login, _request
from tests.test_intake_files import TITLE, _pdf
from tests.test_portal_state import build_workspace

REASON = "The first page names a 2008 discussion paper; the candidate is the 2009 article."


def _now(**delta) -> str:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(**delta)).isoformat(timespec="seconds")


@pytest.fixture()
def ws(tmp_path):
    projects_dir, store_dir, project, store = build_workspace(tmp_path)
    state = tmp_path / "state"
    operators.add_operator(state, "op1", "Op One", "correct horse")
    store.append("candidates.jsonl", {
        "candidate_key": "r1-c", "source_id": "S09", "round": "r1", "channel": "keyword",
        "source_class": "ACA", "title": TITLE, "doi": "10.1234/study.three",
        "url": "https://example.org/S09", "discovered_at": "2026-10-03T10:00:00+00:00"})
    # A refused candidate: two hosts reached, one of them refusing repeatedly.
    store.append("candidates.jsonl", {
        "candidate_key": "r1-d", "source_id": "S10", "round": "r1", "channel": "keyword",
        "source_class": "WP", "title": "A refused working paper on returns",
        "url": "https://pub.example/S10", "discovered_at": "2026-10-03T10:00:01+00:00"})
    store.append("acquisitions.jsonl", {
        "candidate_key": "r1-d", "source_id": "S10", "source_class": "WP", "acquired": False,
        "failure_class": "PAYWALL_403", "url": "https://pub.example/S10", "campaign": "routine",
        "attempt_no": 1, "fetched_at": _now(hours=-1),
        "attempts": [{"url": "https://pub.example/S10", "http_status": 403,
                      "failure_class": "PAYWALL_403"},
                     {"url": "https://repo.example/S10.pdf", "http_status": 404,
                      "failure_class": "NOT_FOUND"}]})
    for _ in range(5):
        store.append("requests.jsonl", {"event": "transport", "url": "https://pub.example/x",
                                        "failure_class": "PAYWALL_403", "recorded_at": _now()})
    row = next(iter(flows.flows(store).values()))
    from claimstone import portal_state, scope
    selector = portal_state._selector_of(row, scope.Selector(None))
    return {"projects": projects_dir, "store_dir": store_dir, "project": project, "store": store,
            "state": state, "flow": row, "flow_id": row["flow_id"], "selector": selector}


def _possible_version_file(ws):
    """A quarantined file for r1-c whose title was not found: an identity question."""
    payload = _pdf(["A different first page"])
    sha, path, held = intake.quarantine_stream(ws["store"], __import__("io").BytesIO(payload),
                                               len(payload))
    return intake.receive_file(ws["store"], ws["project"], ws["flow"], ws["selector"],
                               target="r1-c", sha=sha, path=path, already_held=held,
                               actor="op1", code_revision=None,
                               extract_text=lambda _p: "A different first page")


def _possible_version_reference(ws):
    held = ws["store"].latest_by("candidates.jsonl", "candidate_key")["r1-b"]
    ws["store"].append("candidates.jsonl", {**held, "title": "Tone in the news and later returns"})
    return intake.submit(ws["store"], ws["project"], ws["flow"], ws["selector"], kind="reference",
                         value="Doe (2018). Tone in the news and later returns. WP 12.",
                         note=None, actor="op1", code_revision=None)


def _resolve(ws, item, answer, reason=REASON):
    return decisions.resolve_identity(ws["store"], ws["project"], ws["flow"], ws["selector"],
                                      intake_id=item["intake_id"], answer=answer, reason=reason,
                                      actor="op1", code_revision=None)


def _supplied(ws):
    return [r for r in ws["store"].read("acquisitions.jsonl")
            if r.get("provenance") == admissibility.OPERATOR_SUPPLIED]


# --- identity ---------------------------------------------------------------------------------------


def test_same_work_accepts_the_file_through_the_one_acceptance_path(ws):
    item = _possible_version_file(ws)
    assert item["state"] == "POSSIBLE_VERSION"
    result = _resolve(ws, item, "same_work")
    assert result["intake"]["state"] == "REPORTED_SEPARATELY"
    assert result["intake"]["intake_id"] == item["intake_id"]
    assert result["intake"]["links"]["identity"]["confirmed_by_decision"] == \
        result["decision"]["decision_id"]
    [row] = _supplied(ws)
    assert row["intake_id"] == item["intake_id"] and row["gate"]


@pytest.mark.parametrize("answer", ["version_of", "different"])
def test_a_version_or_another_work_is_never_the_candidates_copy(ws, answer):
    item = _possible_version_file(ws)
    result = _resolve(ws, item, answer)
    assert result["intake"]["state"] == "REJECTED"
    assert _supplied(ws) == []
    assert result["decision"]["answer"] == answer and result["decision"]["reason"] == REASON


def test_not_sure_keeps_the_question_open_and_needs_no_reason(ws):
    item = _possible_version_file(ws)
    result = _resolve(ws, item, "not_sure", reason=None)
    assert result["intake"]["state"] == "POSSIBLE_VERSION"
    assert intake.latest(ws["store"])[item["intake_id"]]["state"] == "POSSIBLE_VERSION"
    assert [o["id"] for o in decisions.open_items(ws["store"], ws["selector"], ws["flow_id"])
            if o["type"] == "identity"] == [item["intake_id"]]


def test_a_reference_version_adds_no_study_and_a_different_one_is_routed_anew(ws):
    item = _possible_version_reference(ws)
    assert item["state"] == "POSSIBLE_VERSION"
    found_before = admissibility.rate(ws["store"], round_name="r1")["found"]
    version = _resolve(ws, item, "version_of")
    assert version["intake"]["state"] == "DUPLICATE"
    assert admissibility.rate(ws["store"], round_name="r1")["found"] == found_before

    other = _possible_version_reference(ws)
    assert other["state"] == "DUPLICATE"  # the same reference again: recognised, not re-asked


def test_a_different_reference_is_routed_as_a_new_work(ws):
    item = _possible_version_reference(ws)
    result = _resolve(ws, item, "different")
    assert result["intake"]["state"] == "READY" and "r1" in result["intake"]["reason"]


def test_identity_refusals(ws):
    item = _possible_version_file(ws)
    with pytest.raises(decisions.DecisionRefused, match="below 20"):
        _resolve(ws, item, "same_work", reason="looks right")
    with pytest.raises(decisions.DecisionRefused):
        _resolve(ws, item, "merge")
    _resolve(ws, item, "different")
    with pytest.raises(decisions.Conflict):
        _resolve(ws, item, "same_work")  # already answered
    with pytest.raises(LookupError):
        _resolve(ws, {"intake_id": "nope"}, "same_work")


# --- retry campaigns --------------------------------------------------------------------------------


def test_the_preview_is_built_from_recorded_attempts_and_the_host_budget(ws):
    plan = decisions.retry_preview(ws["store"], ws["project"], ws["selector"], ["r1-d"])
    assert plan["hosts"] == ["repo.example"]
    assert "budget exhausted" in plan["refused_hosts"]["pub.example"]
    assert plan["candidates"][0]["last_failure"] == "PAYWALL_403"


def test_an_excluded_host_is_never_in_a_plan(ws):
    held = ws["store"].latest_by("candidates.jsonl", "candidate_key")["r1-c"]
    ws["store"].append("candidates.jsonl", {**held, "url": "https://sci-hub.se/S09"})
    plan = decisions.retry_preview(ws["store"], ws["project"], ws["selector"], ["r1-c"])
    assert plan["hosts"] == [] and "excluded" in plan["refused_hosts"]["sci-hub.se"]
    with pytest.raises(decisions.Conflict, match="no host"):
        decisions.approve_retry(ws["store"], ws["project"], ws["flow"], ws["selector"],
                                candidate_keys=["r1-c"], campaign="retry-sci", max_requests=2,
                                actor="op1", code_revision=None)


def test_an_approval_records_the_exact_plan_and_executes_nothing(ws):
    requests_before = list(ws["store"].read("requests.jsonl"))
    row = decisions.approve_retry(ws["store"], ws["project"], ws["flow"], ws["selector"],
                                  candidate_keys=["r1-d"], campaign="retry-s10", max_requests=4,
                                  actor="op1", code_revision=None)
    assert row["state"] == "approved" and row["plan"]["hosts"] == ["repo.example"]
    assert list(ws["store"].read("requests.jsonl")) == requests_before
    with pytest.raises(decisions.Conflict, match="already recorded"):
        decisions.approve_retry(ws["store"], ws["project"], ws["flow"], ws["selector"],
                                candidate_keys=["r1-d"], campaign="retry-s10", max_requests=4,
                                actor="op1", code_revision=None)


@pytest.mark.parametrize("campaign, max_requests", [
    ("routine", 4), ("X", 4), ("retry-ok", 0), ("retry-ok", 51), ("retry-ok", "4"), ("retry-ok", True)])
def test_campaign_bounds(ws, campaign, max_requests):
    with pytest.raises(decisions.DecisionRefused):
        decisions.approve_retry(ws["store"], ws["project"], ws["flow"], ws["selector"],
                                candidate_keys=["r1-d"], campaign=campaign,
                                max_requests=max_requests, actor="op1", code_revision=None)


def test_a_candidate_with_a_copy_has_nothing_to_retry(ws):
    with pytest.raises(decisions.Conflict):
        decisions.retry_preview(ws["store"], ws["project"], ws["selector"], ["r1-a"])


# --- purchase offers --------------------------------------------------------------------------------


def _offer(ws, **overrides):
    body = {"candidate_id": "r1-c", "work_version": "journal version of record",
            "vendor": "A publisher", "price": "35.00", "currency": "EUR",
            "terms_url": "https://shop.example/terms", "verified_at": _now(minutes=-5),
            "resolves": "Q04's coverage: the one ACA source without a copy"}
    body.update(overrides)
    return decisions.record_offer(ws["store"], ws["flow"], ws["selector"], body=body,
                                  actor="op1", code_revision=None)


def _stage(ws, offer, stage):
    return decisions.offer_stage(ws["store"], ws["flow"], offer_id=offer["decision_id"],
                                 stage=stage, actor="op1", code_revision=None)


def test_approval_payment_and_possession_are_four_different_facts(ws):
    offer = _offer(ws)
    assert offer["state"] == "proposed"
    _stage(ws, offer, "approved")
    bought = _stage(ws, offer, "bought_externally")
    assert decisions.possession(ws["store"], bought) is None
    with pytest.raises(decisions.DecisionRefused, match="only from a file"):
        _stage(ws, offer, "copy_verified")

    payload = _pdf([TITLE])
    sha, path, held = intake.quarantine_stream(ws["store"], __import__("io").BytesIO(payload),
                                               len(payload))
    intake.receive_file(ws["store"], ws["project"], ws["flow"], ws["selector"], target="r1-c",
                        sha=sha, path=path, already_held=held, actor="op1", code_revision=None,
                        extract_text=lambda _p: TITLE)
    latest = decisions.latest(ws["store"])[offer["decision_id"]]
    assert decisions.possession(ws["store"], latest) == "copy_verified"
    assert offer["decision_id"] not in {
        o["id"] for o in decisions.open_items(ws["store"], ws["selector"], ws["flow_id"])}


def test_stages_cannot_be_skipped(ws):
    offer = _offer(ws)
    with pytest.raises(decisions.Conflict):
        _stage(ws, offer, "bought_externally")  # not approved yet


def test_a_changed_offer_is_a_new_offer_and_the_old_approval_does_not_carry(ws):
    first = _offer(ws)
    _stage(ws, first, "approved")
    second = _offer(ws, price="42.00")
    assert second["supersedes"] == first["decision_id"]
    assert second["state"] == "proposed"
    assert decisions.latest(ws["store"])[first["decision_id"]]["state"] == "obsolete"
    with pytest.raises(decisions.Conflict, match="already recorded"):
        _offer(ws, price="42.00")


@pytest.mark.parametrize("overrides", [
    {"price": "-1"}, {"price": "free"}, {"currency": "eur"}, {"terms_url": "ftp://x/terms"},
    {"verified_at": "2026-10-07"}, {"verified_at": "2999-01-01T00:00:00+00:00"},
    {"vendor": " "}, {"resolves": ""}])
def test_offer_fields_are_validated(ws, overrides):
    with pytest.raises(decisions.DecisionRefused):
        _offer(ws, **overrides)


def test_no_offer_for_a_candidate_that_already_has_a_copy(ws):
    with pytest.raises(decisions.Conflict):
        _offer(ws, candidate_id="r1-a")


# --- defer, decline, order --------------------------------------------------------------------------


def test_declining_states_the_consequence_and_closes_the_item(ws):
    offer = _offer(ws)
    row = decisions.set_state(ws["store"], ws["flow"], decision_id=offer["decision_id"],
                              state="declined", until=None, reason=REASON, actor="op1",
                              code_revision=None)
    assert row["consequence"] == "the candidate stays not obtained; nothing is bought"
    assert offer["decision_id"] not in {
        o["id"] for o in decisions.open_items(ws["store"], ws["selector"], ws["flow_id"])}
    with pytest.raises(decisions.Conflict):
        _stage(ws, offer, "approved")


def test_a_deferral_hides_the_item_until_its_date(ws):
    offer = _offer(ws)
    tomorrow = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    decisions.set_state(ws["store"], ws["flow"], decision_id=offer["decision_id"],
                        state="deferred", until=tomorrow, reason=REASON, actor="op1",
                        code_revision=None)
    assert offer["decision_id"] not in {
        o["id"] for o in decisions.open_items(ws["store"], ws["selector"], ws["flow_id"])}
    with pytest.raises(decisions.DecisionRefused, match="future"):
        decisions.set_state(ws["store"], ws["flow"], decision_id=offer["decision_id"],
                            state="deferred", until="2020-01-01", reason=REASON, actor="op1",
                            code_revision=None)


def test_the_open_list_ignores_claims_reviews_and_stances(ws):
    """F13: the order is required first, then acquisition metadata, then age. Adding claims that
    favour one candidate's source must not move anything."""
    _offer(ws)
    _possible_version_file(ws)
    before = [o["id"] for o in decisions.open_items(ws["store"], ws["selector"], ws["flow_id"])]
    assert decisions.open_items(ws["store"], ws["selector"], ws["flow_id"])[0]["required"] is True
    for stance in ("SUPPORTS", "CONTRADICTS"):
        ws["store"].append("claims.jsonl", {
            "claim_id": f"c-{stance}", "question_id": "Q02", "source_id": "S09",
            "source_class": "ACA", "stance": stance, "claim": "x", "evidence_quote": "x"})
        ws["store"].append("reviews.jsonl", {"claim_id": f"c-{stance}", "verdict": "SUPPORTED"})
    after = [o["id"] for o in decisions.open_items(ws["store"], ws["selector"], ws["flow_id"])]
    assert after == before


# --- the routes -------------------------------------------------------------------------------------


@contextmanager
def _served(ws):
    httpd = control.make_server(ws["projects"], ws["store_dir"], host="127.0.0.1", port=0,
                                state_dir=ws["state"])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        status, headers, body = _login(base)
        yield base, _cookie(headers), body["csrf_token"]
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def test_routes_map_the_rules_to_statuses(ws):
    prefix = f"/control/v1/p/{ws['project'].name}/flows/{ws['flow_id']}"
    with _served(ws) as (base, cookie, csrf):
        headers = {"Cookie": cookie, "Origin": base, "X-CSRF-Token": csrf}
        status, _h, plan = _request(base + prefix + "/decisions/retry-campaign/preview"
                                    "?candidate_ids=r1-d", headers={"Cookie": cookie})
        assert status == 200 and plan["hosts"] == ["repo.example"]
        assert _request(base + prefix + "/decisions/retry-campaign/preview?candidate_ids=nope",
                        headers={"Cookie": cookie})[0] == 404
        status, _h, made = _request(base + prefix + "/offers", method="POST", headers=headers,
                                    payload={"candidate_id": "r1-c", "work_version": "v",
                                             "vendor": "V", "price": "1", "currency": "EUR",
                                             "terms_url": "https://shop.example/t",
                                             "verified_at": _now(minutes=-1), "resolves": "r"})
        assert status == 201
        offer_id = made["offer"]["decision_id"]
        assert _request(base + prefix + f"/offers/{offer_id}/stage", method="POST",
                        headers=headers, payload={"stage": "bought_externally"})[0] == 409
        assert _request(base + prefix + f"/offers/{offer_id}/stage", method="POST",
                        headers=headers, payload={"stage": "copy_verified"})[0] == 422
        status, _h, listed = _request(base + prefix + "/decisions", headers={"Cookie": cookie})
        assert status == 200 and [o["id"] for o in listed["open"]] == [offer_id]
        assert _request(base + prefix + "/intake/nope/resolve", method="POST", headers=headers,
                        payload={"answer": "same_work", "reason": REASON})[0] == 404
