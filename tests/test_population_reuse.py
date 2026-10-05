"""Metadata scope and byte reuse must not inflate the acquired population."""
from dataclasses import replace
import hashlib
from pathlib import Path
import pytest
import yaml

from claimstone import acquire, discover, population
from claimstone.config import ConfigError, load_project, ManifestEntry
from claimstone.store import Store
from tests.fakes import FakeFetcher
from tests.test_searchers import OPENALEX, OPENALEX_PAYLOAD


POLICY = {"version": 1, "declared_at": "2026-09-28", "rationale": "fixed metadata hosts",
          "hosts": ["archive.example"], "source_apis": [], "venues": []}


def configured(tmp_path, policy=POLICY):
    import shutil
    root = tmp_path / "project"
    shutil.copytree("projects/example-news-and-returns", root)
    path = root / "sources.yaml"
    raw = yaml.safe_load(path.read_text()); raw["population"] = policy
    path.write_text(yaml.safe_dump(raw))
    return load_project(root)


def test_discovery_keeps_rejected_metadata_outside_denominator(tmp_path):
    project = configured(tmp_path)
    rows = OPENALEX_PAYLOAD["results"]
    first = dict(rows[0]); second = dict(rows[0]); second["doi"] = "https://doi.org/10.1234/other"
    first["primary_location"] = {"landing_page_url": "https://archive.example/a", "source": {"type": "journal"}}
    second["primary_location"] = {"landing_page_url": "https://archive.example.evil/a", "source": {"type": "journal"}}
    store = Store("t", base=tmp_path)
    fetched = FakeFetcher(json_pages={OPENALEX: {"results": [first, second]}})
    result = discover.run(project, store, fetched, topics=["T02"], apis=["openalex"], round_name="r")
    candidates = list(store.read("candidates.jsonl"))
    observations = list(store.read("discovery_population.jsonl"))
    assert len(candidates) == 1 and candidates[0]["url"] == "https://archive.example/a"
    assert result["outside_population"] > 0
    assert any(not r["admitted"] for r in observations)
    assert population.decide(project.population, {"url": "https://archive.example/a", "acquired": False})[0]
    assert not population.decide(project.population, {"url": "https://other.example/a", "acquired": True})[0]


def test_policy_cannot_change_or_disappear_in_a_held_round(tmp_path):
    store = Store("t", base=tmp_path)
    p = population.validate(POLICY)
    population.check_round(store, p, "r")
    with pytest.raises(ValueError, match="changed"):
        population.check_round(store, {**p, "version": 2}, "r")
    with pytest.raises(ValueError, match="removed"):
        population.check_round(store, {}, "r")
    population.check_round(store, {**p, "version": 2}, "new-round")


def test_no_retrofit_to_existing_candidate_denominator(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {"candidate_key": "k", "round": "r"})
    with pytest.raises(ValueError, match="retrofit"):
        population.check_round(store, population.validate(POLICY), "r")


def test_malformed_external_url_cannot_match_a_declared_host():
    assert not population.decide(population.validate(POLICY), {"url": "https://[bad"})[0]


@pytest.mark.parametrize("policy", [dict(POLICY, host=["a"]), dict(POLICY, version=True),
    dict(POLICY, declared_at="yesterday"), dict(POLICY, hosts=["*.edu"]),
    dict(POLICY, hosts=[]), dict(POLICY, hosts=["https://example.org"]),
    dict(POLICY, rationale="")])
def test_invalid_population_refuses_before_any_request(tmp_path, policy):
    with pytest.raises(ConfigError, match="population"):
        configured(tmp_path, policy)


def test_seed_and_citations_use_the_same_frozen_policy(tmp_path):
    project = configured(tmp_path); store = Store("t", base=tmp_path)
    entry = ManifestEntry("S1", "ACA", "pdf", "https://verified-author.example/a.pdf", "Known seed")
    discover.import_manifest(store, [entry], round_name="r", population_policy=project.population)
    store.append("references.jsonl", {"key": "title:ref", "title": "A reference that exceeds required title length",
        "year": 2020, "citations_in_corpus": 3, "cited_by": ["S1"], "doi": "10.1234/ref"})
    result = discover.run_citations(project, store, round_name="r")
    assert result["new"] == 0 and result["outside_population"] == 1
    assert len(list(store.read("candidates.jsonl"))) == 1


def test_secondhand_promotion_cannot_bypass_population(tmp_path):
    from tests.test_discover import rejection
    project = configured(tmp_path); store = Store("t", base=tmp_path)
    store.append("references.jsonl", {"key": "title:r squared", "title": "R-squared",
        "authors": ["Roll"], "year": 1988, "doi": "10.1234/outside", "citations_in_corpus": 1})
    store.append("rejections.jsonl", rejection("Roll (1988) found little difference."))
    result = discover.promote_contested(project, store, round_name="r")
    assert result["promoted"] == 0 and result["outside_population"] == 1
    assert not list(store.read("candidates.jsonl"))


def test_citation_retry_preserving_old_round_cannot_apply_new_policy(tmp_path):
    project = configured(tmp_path); store = Store("t", base=tmp_path)
    population.check_round(store, population.validate({**POLICY, "version": 2}), "old")
    store.append("candidates.jsonl", {"candidate_key": "title:ref", "round": "old",
        "resolution": "NOT_ATTEMPTED"})
    store.append("references.jsonl", {"key": "title:ref", "title": "A reference that exceeds required title length",
        "year": 2020, "citations_in_corpus": 3, "doi": "10.1234/ref"})
    fetched = FakeFetcher()
    with pytest.raises(ValueError, match="changed"):
        discover.run_citations(project, store, fetcher=fetched, round_name="new")
    assert not fetched.calls


def origin(tmp_path):
    payload = b"%PDF-1.4\n" + b"x" * 11000 + b"\n%%EOF"
    path = tmp_path / "original.pdf"; path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    return {"acquired": True, "candidate_key": "old", "url": "https://archive.example/a.pdf",
            "stored_path": str(path), "sha256": digest, "content_type": "application/pdf",
            "licence": None, "fetched_at": "2026-09-20T10:00:00+00:00", "source_class": "ACA"}


def reuse(tmp_path, row, **kw):
    return acquire.reuse_cached(Store("new", base=tmp_path),
        {"candidate_key": "new", "source_id": "S1", "source_class": "WP", "url": row["url"]}, row,
        origin_store="old", expected_sha256=row["sha256"], campaign="verified-reuse",
        identity={"document_title": "Verified primary title", "checked_by": "test reference"}, **kw)


def test_reuse_rechecks_gate_keeps_class_and_records_no_http(tmp_path):
    old = origin(tmp_path); original = Path(old["stored_path"]).read_bytes()
    row = reuse(tmp_path, old)
    assert row["acquired"] and row["source_class"] == "WP" and row["licence"] is None
    assert row["provenance"] == "store-reuse" and row["attempts"] == []
    assert row["fetched_at"] == old["fetched_at"] and row["reused_at"]
    assert row["reuse_origin"]["sha256"] == old["sha256"]
    assert Path(old["stored_path"]).read_bytes() == original
    reuse(tmp_path, old)
    assert len(list(Store("new", base=tmp_path).read("acquisitions.jsonl"))) == 1


def test_reuse_gate_failure_is_not_obtained_but_bytes_are_retained(tmp_path):
    row = reuse(tmp_path, origin(tmp_path), thresholds={"min_pdf_bytes": 50000})
    assert not row["acquired"] and row["failure_class"] == "TOO_SHORT"
    assert row["sha256"] is None and Path(row["stored_path"]).is_file()


def test_hash_mismatch_appends_nothing(tmp_path):
    old = origin(tmp_path); Path(old["stored_path"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash"):
        reuse(tmp_path, old)
    assert not list(Store("new", base=tmp_path).read("acquisitions.jsonl"))
