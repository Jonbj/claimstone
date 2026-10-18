"""D143: citation edges, suggestions as counts, depth one, caps recorded, nothing written to candidates."""
import datetime as dt

import pytest

from claimstone import net, snowball
from claimstone.store import Store
from tools import observe_citation_edges as tool


def oc(field, *dois):
    return [{"oci": f"oci:{i}", field: f"omid:br/{i} doi:{d}", "creation": "2020-01-01"} for i, d in enumerate(dois)]


def test_parse_takes_the_doi_token_and_the_right_end_of_the_edge():
    cited_by = snowball.parse_edges(oc("citing", "10.2000/A", "10.3000/b", "10.1000/seed"), "10.1000/seed", snowball.CITED_BY)[0]
    assert [e["other_doi"] for e in cited_by] == ["10.2000/a", "10.3000/b"], "seed itself dropped, DOIs normalised"
    cites = snowball.parse_edges(oc("cited", "10.9000/z"), "10.1000/seed", snowball.CITES)[0]
    assert [e["other_doi"] for e in cites] == ["10.9000/z"]
    assert snowball.parse_edges({"error": "x"}, "10.1000/seed", snowball.CITES) == ([], False)


def test_a_long_answer_is_capped_and_says_so():
    many = oc("citing", *[f"10.5000/x{i}" for i in range(snowball.MAX_EDGES_PER_DIRECTION + 5)])
    edges, truncated = snowball.parse_edges(many, "10.1000/s", snowball.CITED_BY)
    assert len(edges) == snowball.MAX_EDGES_PER_DIRECTION and truncated is True


def make_store(tmp_path, n=3):
    store = Store("p", base=tmp_path)
    for i in range(n):
        store.append("candidates.jsonl", {"candidate_key": f"doi:10.1000/s{i}", "title": f"seed {i}"})
    return store


def test_a_work_linked_by_several_seeds_is_suggested_with_a_count_and_held_ones_are_not(tmp_path):
    store = make_store(tmp_path)
    for seed, direction, others in (("s0", snowball.CITED_BY, ["10.7000/hot", "10.7000/once", "10.1000/s1"]),
                                    ("s1", snowball.CITES, ["10.7000/hot"]),
                                    ("s2", snowball.CITES, ["10.7000/hot", "10.8000/two"])):
        store.append(snowball.EDGES, snowball.edge_row(f"doi:10.1000/{seed}", f"10.1000/{seed}", direction,
                                                       [{"other_doi": d} for d in others], ok=True, truncated=False))
    store.append(snowball.EDGES, snowball.edge_row("doi:10.1000/s2", "10.1000/s2", snowball.CITED_BY,
                                                   [{"other_doi": "10.8000/two"}], ok=True, truncated=False))
    got = snowball.suggestions(store, min_links=2)
    assert got[0]["doi"] == "10.7000/hot" and got[0]["links"] == 3 and got[0]["seeds"] == sorted(got[0]["seeds"])
    assert all(s["doi"] != "10.1000/s1" for s in got), "a candidate we already hold is not a suggestion"
    assert all(s["doi"] != "10.7000/once" for s in got), "below min_links"


def test_a_failed_answer_contributes_nothing(tmp_path):
    store = make_store(tmp_path, 2)
    for seed in ("s0", "s1"):
        store.append(snowball.EDGES, snowball.edge_row(f"doi:10.1000/{seed}", f"10.1000/{seed}", snowball.CITES,
                                                       [{"other_doi": "10.7000/x"}], ok=False, truncated=False))
    assert snowball.suggestions(store, min_links=1) == []


class Fetcher:
    def __init__(self):
        self.urls = []

    def get_json(self, url):
        self.urls.append(url)
        if "opencitations" in url:
            return oc("citing" if "/citations/" in url else "cited", "10.7000/hot", "10.8000/cold"), net.Outcome(url, True, 200)
        return {"results": [{"doi": "https://doi.org/10.7000/hot", "title": "A hot paper", "publication_year": 2020,
                             "primary_location": {"source": {"display_name": "J Hot"}}}]}, net.Outcome(url, True, 200)


def test_the_tool_previews_then_runs_within_its_ceiling_and_never_writes_candidates(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAIMSTONE_CONTACT_EMAIL", "a@b.example")
    store = make_store(tmp_path)
    before = list(store.read("candidates.jsonl"))
    summary = tool.run("p", store_base=tmp_path)
    assert summary["seeds_pending"] == 3 and summary["edge_requests"] == 6 and summary["usd"] == 0
    fetcher = Fetcher()
    out = tool.run("p", execute=True, store_base=tmp_path, fetcher=fetcher)
    oc_calls = [u for u in fetcher.urls if "opencitations" in u]
    assert len(oc_calls) == 6 and out["suggestions"] >= 1
    hot = snowball.suggestions(store, min_links=2)[0]
    assert hot["doi"] == "10.7000/hot" and hot["title"] == "A hot paper" and hot["links"] == 3
    assert list(store.read("candidates.jsonl")) == before
    again = Fetcher()
    tool.run("p", execute=True, store_base=tmp_path, fetcher=again)
    assert not [u for u in again.urls if "opencitations" in u], "recent seeds are not asked again"
    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=15)
    with pytest.raises(ValueError, match="exceed the approved"):
        tool.run("p", execute=True, store_base=tmp_path, fetcher=Fetcher(), now=later, max_seeds=2)
