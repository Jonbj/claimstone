"""profile-diff: B6 — two stored profiles of one question compared result by result,
through the real server over the `build_workspace` fixture (spec B6).

Every comparison is between hashes the ledger actually holds: the second and third
profile generations are produced by the real instruments — `review.build`, an answered
call, `review.harvest`, `synthesize.build` — never by hand-written profile rows, because a
diff against an invented hash would prove nothing about the engine.
"""

from __future__ import annotations

import pytest

from claimstone import claimgate, flows, model_call, review, synthesize
from tests.test_api import PROJECT, _error_json, _get_json, _q02_sha, _served
from tests.test_portal_state import build_workspace

# A reader different from the fixture's extractor ("b"/"m"): the different-reader refusal
# is the point of stage 5, and the same reader would never reach the ledger.
READER = {"backend": "claude-cli", "model": "claude-opus-5", "harness_version": "claude-cli/1"}


@pytest.fixture()
def workspace(tmp_path):
    return build_workspace(tmp_path)


def _diff_url(base: str, flow_id: str, from_sha: str, to_sha: str,
              question_id: str = "Q02") -> str:
    return (f"{base}/api/v1/projects/{PROJECT}/flows/{flow_id}/questions/{question_id}"
            f"/profile-diff?from={from_sha}&to={to_sha}")


def _q02_sha(store, *, which: int = -1) -> str:
    """Q02's stored profile hashes, in the order they were built; `which=-1` is the newest."""
    rows = [row for row in store.read("profiles.jsonl")
            if str(row.get("question_id")) == "Q02"]
    return str(rows[which]["profile_sha256"])


def _review_claims(workspace, batch: str, answers: dict[str, tuple[str, str]]) -> None:
    """Answer the review calls the real stage 5 builds, and harvest them into the ledger."""
    _projects_dir, _store_dir, project, store = workspace
    review.build(project, store, batch=batch)
    queue = model_call.Queue(store, lane="review", batch=batch)
    units = {str(unit["claim_id"]): unit for unit in queue.requests()}
    for claim_id, (verdict, reason) in answers.items():
        store.append(queue.results_name, {
            "call_id": units[claim_id]["call_id"], "ok": True,
            "output": {"verdict": verdict, "reason": reason},
            "usage": {"input_tokens": 10, "output_tokens": 10}, "cost_usd": 0.00002,
            **READER})
    review.harvest(project, store, batch=batch)


def _re_extract_c1(workspace, claim: str) -> None:
    """A re-extraction of c1: same chunk, same quote, a different annotation. The old review
    no longer supports exactly this annotation, so the claim is re-reviewed for real."""
    _projects_dir, _store_dir, _project, store = workspace
    store.append("claims.jsonl", {
        "claim_id": "c1", "question_id": "Q02", "source_id": "S01", "source_class": "ACA",
        "chunk_id": "S01#c1", "stance": "SUPPORTS", "claim": claim,
        "evidence_quote": "news tone has an effect", "registry_version": 2,
        "claim_gate_version": claimgate.CLAIM_GATE_VERSION, "gate_revision": 2,
        "backend": "b", "model": "m", "harness_version": "t/1",
        "harvested_at": "2026-10-05T11:00:00+00:00"})


def _build(workspace) -> None:
    _projects_dir, _store_dir, project, store = workspace
    synthesize.build(project, store, round_name="r1")


def test_identical_hashes_give_an_empty_diff(workspace):
    """Spec B6: comparing a profile with itself reports nothing, and says so with the
    counts it holds rather than with an empty payload."""
    with _served(workspace) as (_httpd, base, store):
        flow_id = next(iter(flows.flows(store)))
        sha = _q02_sha(store)
        status, _headers, payload = _get_json(_diff_url(base, flow_id, sha, sha))
    assert status == 200
    assert payload["summary"] == {"added": 0, "removed": 0, "changed": 0}
    assert payload["added"] == [] and payload["removed"] == [] and payload["changed"] == []
    assert payload["reason"] is None
    assert payload["from"] == payload["to"]
    assert payload["counts"]["from"] == payload["counts"]["to"]


def test_a_result_appearing_is_added(workspace):
    """A review making a claim usable puts it in the profile: the diff lists it as added,
    and the per-direction counts move with it."""
    _review_claims(workspace, "rb1",
                   {"c1": ("SUPPORTED", "the quote carries the claim in context")})
    _build(workspace)
    store = workspace[3]
    sha_empty, sha_with = _q02_sha(store, which=0), _q02_sha(store)
    with _served(workspace) as (_httpd, base, _store):
        flow_id = next(iter(flows.flows(_store)))
        status, _headers, payload = _get_json(_diff_url(base, flow_id, sha_empty, sha_with))
    assert status == 200
    assert payload["summary"] == {"added": 1, "removed": 0, "changed": 0}
    assert payload["added"][0]["result_id"] == "c1"
    assert payload["added"][0]["reason"] is None
    assert payload["added"][0]["result"]["evidence_quote"] == "news tone has an effect"
    assert payload["counts"]["from"]["direction_count"] == {}
    assert payload["counts"]["to"]["direction_count"] == {"SUPPORTS": 1}
    assert payload["to"]["claim_gate_version"] == claimgate.CLAIM_GATE_VERSION


def test_a_result_losing_its_review_is_removed_with_its_reason(workspace):
    """Spec B6: the second review's recorded reason travels with the removal — the diff
    repeats what the ledger says, never invents a narrative of its own."""
    _review_claims(workspace, "rb1",
                   {"c1": ("SUPPORTED", "the quote carries the claim in context")})
    _build(workspace)
    _re_extract_c1(workspace, "News tone has a large effect.")
    _review_claims(workspace, "rb2",
                   {"c1": ("OVERSTATED", "The quote reports a mean, not predictive power.")})
    _build(workspace)
    store = workspace[3]
    sha_with, sha_without = _q02_sha(store, which=-2), _q02_sha(store)
    with _served(workspace) as (_httpd, base, served_store):
        flow_id = next(iter(flows.flows(served_store)))
        status, _headers, payload = _get_json(_diff_url(base, flow_id, sha_with, sha_without))
    assert status == 200
    assert payload["summary"] == {"added": 0, "removed": 1, "changed": 0}
    removed = payload["removed"][0]
    assert removed["result_id"] == "c1"
    assert removed["reason"] == ("review OVERSTATED: "
                                "The quote reports a mean, not predictive power.")
    assert removed["result"]["claim"] == "News tone has an effect."
    assert payload["counts"]["from"]["direction_count"] == {"SUPPORTS": 1}
    assert payload["counts"]["to"]["direction_count"] == {}


def test_a_changed_annotation_is_changed_not_replaced(workspace):
    """The same claim, re-extracted and re-reviewed as usable, is one changed result —
    its id never leaves the profile, so the diff never reads a re-wording as a removal."""
    _review_claims(workspace, "rb1",
                   {"c1": ("SUPPORTED", "the quote carries the claim in context")})
    _build(workspace)
    _re_extract_c1(workspace, "News tone has a large effect.")
    _review_claims(workspace, "rb2",
                   {"c1": ("SUPPORTED", "the changed annotation is still what the quote says")})
    _build(workspace)
    store = workspace[3]
    sha_before, sha_after = _q02_sha(store, which=-2), _q02_sha(store)
    with _served(workspace) as (_httpd, base, served_store):
        flow_id = next(iter(flows.flows(served_store)))
        status, _headers, payload = _get_json(_diff_url(base, flow_id, sha_before, sha_after))
    assert status == 200
    assert payload["summary"] == {"added": 0, "removed": 0, "changed": 1}
    changed = payload["changed"][0]
    assert changed["result_id"] == "c1"
    assert changed["fields"] == {"claim": {"from": "News tone has an effect.",
                                           "to": "News tone has a large effect."}}
    assert payload["counts"]["from"]["direction_count"] == {"SUPPORTS": 1}
    assert payload["counts"]["to"]["direction_count"] == {"SUPPORTS": 1}


def test_a_hash_not_in_the_ledger_is_404(workspace):
    """Spec B6: an unknown hash is a missing resource, never an empty diff — an unknown
    hash answering "no changes" would fabricate a comparison."""
    with _served(workspace) as (_httpd, base, store):
        flow_id = next(iter(flows.flows(store)))
        sha = _q02_sha(store)
        missing = "0" * 64
        for url in (_diff_url(base, flow_id, missing, sha),
                    _diff_url(base, flow_id, sha, missing)):
            status, payload = _error_json(url)
            assert status == 404
            assert payload["error"]["code"] == "NOT_FOUND"


def test_a_missing_end_of_the_diff_is_400(workspace):
    """Both hashes are required: a diff without either end is the caller's error, not a
    defaulted or empty comparison."""
    with _served(workspace) as (_httpd, base, store):
        flow_id = next(iter(flows.flows(store)))
        sha = _q02_sha(store)
        tail = f"/api/v1/projects/{PROJECT}/flows/{flow_id}/questions/Q02/profile-diff"
        for query in (f"from={sha}", f"to={sha}", ""):
            status, payload = _error_json(base + tail + (f"?{query}" if query else ""))
            assert status == 400
            assert payload["error"]["code"] == "BAD_REQUEST"


def test_an_unknown_question_is_404(workspace):
    """The diff belongs to a question the registry knows: an invented id names nothing."""
    with _served(workspace) as (_httpd, base, store):
        flow_id = next(iter(flows.flows(store)))
        sha = _q02_sha(store)
        status, payload = _error_json(_diff_url(base, flow_id, sha, sha, question_id="Q99"))
        assert status == 404
        assert payload["error"]["code"] == "NOT_FOUND"