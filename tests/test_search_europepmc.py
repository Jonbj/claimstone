"""D141: the Europe PMC searcher turns one saved payload into candidate rows and stays opt-in."""
import pytest

from claimstone import net, searchers, classify
from claimstone.config import SourceClass

PAYLOAD = {"resultList": {"result": [
    {"id": "123", "source": "MED", "pmid": "123", "pmcid": "PMC9", "doi": "10.1000/XYZ", "title": "Exercise and mood.",
     "pubYear": "2019", "journalTitle": "J Mood", "pubType": "journal article", "isOpenAccess": "Y", "citedByCount": 7,
     "authorString": "Smith JA, Patel R, Wong"},
    {"id": "PPR1", "source": "PPR", "title": "A preprint", "pubYear": "2024", "isOpenAccess": "N", "pubType": "preprint"},
]}}


class Fetcher:
    def __init__(self, payload=PAYLOAD, outcome=None):
        self.payload, self.outcome, self.urls = payload, outcome or net.Outcome("u", True, 200), []

    def get_json(self, url):
        self.urls.append(url)
        return self.payload, self.outcome


def test_rows_carry_identifiers_open_access_and_the_pubtype_as_venue_type():
    fetcher = Fetcher()
    rows = list(searchers.search_europepmc(fetcher, "exercise depression", "T1"))
    assert fetcher.urls[0].startswith("https://www.ebi.ac.uk/europepmc/webservices/rest/search?")
    assert "pageSize=25" in fetcher.urls[0] and "resultType=lite" in fetcher.urls[0]
    first, second = rows
    assert first["candidate_key"] == "doi:10.1000/xyz" and first["title"] == "Exercise and mood"
    assert first["year"] == 2019 and first["venue"] == "J Mood" and first["venue_type"] == "journal article"
    assert first["is_oa"] is True and first["citations"] == 7 and first["pmcid"] == "PMC9"
    assert first["source_api"] == "europepmc" and first["europepmc_id"] == "MED:123"
    assert first["url"] == "https://doi.org/10.1000/xyz"
    assert first["authors"] == ["Smith JA", "Patel R", "Wong"], "one authorString field, split into names (D158)"
    assert second["is_oa"] is False and second["url"] == "https://europepmc.org/article/PPR/PPR1"
    assert second["authors"] == []


def test_a_failed_or_malformed_response_is_a_named_failure_never_an_empty_success():
    with pytest.raises(searchers.SearchError):
        list(searchers.search_europepmc(Fetcher({}, net.Outcome("u", True, 200)), "q", "T"))
    bad = net.Outcome("u", False, 503, net.SERVER_ERROR)
    with pytest.raises(searchers.SearchError) as caught:
        list(searchers.search_europepmc(Fetcher(None, bad), "q", "T"))
    assert caught.value.failure == net.SERVER_ERROR


def test_it_is_registered_but_not_a_default():
    assert "europepmc" in searchers.SEARCHERS and "europepmc" not in searchers.DEFAULT_APIS
    assert searchers.DEFAULT_APIS == ("openalex", "crossref", "arxiv")
    assert searchers._limit_kw("europepmc") == "page_size"


def test_a_project_classifies_it_by_declared_rules_not_by_the_engine():
    klass = SourceClass(id="REVIEWED", name="r", weight_hint="", assign_when={"europepmc_type": ["journal article"]})
    row = next(iter(searchers.search_europepmc(Fetcher(), "q", "T")))
    assert classify.classify(row, [klass]) == "REVIEWED"
    other = SourceClass(id="PRE", name="p", weight_hint="", assign_when={"source_api": ["europepmc"]})
    assert classify.classify(row, [other]) == "PRE"


def test_a_joined_publication_type_matches_on_any_one_part():
    klass = SourceClass(id="REVIEWED", name="r", weight_hint="", assign_when={"europepmc_type": ["journal article"]})
    joined = {"source_api": "europepmc", "venue_type": "review; journal article; research support, non-u.s. gov't"}
    assert classify.classify(joined, [klass]) == "REVIEWED"
    assert classify.classify(joined | {"venue_type": "preprint"}, [klass]) is None
    assert classify.classify(joined | {"source_api": "openalex"}, [klass]) is None, "only for rows from Europe PMC"
