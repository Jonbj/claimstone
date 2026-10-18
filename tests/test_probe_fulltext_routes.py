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
        store.append("candidates.jsonl", {"candidate_key": f"doi:10.1000/x{i}", "title": f"t{i}"})
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
    assert probe.openalex_url("10.1000/x").startswith("https://api.openalex.org/works/doi:10.1000/x?select=")


def test_the_core_lookup_counts_only_an_exact_doi_and_is_bounded(tmp_path):
    store = make_store(tmp_path, 3)
    store.append("acquisitions.jsonl", {"candidate_key": "doi:10.1000/x0", "acquired": True})

    class Core:
        def __init__(self):
            self.urls = []

        def get_json(self, url):
            self.urls.append(url)
            return {"results": [{"doi": "10.1000/X1", "downloadUrl": "https://r.edu/a.pdf", "id": 1},
                                {"doi": "10.9000/other", "downloadUrl": "https://r.edu/b.pdf"}]}, net.Outcome(url, True, 200)

    preview = probe.run_core("p", store_base=tmp_path)
    assert preview["lookups_pending"] == 2, "an obtained candidate is not looked up"
    fetcher = Core()
    probe.run_core("p", execute=True, store_base=tmp_path, fetcher=fetcher)
    assert len(fetcher.urls) == 2 and all(u.startswith("https://api.core.ac.uk/") for u in fetcher.urls)
    rows = [r for r in store.read(probe.LEDGER) if r["service"] == "core"]
    first = next(r for r in rows if r["candidate_key"] == "doi:10.1000/x1")
    assert first["summary"]["exact"] == 1 and first["summary"]["copies"][0]["downloadUrl"] == "https://r.edu/a.pdf"
    probe.run_core("p", execute=True, store_base=tmp_path, fetcher=fetcher)
    assert len(fetcher.urls) == 2, "a recorded lookup is not asked again"


def test_two_unparseable_dois_are_not_the_same_work():
    assert probe.summarize_core({"results": [{"doi": "garbage", "downloadUrl": "https://r.edu/a.pdf"}]}, "also garbage")["exact"] == 0
