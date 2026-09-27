"""Orchestration: plan, attempt, gate, store, record. Never raises on a failed fetch."""

import datetime as _dt
import pathlib
import time

import pytest

from claimstone import acquire, fulltext, net
from claimstone.store import Store
from tests.fakes import FakeFetcher, fail, ok
from tests.test_fulltext import page, pdf

UNPAYWALL = "https://api.unpaywall.org/v2/"


def candidate(**overrides):
    base = {"candidate_key": "doi:10.1234/abc", "source_id": "S01", "source_class": "ACA",
            "doi": "10.1234/abc", "url": "https://repo.example/paper.pdf", "title": "A paper"}
    return {**base, **overrides}


def test_a_candidate_without_a_source_class_is_an_error(tmp_path):
    store = Store("t", base=tmp_path)
    with pytest.raises(acquire.MissingSourceClass):
        acquire.acquire_one(FakeFetcher(), store, candidate(source_class=None), use_apis=False)


def test_a_gated_landing_page_is_not_an_acquisition(tmp_path):
    store = Store("t", base=tmp_path)
    url = "https://publisher.example/article"
    fetcher = FakeFetcher(pages={url: ok(url, page(40, "<p>Purchase PDF</p>"), "text/html")})
    row = acquire.acquire_one(fetcher, store, candidate(url=url, doi=None), use_apis=False)
    assert row["acquired"] is False
    assert row["failure_class"] == net.LANDING
    assert row["attempts"][-1]["gate_kind"] == "LANDING_PAGE_ONLY"
    # The bytes survive a rejection, or the threshold audit is impossible later.
    kept = row["attempts"][-1]["stored_path"]
    assert kept and pathlib.Path(kept).exists()


def test_an_abstract_page_is_not_an_acquisition(tmp_path):
    store = Store("t", base=tmp_path)
    url = "https://vendor.example/research/x"
    fetcher = FakeFetcher(pages={url: ok(url, page(60), "text/html")})
    row = acquire.acquire_one(fetcher, store, candidate(url=url, doi=None), use_apis=False)
    assert row["acquired"] is False
    assert row["failure_class"] == net.ABSTRACT


def test_a_real_pdf_is_stored_under_its_hash(tmp_path):
    store = Store("t", base=tmp_path)
    url = "https://repo.example/paper.pdf"
    fetcher = FakeFetcher(pages={url: ok(url, pdf(), "application/pdf")})
    row = acquire.acquire_one(fetcher, store, candidate(), use_apis=False)
    assert row["acquired"] is True
    assert row["gate"]["kind"] == "PDF_FULLTEXT"
    assert row["gate"]["gate_version"] == fulltext.GATE_VERSION
    assert (tmp_path / "t" / "raw" / f"{row['sha256']}.pdf").exists()


def test_the_cascade_continues_past_a_403(tmp_path):
    store = Store("t", base=tmp_path)
    wall = "https://www.sciencedirect.com/science/article/pii/S03"
    open_copy = "https://repo.example/paper.pdf"
    fetcher = FakeFetcher(
        pages={wall: fail(wall, 403, net.PAYWALL), open_copy: ok(open_copy, pdf())},
        json_pages={UNPAYWALL: {
            "oa_status": "green",
            "oa_locations": [{"url_for_pdf": open_copy, "version": "acceptedVersion",
                              "license": "cc-by"}]}},
    )
    row = acquire.acquire_one(fetcher, store, candidate(url=wall))
    assert row["acquired"] is True
    assert row["provenance"] == "unpaywall"
    assert row["licence"] == "cc-by"
    # The open copy is tried first and succeeds; the wall is never reached.
    assert [a["http_status"] for a in row["attempts"]] == [200]


def test_every_attempt_is_kept_not_just_the_last(tmp_path):
    store = Store("t", base=tmp_path)
    a, b = "https://a.example/x.pdf", "https://b.example/y.pdf"
    fetcher = FakeFetcher(
        pages={a: fail(a, 404, net.NOT_FOUND), b: fail(b, 403, net.PAYWALL)},
        json_pages={UNPAYWALL: {"oa_status": "closed", "oa_locations": [{"url": a}, {"url": b}]}},
    )
    row = acquire.acquire_one(fetcher, store, candidate(url="https://doi.org/10.1234/abc"))
    assert len(row["attempts"]) >= 2
    assert {a["failure_class"] for a in row["attempts"]} == {net.NOT_FOUND, net.PAYWALL}


def test_a_candidate_with_nowhere_to_look_says_so(tmp_path):
    store = Store("t", base=tmp_path)
    row = acquire.acquire_one(
        FakeFetcher(), store, candidate(url="", doi=None, title=""), use_apis=False)
    assert row["acquired"] is False
    assert row["failure_class"] == net.NO_LOCATIONS
    assert row["attempts"] == []


def test_the_campaign_is_written_on_every_row(tmp_path):
    store = Store("t", base=tmp_path)
    url = "https://repo.example/paper.pdf"
    fetcher = FakeFetcher(pages={url: ok(url, pdf())})
    row = acquire.acquire_one(fetcher, store, candidate(), campaign="elsevier-retry",
                              use_apis=False)
    assert row["campaign"] == "elsevier-retry"


# --- Task 5: the retry policy -------------------------------------------------

def _row(failure_class, *, acquired=False, age_s=0):
    stamp = _dt.datetime.fromtimestamp(time.time() - age_s, _dt.timezone.utc)
    return {"acquired": acquired, "failure_class": failure_class,
            "fetched_at": stamp.isoformat(timespec="seconds")}


def test_a_candidate_never_tried_is_attempted():
    assert acquire.should_attempt(None, retry_classes=frozenset()) is True


def test_an_acquired_candidate_is_left_alone():
    assert acquire.should_attempt(_row(None, acquired=True), retry_classes=frozenset()) is False


def test_a_403_is_not_reattempted_without_a_named_campaign():
    assert acquire.should_attempt(_row(net.PAYWALL), retry_classes=frozenset()) is False


def test_a_403_is_reattempted_when_its_class_is_named():
    assert acquire.should_attempt(
        _row(net.PAYWALL), retry_classes=frozenset({net.PAYWALL})) is True


def test_an_abstract_page_is_terminal_too():
    assert acquire.should_attempt(_row(net.ABSTRACT), retry_classes=frozenset()) is False


def test_a_fresh_timeout_waits():
    assert acquire.should_attempt(
        _row(net.TIMEOUT, age_s=60), retry_classes=frozenset(), retry_after_s=6 * 3600) is False


def test_an_old_timeout_is_retried_on_its_own():
    assert acquire.should_attempt(
        _row(net.TIMEOUT, age_s=7 * 3600), retry_classes=frozenset(),
        retry_after_s=6 * 3600) is True


def test_an_exhausted_budget_returns_to_the_queue():
    # Transient on purpose: a source dropped because the budget ran out must come back, or a
    # blocked downloader reads as a saturated corpus.
    assert acquire.should_attempt(
        _row(net.BUDGET, age_s=7 * 3600), retry_classes=frozenset(),
        retry_after_s=6 * 3600) is True


def test_a_skipped_candidate_writes_no_row(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", {"candidate_key": "doi:10.1234/abc", **_row(net.PAYWALL)})
    rows = list(acquire.run([candidate()], store, FakeFetcher(), use_apis=False))
    assert rows == []
    assert len(list(store.read("acquisitions.jsonl"))) == 1


def test_attempt_no_increments_across_campaigns(tmp_path):
    store = Store("t", base=tmp_path)
    url = "https://repo.example/paper.pdf"
    fetcher = FakeFetcher(pages={url: ok(url, pdf())})
    first = list(acquire.run([candidate()], store, fetcher, use_apis=False))
    assert first[0]["attempt_no"] == 1
    # A retry campaign that names the class re-attempts even a terminal failure.
    store.append("acquisitions.jsonl", {**first[0], "acquired": False,
                                       "failure_class": net.PAYWALL})
    again = list(acquire.run([candidate()], store, fetcher, use_apis=False,
                             campaign="elsevier", retry_classes=frozenset({net.PAYWALL})))
    assert again[0]["attempt_no"] == 2
    assert again[0]["campaign"] == "elsevier"


def test_one_unclassified_candidate_does_not_end_the_sweep(tmp_path):
    """The refusal is right and killing the run is not — the same defect shape as an unreadable artifact
    ending a normalize sweep. Reproduced on the real store: 34 fetchable citation candidates and the run
    died on the first of the 16 that carry no class, having acquired none of them.

    `acquire_one` still raises, because a caller handing it an unclassified candidate has made a mistake.
    The sweep catches it, records it, and moves on.
    """
    store = Store("t", base=tmp_path)
    candidates = [
        {"candidate_key": "title:no class here at all", "url": "https://x.example/a", "title": "A"},
        {"candidate_key": "doi:10.1/ok", "url": "https://x.example/b", "title": "B",
         "source_class": "ACA"},
    ]
    fetcher = FakeFetcher(pages={"https://x.example/b": ok("https://x.example/b", pdf())})
    rows = list(acquire.run(candidates, store, fetcher, use_apis=False))

    assert [r["candidate_key"] for r in rows] == ["title:no class here at all", "doi:10.1/ok"]
    assert rows[0]["acquired"] is False
    assert rows[0]["failure_class"] == "UNCLASSIFIED"
    assert rows[1]["acquired"] is True
    # Recorded, so the refusal is countable rather than a crash somebody has to read a traceback for.
    assert "invariant 6" in rows[0]["notes"]


def test_an_unclassified_refusal_is_not_retried_as_though_a_host_had_refused_us(tmp_path):
    """It is terminal until the candidate changes, and a host budget has nothing to do with it."""
    store = Store("t", base=tmp_path)
    candidate = {"candidate_key": "title:no class", "url": "https://x.example/a", "title": "A"}
    list(acquire.run([candidate], store, FakeFetcher(), use_apis=False))
    again = list(acquire.run([candidate], store, FakeFetcher(), use_apis=False))
    assert again == []


def test_acquire_can_be_limited_to_the_declared_manifest(tmp_path):
    """Measured, and it produced a figure about the wrong population: the pilot corpus discovered 199
    candidates and then curated 28, and `acquire --limit 28` attempted the first twenty-eight unattempted
    candidates of the 199 — exactly one of which was on the list. `report` had grown --round and --manifest
    two days earlier; acquire had neither, so a curated corpus could not be acquired as a corpus.
    """
    store = Store("t", base=tmp_path)
    declared = {"candidate_key": "doi:10.1/declared", "source_class": "ACA", "source_id": "ACA001",
                "url": "https://x.example/a", "title": "Declared", "round": "sweep"}
    found = {"candidate_key": "doi:10.9/found", "source_class": "ACA",
             "url": "https://x.example/b", "title": "Found", "round": "sweep"}
    fetcher = FakeFetcher(pages={
        "https://x.example/a": ok("https://x.example/a", pdf()),
        "https://x.example/b": ok("https://x.example/b", pdf())})

    rows = list(acquire.run([declared, found], store, fetcher, use_apis=False, manifest_only=True))
    assert [r["candidate_key"] for r in rows] == ["doi:10.1/declared"]


def test_acquire_can_be_limited_to_one_round(tmp_path):
    store = Store("t", base=tmp_path)
    spring = {"candidate_key": "doi:10.1/a", "source_class": "ACA", "url": "https://x.example/a",
              "title": "A", "round": "spring"}
    autumn = {"candidate_key": "doi:10.1/b", "source_class": "ACA", "url": "https://x.example/b",
              "title": "B", "round": "autumn"}
    fetcher = FakeFetcher(pages={
        "https://x.example/a": ok("https://x.example/a", pdf()),
        "https://x.example/b": ok("https://x.example/b", pdf())})
    rows = list(acquire.run([spring, autumn], store, fetcher, use_apis=False, round_name="autumn"))
    assert [r["candidate_key"] for r in rows] == ["doi:10.1/b"]


def test_only_oa_attempts_what_discovery_already_called_free(tmp_path):
    """The third population selector. On sources where a free copy exists by definition, a miss is ours,
    which is what makes this the population that measures the cascade rather than the literature."""
    store = Store("t", base=tmp_path)
    fetcher = FakeFetcher()
    candidates = [
        {"candidate_key": "a", "source_class": "ACA", "url": "https://x.example/a", "is_oa": True},
        {"candidate_key": "b", "source_class": "ACA", "url": "https://x.example/b", "is_oa": False},
        {"candidate_key": "c", "source_class": "ACA", "url": "https://x.example/c"},
    ]
    rows = list(acquire.run(candidates, store, fetcher, use_apis=False, only_oa=True))
    assert [r["candidate_key"] for r in rows] == ["a"]


def test_a_candidate_with_no_oa_field_is_unknown_and_not_closed(tmp_path):
    """Treating absent as closed would silently shrink the population this selector claims to describe.
    Without the selector it is attempted like any other."""
    store = Store("t", base=tmp_path)
    fetcher = FakeFetcher()
    candidates = [{"candidate_key": "c", "source_class": "ACA", "url": "https://x.example/c"}]
    assert [r["candidate_key"] for r in acquire.run(candidates, store, fetcher, use_apis=False)] == ["c"]


LANDING = (
    b"<html><body><h1>Screen time and well-being</h1>"
    b"<p>Abstract. We study adolescents.</p>"
    b"<a href='/ws/files/69982711/main.pdf'>Full text</a>"
    b"</body></html>"
)


def test_the_cascade_follows_a_record_page_to_the_file_it_names(tmp_path):
    """Measured on the pilot: 7 of 25 open-access misses had the deposited PDF's link in bytes already on
    disk, because Unpaywall names a Pure or DSpace record page as the free location."""
    store = Store("t", base=tmp_path)
    landing = "https://pure.example/en/publications/abc"
    fetcher = FakeFetcher(pages={
        landing: ok(landing, LANDING, "text/html"),
        "https://pure.example/ws/files/69982711/main.pdf": ok(
            "https://pure.example/ws/files/69982711/main.pdf", pdf(), "application/pdf"),
    })
    row = acquire.acquire_one(fetcher, store, candidate(url=landing), use_apis=False)
    assert row["acquired"] is True
    # The warrant is weaker than a metadata API's and the ledger says so.
    assert row["provenance"] == "landing"


def test_a_followed_link_does_not_itself_get_followed(tmp_path):
    """One level deep. A link read off a page never yields more links, so this cannot become a crawl."""
    store = Store("t", base=tmp_path)
    first = "https://pure.example/en/publications/abc"
    second = "https://pure.example/ws/files/1/main.pdf"
    # The "file" is another landing page naming a third file, which must never be fetched.
    fetcher = FakeFetcher(pages={
        first: ok(first, LANDING.replace(b"69982711/main.pdf", b"1/main.pdf"), "text/html"),
        second: ok(second, LANDING.replace(b"69982711/main.pdf", b"99/deeper.pdf"), "text/html"),
    })
    row = acquire.acquire_one(fetcher, store, candidate(url=first), use_apis=False)
    assert row["acquired"] is False
    tried = [a["url"] for a in row["attempts"]]
    assert tried == [first, second]


def test_a_record_page_with_no_file_link_changes_nothing(tmp_path):
    store = Store("t", base=tmp_path)
    url = "https://pure.example/en/publications/abc"
    bare = b"<html><body><h1>Title</h1><p>Abstract only.</p></body></html>"
    fetcher = FakeFetcher(pages={url: ok(url, bare, "text/html")})
    row = acquire.acquire_one(fetcher, store, candidate(url=url), use_apis=False)
    assert row["acquired"] is False
    assert [a["url"] for a in row["attempts"]] == [url]
