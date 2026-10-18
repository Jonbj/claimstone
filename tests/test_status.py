"""D142: Crossref notices are recorded, silence is not a clean bill, and a failed lookup is its own state."""
import datetime as dt

from claimstone import net, status
from claimstone.store import Store
from tools import observe_status

WORK = {"message": {
    "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/", "content-version": "vor",
                 "start": {"date-parts": [[2021, 3, 1]]}}],
    "link": [{"URL": "https://pub.example/tdm.xml", "content-type": "text/xml", "intended-application": "text-mining"},
             {"URL": "https://pub.example/sim.pdf", "content-type": "application/pdf", "intended-application": "similarity-checking"}],
    "updated-by": [{"DOI": "10.1/notice", "type": "correction", "label": "Correction", "source": "publisher",
                    "updated": {"date-parts": [[2022, 5]]}}]}}
UPDATES = {"message": {"items": [
    {"DOI": "10.1/retraction", "update-to": [{"DOI": "10.1/A", "type": "retraction", "label": "Retraction",
                                              "source": "retraction-watch", "updated": {"date-parts": [[2023, 1, 9]]}}]},
    {"DOI": "10.1/other", "update-to": [{"DOI": "10.9/unrelated", "type": "retraction"}]}]}}


def test_a_retraction_found_through_the_updates_filter_is_withdrawing_and_a_correction_is_not():
    row = status.observation("doi:10.1/a", "10.1/a", work=WORK, updates=UPDATES, work_ok=True, updates_ok=True)
    assert row["state"] == status.NOTICE_RECORDED and row["withdrawing"] is True
    kinds = {(n["type"], n["kind"]) for n in row["notices"]}
    assert kinds == {("retraction", "withdrawing"), ("correction", "correcting")}
    assert row["notices"][0]["doi"] and all("unrelated" not in str(n) for n in row["notices"])
    assert [l["url"] for l in row["licences"]] == ["https://creativecommons.org/licenses/by/4.0/"]
    assert [l["url"] for l in row["tdm_links"]] == ["https://pub.example/tdm.xml"], "only text-mining links"


def test_silence_is_no_notice_recorded_never_a_clean_state():
    row = status.observation("doi:10.1/b", "10.1/b", work={"message": {}}, updates={"message": {"items": []}},
                             work_ok=True, updates_ok=True)
    assert row["state"] == status.NO_NOTICE_RECORDED and row["withdrawing"] is False
    assert status.STATES == (status.NOTICE_RECORDED, status.NO_NOTICE_RECORDED, status.LOOKUP_FAILED)


def test_a_lookup_that_did_not_complete_is_failed_not_silent():
    row = status.observation("doi:10.1/c", "10.1/c", work=None, updates=None, work_ok=False, updates_ok=False)
    assert row["state"] == status.LOOKUP_FAILED
    half = status.observation("doi:10.1/c", "10.1/c", work=WORK, updates=None, work_ok=True, updates_ok=False)
    assert half["state"] == status.NOTICE_RECORDED  # what was found is kept, the half that failed is flagged
    assert half["updates_ok"] is False
    quiet = status.observation("doi:10.1/c", "10.1/c", work={"message": {}}, updates=None, work_ok=True, updates_ok=False)
    assert quiet["state"] == status.LOOKUP_FAILED


def test_unknown_update_types_are_kept_and_not_dropped():
    payload = {"message": {"updated-by": [{"DOI": "10.1/x", "type": "brand_new_type"}]}}
    row = status.observation("doi:10.1/d", "10.1/d", work=payload, updates=None, work_ok=True, updates_ok=True)
    assert row["notices"][0]["kind"] == "other" and row["notices"][0]["type"] == "brand_new_type"


class Fetcher:
    def __init__(self):
        self.urls = []

    def get_json(self, url):
        self.urls.append(url)
        return (UPDATES if "filter=updates" in url else WORK), net.Outcome(url, True, 200)


def make_store(tmp_path, n=2):
    store = Store("p", base=tmp_path)
    for i in range(n):
        store.append("candidates.jsonl", {"candidate_key": f"doi:10.1/x{i}"})
    store.append("candidates.jsonl", {"candidate_key": "title:no doi"})
    return store


def test_preview_counts_two_requests_per_doi_and_makes_none(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAIMSTONE_CONTACT_EMAIL", "a@b.example")
    make_store(tmp_path)
    summary = observe_status.run("p", store_base=tmp_path)
    assert summary["dois_pending"] == 2 and summary["requests"] == 4 and summary["usd"] == 0


def test_execute_records_rows_skips_recent_ones_and_enforces_the_ceiling(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAIMSTONE_CONTACT_EMAIL", "a@b.example")
    store = make_store(tmp_path)
    fetcher = Fetcher()
    observe_status.run("p", execute=True, store_base=tmp_path, fetcher=fetcher)
    assert len(fetcher.urls) == 4 and all(u.startswith("https://api.crossref.org/") for u in fetcher.urls)
    assert len(list(store.read(status.LEDGER))) == 2
    observe_status.run("p", execute=True, store_base=tmp_path, fetcher=fetcher)
    assert len(fetcher.urls) == 4, "observed within the minimum age is not asked again"
    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=8)
    observe_status.run("p", execute=True, store_base=tmp_path, fetcher=fetcher, now=later)
    assert len(fetcher.urls) == 8
    import pytest
    with pytest.raises(ValueError, match="exceed the approved"):
        observe_status.run("p", execute=True, store_base=tmp_path, fetcher=fetcher, now=later, max_dois=1)


def test_an_absent_ledger_reads_as_nothing_observed(tmp_path):
    assert status.latest(Store("empty", base=tmp_path)) == {}
