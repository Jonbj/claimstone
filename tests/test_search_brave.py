"""D159: a web search is a discovery channel only through a DOI that OpenAlex confirms."""
import pytest

from claimstone import net, searchers
from tests.fakes import FakeFetcher

BRAVE = "https://api.search.brave.com/res/v1/web/search"
OA = "https://api.openalex.org/works/doi:"

PAGE = {"web": {"results": [
    {"url": "https://link.springer.com/article/10.1007/s00737-026-01752-9", "title": "Isolated physical activity | Springer"},
    {"url": "https://www.frontiersin.org/articles/10.3389/fpsyt.2021.705559/full", "title": "The Effects ... | Frontiers"},
    {"url": "https://example.com/blog/exercise-and-mood", "title": "10 tips for a better mood"},
    {"url": "https://doi.org/10.9999/unknown-work", "title": "Not in OpenAlex"},
    {"url": "https://link.springer.com/article/10.1007/s00737-026-01752-9#Abs1", "title": "same again"},
]}}


def work(doi, title):
    return {"id": "https://openalex.org/W1", "doi": f"https://doi.org/{doi}", "title": title,
            "publication_year": 2026, "primary_location": {"landing_page_url": f"https://doi.org/{doi}",
            "source": {"display_name": "A Journal", "type": "journal"}}, "open_access": {"is_oa": True},
            "cited_by_count": 3}


def fetcher():
    return FakeFetcher(json_pages={
        BRAVE: PAGE,
        OA + "10.1007/s00737-026-01752-9": work("10.1007/s00737-026-01752-9", "Isolated physical activity programs"),
        OA + "10.3389/fpsyt.2021.705559": work("10.3389/fpsyt.2021.705559", "The Effects and Mechanisms of Exercise"),
    })


@pytest.mark.parametrize("url,doi", [
    ("https://link.springer.com/article/10.1007/s00737-026-01752-9", "10.1007/s00737-026-01752-9"),
    ("https://www.frontiersin.org/articles/10.3389/fpsyt.2021.705559/full", "10.3389/fpsyt.2021.705559"),
    ("https://x.org/doi/pdf/10.1016/j.jad.2016.03.063.pdf", "10.1016/j.jad.2016.03.063"),
    ("https://example.com/blog/exercise-and-mood", None),
    ("https://pmc.ncbi.nlm.nih.gov/articles/PMC11298280/", None)])
def test_a_doi_is_read_from_the_path_without_a_page_suffix(url, doi):
    assert searchers.doi_from_url(url) == doi


def test_only_results_with_a_doi_openalex_confirms_become_candidates_and_carry_openalexs_metadata():
    f = fetcher()
    rows = list(searchers.search_brave(f, "exercise depression", "T1"))
    assert [r["doi"] for r in rows] == ["10.1007/s00737-026-01752-9", "10.3389/fpsyt.2021.705559"]
    first = rows[0]
    assert first["title"] == "Isolated physical activity programs" and first["venue_type"] == "journal"
    assert first["source_api"] == "openalex" and first["channel"] == searchers.CHANNEL_WEB
    assert first["found_by"] == "brave" and first["web_title"].endswith("Springer")
    # one search, then one lookup per distinct DOI: the blog was never looked up, the repeat was not asked twice
    assert len(f.calls) == 1 + 3 and sum(c.startswith(OA) for c in f.calls) == 3


def test_a_doi_that_is_already_a_candidate_costs_no_lookup():
    f = fetcher()
    rows = list(searchers.search_brave(f, "x", "T1", known_dois={"10.1007/s00737-026-01752-9"}))
    assert [r["doi"] for r in rows] == ["10.3389/fpsyt.2021.705559"]
    assert not any("s00737" in c for c in f.calls[1:])


def test_lookups_are_capped():
    page = {"web": {"results": [{"url": f"https://doi.org/10.1000/w{i}", "title": "t"} for i in range(30)]}}
    f = FakeFetcher(json_pages={BRAVE: page})
    list(searchers.search_brave(f, "x", "T1", max_lookups=4))
    assert sum(c.startswith(OA) for c in f.calls) == 4


def test_a_failed_search_is_a_search_error_and_never_an_empty_answer():
    class Down:
        def get_json(self, url):
            return None, net.Outcome(url, False, 429, "RATE_LIMITED", "slow down")
    with pytest.raises(searchers.SearchError) as caught:
        list(searchers.search_brave(Down(), "x", "T1"))
    assert caught.value.failure == "RATE_LIMITED"


def test_it_is_opt_in_and_registered():
    assert "brave" not in searchers.DEFAULT_APIS
    assert searchers.SEARCHERS["brave"] is searchers.search_brave
    assert searchers._limit_kw("brave") == "count"


def test_through_discovery_a_web_found_work_is_a_classified_candidate_with_its_provenance(tmp_path):
    from claimstone import discover
    from claimstone.config import load_project
    from claimstone.store import Store

    project = load_project("projects/example-news-and-returns")
    store = Store("t", base=tmp_path)
    term = next(t for t in project.topics if t.id == "T02").terms[0]
    summary = discover.run(project, store, fetcher(), apis=("brave",), topics=("T02",), terms=[term])
    rows = list(store.read("candidates.jsonl"))
    assert summary["new"] == 2 and summary["final"] is True
    assert {r["candidate_key"] for r in rows} == {"doi:10.1007/s00737-026-01752-9", "doi:10.3389/fpsyt.2021.705559"}
    assert all(r["source_class"] == "ACA" and r["found_by"] == "brave" and r["round"] == "routine" for r in rows)
    # a second run finds the same DOIs known: no duplicate row, and no lookup is repeated
    again = fetcher()
    discover.run(project, store, again, apis=("brave",), topics=("T02",), terms=[term])
    assert len(list(store.read("candidates.jsonl"))) == 2
    assert [c.split("?")[0] for c in again.calls if c.startswith(OA)] == [OA + "10.9999/unknown-work"]  # only the unconfirmed one is asked again
