"""The phase-1 route probe: preview makes no request, execute is bounded and recorded, a refusal stops it."""
import json
import pytest

from claimstone import net
from claimstone.store import Store
from tools import probe_fulltext_routes as probe


class FakeFetcher:
    def __init__(self, refuse_after=None):
        self.urls, self.refuse_after = [], refuse_after

    def get_json(self, url):
        self.urls.append(url)
        if self.refuse_after is not None and len(self.urls) > self.refuse_after:
            return None, net.Outcome(url, False, 403, net.PAYWALL, "refused")
        if "europepmc" in url:
            payload = {"resultList": {"result": [{"pmcid": "PMC1", "isOpenAccess": "Y", "inEPMC": "Y",
                                                  "inPMC": "Y", "hasPDF": "Y", "license": "cc by"}]}}
        else:
            payload = {"open_access": {"is_oa": True, "oa_status": "gold"}, "locations": [{"is_oa": True}]}
        return payload, net.Outcome(url, True, 200)


def make_store(tmp_path, n=3):
    store = Store("p", base=tmp_path)
    for i in range(n):
        store.append("candidates.jsonl", {"candidate_key": f"doi:10.1/x{i}", "title": f"t{i}"})
    store.append("candidates.jsonl", {"candidate_key": "title:no doi", "title": "no doi"})
    return store


def test_preview_makes_no_request_and_counts_two_per_doi(tmp_path):
    make_store(tmp_path)
    summary = probe.run("p", store_base=tmp_path, fetcher=FakeFetcher())
    assert summary["candidates"] == 3 and summary["pending_requests"] == 6 and summary["usd"] == 0


def test_execute_records_one_row_per_service_and_is_idempotent(tmp_path):
    store = make_store(tmp_path)
    fetcher = FakeFetcher()
    probe.run("p", execute=True, store_base=tmp_path, fetcher=fetcher)
    assert len(fetcher.urls) == 6
    assert all(u.startswith(("https://www.ebi.ac.uk/", "https://api.openalex.org/")) for u in fetcher.urls)
    rows = list(store.read(probe.LEDGER))
    assert len(rows) == 6 and {r["service"] for r in rows} == {"europe_pmc", "openalex"}
    probe.run("p", execute=True, store_base=tmp_path, fetcher=fetcher)
    assert len(fetcher.urls) == 6, "a recorded pair is never asked again"


def test_a_refusal_stops_the_run(tmp_path):
    make_store(tmp_path)
    fetcher = FakeFetcher(refuse_after=2)
    summary = probe.run("p", execute=True, store_base=tmp_path, fetcher=fetcher)
    assert summary["stopped_on_refusal"]["status"] == 403
    assert len(fetcher.urls) == 3


def test_more_candidates_than_the_approved_ceiling_refuses_to_run(tmp_path):
    make_store(tmp_path, n=11)
    with pytest.raises(ValueError, match="exceed the approved"):
        probe.run("p", execute=True, store_base=tmp_path, fetcher=FakeFetcher())


def test_urls_encode_the_doi():
    assert "DOI%3A%2210.1016/j.x%28y%29%22" in probe.europe_pmc_url("10.1016/j.x(y)")
    assert probe.openalex_url("10.1/x").startswith("https://api.openalex.org/works/doi:10.1/x?select=")
