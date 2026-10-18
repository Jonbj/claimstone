"""The search appendix: what was searched, what was not, and the stage counts (issue #11).

The appendix is a derived output of an export, so it must be computable from the frozen ledger
prefix alone and must not turn a recorded query into a claim about the literature.
"""

from __future__ import annotations

import pytest

from claimstone import export, search_appendix
from claimstone.config import load_project
from claimstone.scope import Selector
from claimstone.store import Store

PROJECT = "projects/example-news-and-returns"

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _query(**over):
    row = {
        "query_id": "q1", "round": "r1", "source_api": "openalex", "topic_id": "T02",
        "query": "news sentiment", "per_query": 25, "discovery_version": 5,
        "ok": True, "failure_class": None, "detail": "", "returned": 25,
        "total_available": 1055, "depth_capped": True, "next_cursor": None,
        "completed_at": "2026-10-18T10:00:00+00:00",
        "page_budget": 2, "pages_requested": 2, "stop_reason": "PAGE_BUDGET",
        "page_failures": [],
    }
    row.update(over)
    return row


def _request(**over):
    row = {
        "event": "validated_response", "purpose": "discovery", "round": "r1",
        "source_api": "openalex", "topic_id": "T02", "query": "news sentiment",
        "raw_sha256": HASH_A, "http_status": 200, "fetch_version": 8,
        "recorded_at": "2026-10-18T09:59:00+00:00",
    }
    row.update(over)
    return row


def _candidate(key, **over):
    row = {"candidate_key": key, "round": "r1", "source_class": "ACA",
           "source_id": key, "channel": "keyword", "title": key}
    row.update(over)
    return row


def _acquisition(key, **over):
    row = {"candidate_key": key, "round": "r1", "acquired": True,
           "source_id": key, "source_class": "ACA"}
    row.update(over)
    return row


def _render(store, *, round_name="r1", manifest_only=False):
    return search_appendix.render(
        load_project(PROJECT), store, Selector(round_name, manifest_only)).decode("utf-8")


def test_each_query_is_named_with_its_provider_cap_and_date(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("queries.jsonl", _query())
    store.append("queries.jsonl", _query(
        query_id="q2", source_api="crossref", topic_id="T01", query="returns OR momentum",
        per_query=50, returned=12, total_available=None, depth_capped=None,
        completed_at="2026-10-18T11:00:00+00:00"))
    text = _render(store)
    assert "news sentiment" in text
    assert "returns OR momentum" in text
    assert "| openalex | T02 | news sentiment | 25 |" in text
    assert "| crossref | T01 | returns OR momentum | 50 |" in text
    assert "2026-10-18T10:00:00+00:00" in text
    assert "2026-10-18T11:00:00+00:00" in text


def test_payload_hashes_come_from_the_matching_discovery_requests_only(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("queries.jsonl", _query())
    store.append("requests.jsonl", _request())
    store.append("requests.jsonl", _request(
        raw_sha256=HASH_B, recorded_at="2026-10-18T09:59:30+00:00"))
    # Another purpose with the same query context is not a search payload.
    store.append("requests.jsonl", _request(
        event="response", purpose="acquisition", raw_sha256=HASH_C))
    text = _render(store)
    assert f"sha256:{HASH_A}" in text
    assert f"sha256:{HASH_B}" in text
    assert f"sha256:{HASH_C}" not in text


def test_the_appendix_says_when_pages_omit_further_provider_hits(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("queries.jsonl", _query())
    text = _render(store)
    assert "further provider hits" in text
    assert "news sentiment" in text
    assert "PAGE_BUDGET" in text


def test_failed_queries_and_failed_pages_are_listed(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("queries.jsonl", _query(
        query_id="q3", ok=False, failure_class="SERVER_ERROR", detail="status 500",
        returned=0, total_available=None, depth_capped=None,
        stop_reason="PAGE_FAILED",
        page_failures=[{"page": 2, "failure_class": "SERVER_ERROR",
                        "detail": "status 500"}]))
    text = _render(store)
    assert "SERVER_ERROR" in text
    assert "status 500" in text
    assert "page 2" in text


def test_another_rounds_queries_are_not_in_this_appendix(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("queries.jsonl", _query())
    store.append("queries.jsonl", _query(
        query_id="q4", round="r2", query="a different round"))
    text = _render(store)
    assert "news sentiment" in text
    assert "a different round" not in text


def test_a_manifest_only_flow_claims_no_search(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("queries.jsonl", _query())
    text = _render(store, manifest_only=True)
    assert "manifest-only" in text.lower()
    assert "news sentiment" not in text


def test_stage_denominators_are_row_counts_not_a_result(tmp_path):
    store = Store("t", base=tmp_path)
    for key in ("c1", "c2", "c3"):
        store.append("candidates.jsonl", _candidate(key))
    store.append("acquisitions.jsonl", _acquisition("c1"))
    store.append("chunks.jsonl", {"chunk_id": "k1-chunk", "source_id": "c1",
                                  "generation_sha256": "g1", "text": "a verified quote"})
    store.append("documents.jsonl", {"source_id": "c1", "fulltext_confirmed": True,
                                     "chunk_ids": ["k1-chunk"],
                                     "generation_sha256": "g1"})
    store.append("claims.jsonl", {"claim_id": "k1", "source_id": "c1",
                                  "source_class": "ACA", "question_id": "Q01",
                                  "chunk_id": "k1-chunk"})
    store.append("rejections.jsonl", {"claim_id": "k2", "source_id": "c1",
                                      "source_class": "ACA", "failure": "NO_QUOTE",
                                      "chunk_id": "k1-chunk"})
    text = _render(store)
    assert "| candidates found | 3 |" in text
    assert "| acquisition attempted | 1 |" in text
    assert "| obtained | 1 |" in text
    assert "| claims accepted | 1 |" in text
    assert "| claims rejected | 1 |" in text
    assert "not a result" in text
    assert "does not pool evidence or count votes" in text


def test_the_appendix_is_deterministic(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("queries.jsonl", _query())
    store.append("requests.jsonl", _request())
    first = _render(store)
    second = _render(store)
    assert first == second


def test_every_export_carries_the_appendix(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("queries.jsonl", _query())
    outputs = export._compute_outputs(
        load_project(PROJECT), store, Selector("r1", False),
        {"flow_id": "f" * 64, "binding": {"selector": {"round": "r1"}}})
    assert search_appendix.OUTPUT in outputs
    assert b"news sentiment" in outputs[search_appendix.OUTPUT]
