"""D155: the PubMed searcher is two E-utilities requests, opt-in, and never carries a key in a URL."""
import pytest

from claimstone import classify, discover, net, provider_limits, searchers
from claimstone.config import SourceClass, load_project
from claimstone.store import Store
from tests.fakes import FakeFetcher

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"

ESEARCH_PAYLOAD = {"esearchresult": {"count": "2", "retmax": "2", "idlist": ["111", "222"]}}
ESUMMARY_PAYLOAD = {"result": {
    "uids": ["111", "222"],
    "111": {
        "uid": "111", "pubdate": "2019 Mar 15", "source": "J Mood",
        "fulljournalname": "Journal of Mood and Affect",
        "title": "Exercise and mood.",
        "elocationid": "doi: 10.1000/XYZ",
        "articleids": [
            {"idtype": "pubmed", "id": "111"},
            {"idtype": "doi", "id": "10.1000/XYZ"},
            {"idtype": "pmc", "id": "PMC9"},
        ],
        "pubtype": ["Journal Article", "Review"],
        "authors": [{"name": "Smith JA"}, {"name": "Patel R"}],
    },
    "222": {
        "uid": "222", "pubdate": "2024", "source": "medRxiv",
        "fulljournalname": "medRxiv", "title": "A preprint",
        "articleids": [{"idtype": "pubmed", "id": "222"}],
        "pubtype": ["Preprint"],
    },
}}


@pytest.fixture(autouse=True)
def _contact(monkeypatch):
    monkeypatch.setenv("CLAIMSTONE_CONTACT_EMAIL", "research@example.org")


def _fetcher():
    return FakeFetcher(json_pages={ESEARCH: ESEARCH_PAYLOAD, ESUMMARY: ESUMMARY_PAYLOAD})


class FailingFetcher:
    """Answers the first URL, then returns the given outcome for the second."""

    def __init__(self, second, *, first=ESEARCH_PAYLOAD):
        self.payloads = iter([first, second])
        self.urls = []

    def get_json(self, url):
        self.urls.append(url)
        try:
            payload = next(self.payloads)
        except StopIteration:
            return None, net.Outcome(url, False, 404, net.NOT_FOUND)
        if isinstance(payload, net.Outcome):
            return None, payload
        return payload, net.Outcome(url, True, 200)


def test_two_requests_identify_the_tool_and_the_contact():
    fetcher = _fetcher()
    rows = list(searchers.search_pubmed(fetcher, "exercise depression", "T1"))
    assert len(fetcher.calls) == 2
    search, summary = fetcher.calls
    assert search.startswith(ESEARCH)
    assert "db=pubmed" in search and "retmode=json" in search and "retmax=25" in search
    assert "term=exercise+depression" in search
    assert "tool=claimstone" in search and "email=research%40example.org" in search
    assert summary.startswith(ESUMMARY)
    assert "db=pubmed" in summary and "id=111%2C222" in summary
    assert "retmode=json" in summary
    assert "tool=claimstone" in summary and "email=research%40example.org" in summary
    assert len(rows) == 2


def test_rows_carry_pubmed_identifiers_the_journal_and_the_pubtype_list():
    first, second = list(searchers.search_pubmed(_fetcher(), "q", "T1"))
    assert first["candidate_key"] == "doi:10.1000/xyz"
    assert first["title"] == "Exercise and mood"
    assert first["doi"] == "10.1000/xyz"
    assert first["year"] == 2019
    assert first["venue"] == "Journal of Mood and Affect"
    # Several publication types joined the way Europe PMC joins them, so one predicate reads both.
    assert first["venue_type"] == "Journal Article; Review"
    assert first["url"] == "https://doi.org/10.1000/xyz"
    assert first["source_api"] == "pubmed"
    assert first["pubmed_id"] == "111" and first["pmcid"] == "PMC9"
    # E-utilities reports a PubMed record, not a licence: a PMC id is a copy, not an OA grant.
    assert first["is_oa"] is None and first["citations"] is None
    assert first["authors"] == ["Smith JA", "Patel R"] and second["authors"] == []
    assert second["candidate_key"].startswith("title:a preprint")
    assert second["url"] == "https://pubmed.ncbi.nlm.nih.gov/222/"
    assert second["venue"] == "medRxiv" and second["venue_type"] == "Preprint"
    assert second["pmcid"] is None


def test_an_empty_search_is_not_a_failure_and_opens_no_second_request():
    empty = {"esearchresult": {"count": "0", "retmax": "0", "idlist": []}}
    fetcher = FakeFetcher(json_pages={ESEARCH: empty})
    assert list(searchers.search_pubmed(fetcher, "q", "T1")) == []
    assert len(fetcher.calls) == 1


def test_each_failed_request_is_a_named_failure_never_an_empty_success():
    bad = net.Outcome("u", False, 503, net.SERVER_ERROR)
    with pytest.raises(searchers.SearchError) as caught:
        list(searchers.search_pubmed(FailingFetcher(bad, first=bad), "q", "T"))
    assert caught.value.failure == net.SERVER_ERROR
    # A failed esummary must not collapse into "the query found nothing".
    with pytest.raises(searchers.SearchError) as caught:
        list(searchers.search_pubmed(FailingFetcher(bad), "q", "T"))
    assert caught.value.failure == net.SERVER_ERROR


def test_a_malformed_envelope_is_invalid_not_empty():
    with pytest.raises(searchers.SearchError) as caught:
        list(searchers.search_pubmed(FailingFetcher(None, first={}), "q", "T"))
    assert caught.value.failure == "INVALID_SEARCH_RESPONSE"
    with pytest.raises(searchers.SearchError) as caught:
        list(searchers.search_pubmed(FailingFetcher({}), "q", "T"))
    assert caught.value.failure == "INVALID_SEARCH_RESPONSE"


def test_an_api_key_is_never_read_because_it_would_have_to_travel_in_the_url(monkeypatch):
    # requests.jsonl records URLs unredacted, so a key in a query parameter would enter an
    # append-only ledger. The unkeyed 3 req/s limit is the one this adapter stays under.
    monkeypatch.setenv("NCBI_API_KEY", "secret-key-must-not-appear")
    fetcher = _fetcher()
    list(searchers.search_pubmed(fetcher, "q", "T1"))
    assert all("api_key" not in url and "secret-key" not in url for url in fetcher.calls)


def test_ncbi_pacing_is_the_unkeyed_three_per_second_limit():
    assert provider_limits.INTERVALS["eutils.ncbi.nlm.nih.gov"] == pytest.approx(0.34)


def test_it_is_registered_but_not_a_default():
    assert "pubmed" in searchers.SEARCHERS and "pubmed" not in searchers.DEFAULT_APIS
    assert searchers.DEFAULT_APIS == ("openalex", "crossref", "arxiv")
    assert searchers._limit_kw("pubmed") == "retmax"
    # The adapter adds no default, so this change does not move DISCOVERY_VERSION (D141, D149).
    # The constant itself is asserted where a change does move it.


def test_a_project_classifies_it_by_declared_rules_not_by_the_engine():
    klass = SourceClass(id="REVIEWED", name="r", weight_hint="",
                        assign_when={"pubmed_type": ["Review"]})
    row = next(iter(searchers.search_pubmed(_fetcher(), "q", "T")))
    assert classify.classify(row, [klass]) == "REVIEWED"
    assert classify.classify({**row, "venue_type": "Journal Article"}, [klass]) is None
    assert classify.classify({**row, "source_api": "europepmc"}, [klass]) is None


def test_discovery_records_the_pubmed_identifier_on_the_query_hit(tmp_path):
    project = load_project("projects/example-news-and-returns")
    store = Store("t", base=tmp_path)
    terms = next(t.terms for t in project.topics if t.id == "T02")
    result = discover.run(project, store, _fetcher(), apis=("pubmed",), topics=("T02",))
    assert result["completed_queries"] == len(terms)
    hits = list(store.read("query_hits.jsonl"))
    assert {row["provider_id"] for row in hits} == {"111", "222"}
    assert {row["source_api"] for row in hits} == {"pubmed"}
    assert all(row["query_hash"] for row in store.read("candidates.jsonl"))
