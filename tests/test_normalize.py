"""Orchestration: GROBID, the TEI on disk, the three ledgers."""

import pytest

from claimstone import normalize
from claimstone.store import Store
from tests.test_tei import DOC

# `DOC` has two references and 87 body characters, so it satisfies neither clause of the
# confirmation rule. A test that needed a confirmed document and used it anyway would be testing
# a rule nobody runs. `PAPER` is `DOC` with three more references — the smallest change that makes
# it confirm, and it confirms for the stated reason: five references, not enough text.
PAPER = DOC.replace(
    b"</listBibl>",
    b"".join(
        b"<biblStruct><monogr><title level=\"m\">Filler study %d</title>"
        b"<imprint><date type=\"published\" when=\"20%02d\"/></imprint></monogr></biblStruct>" % (n, n)
        for n in range(10, 13)
    ) + b"</listBibl>",
)


class FakeGrobid:
    """Returns prepared TEI. Counts calls, so idempotence is observable."""

    def __init__(self, tei_by_call=None, tei=PAPER):
        self.tei, self.tei_by_call = tei, tei_by_call or {}
        self.calls = 0

    def is_alive(self):
        return True

    def full_text(self, pdf, *, filename="document.pdf"):
        self.calls += 1
        return self.tei_by_call.get(self.calls, self.tei)


FACT_SHEET = """<?xml version="1.0"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
  <div><head>Key use cases</head><p>Proactively detect and manage market abuse.</p></div>
  <div><head>Find out more</head><p>Contact your account manager today.</p></div>
</body></text></TEI>
""".encode()


def _store(tmp_path, rows):
    store = Store("t", base=tmp_path)
    for row in rows:
        store.append("acquisitions.jsonl", row)
    return store


def acquired(source_id, store, body=b"%PDF-1.4 fake", klass="ACA"):
    digest, path = store.store_bytes(body, ".pdf")
    return {"candidate_key": f"k:{source_id}", "source_id": source_id, "source_class": klass,
            "acquired": True, "sha256": digest, "stored_path": str(path),
            "content_type": "application/pdf", "url": f"https://x.example/{source_id}",
            "gate": {"kind": "PDF_FULLTEXT"}}


def test_a_document_produces_chunks_and_a_documents_row(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    rows = list(normalize.run(store, FakeGrobid()))
    assert rows[0]["fulltext_confirmed"] is True
    assert rows[0]["chunks"] > 0
    assert len(list(store.read("chunks.jsonl"))) == rows[0]["chunks"]


def test_the_tei_is_stored_content_addressed(tmp_path):
    import pathlib

    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    row = next(iter(normalize.run(store, FakeGrobid())))
    assert pathlib.Path(row["tei_path"]).exists()


def test_the_same_bytes_are_never_normalized_twice(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    grobid = FakeGrobid()
    list(normalize.run(store, grobid))
    again = list(normalize.run(store, grobid))
    assert again == []
    assert grobid.calls == 1


def test_force_re_normalizes_without_calling_grobid_again(tmp_path):
    # The TEI is already on disk, so a chunk_version bump needs no network — the same
    # arrangement as regate.
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    grobid = FakeGrobid()
    list(normalize.run(store, grobid))
    rows = list(normalize.run(store, grobid, force=True))
    assert len(rows) == 1
    assert grobid.calls == 1


def test_a_fact_sheet_is_not_confirmed_and_produces_no_chunks(tmp_path):
    # Measured: IND008 is a vendor fact sheet with no references and 4,618 characters. It
    # passed stage 2 because that gate is structural, and this is the signal stage 2 promised.
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("IND008", store))
    row = next(iter(normalize.run(store, FakeGrobid(tei=FACT_SHEET))))
    assert row["fulltext_confirmed"] is False
    assert row["failure_class"] == "NOT_A_DOCUMENT"
    assert row["chunks"] == 0
    assert list(store.read("chunks.jsonl")) == []


def test_the_confirmation_reason_names_both_counts(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("IND008", store))
    row = next(iter(normalize.run(store, FakeGrobid(tei=FACT_SHEET))))
    assert "0 references" in row["reason"]
    assert "body_chars" in row["reason"]


def test_references_are_deduplicated_across_documents_with_a_count(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store, body=b"%PDF one"))
    store.append("acquisitions.jsonl", acquired("S02", store, body=b"%PDF two"))
    list(normalize.run(store, FakeGrobid()))
    refs = store.latest_by("references.jsonl", "key")
    talk = refs["title:is all that talk just noise"]
    assert sorted(talk["cited_by"]) == ["S01", "S02"]
    assert talk["citations_in_corpus"] == 2
    assert talk["doi"] == "10.1111/j.1540-6261.2004.00662.x"


def test_an_unacquired_source_is_not_attempted(tmp_path):
    store = _store(tmp_path, [{"candidate_key": "k", "source_id": "S09", "acquired": False,
                               "failure_class": "PAYWALL_403"}])
    assert list(normalize.run(store, FakeGrobid())) == []


FILING_HTML = """<html><head><title>FORM 10-K</title></head><body>
  <h1>Item 1. Business</h1>
  <p>%s</p>
</body></html>""" % ("The registrant operates a service. " * 600)


def test_a_long_html_document_is_confirmed(tmp_path):
    # IND001 in the real corpus: an EDGAR prospectus supplement, 247,993 characters by the
    # content gate's count, with no bibliography. The
    # confirmation rule's second clause is for exactly this, and marking it NOT_PDF dropped a
    # real document out of the count.
    store = Store("t", base=tmp_path)
    row = acquired("IND001", store, body=FILING_HTML.encode())
    row["content_type"] = "text/html"
    store.append("acquisitions.jsonl", row)
    result = next(iter(normalize.run(store, FakeGrobid())))
    assert result["fulltext_confirmed"] is True
    assert result["chunks"] > 0
    assert result["failure_class"] is None


def test_a_short_html_document_is_not_confirmed(tmp_path):
    store = Store("t", base=tmp_path)
    row = acquired("NEW009", store, body=b"<html><body><p>A brief note.</p></body></html>")
    row["content_type"] = "text/html"
    store.append("acquisitions.jsonl", row)
    result = next(iter(normalize.run(store, FakeGrobid())))
    assert result["fulltext_confirmed"] is False
    assert result["failure_class"] == "NOT_A_DOCUMENT"


def test_html_does_not_call_grobid(tmp_path):
    # GROBID reads PDFs. Sending it markup would be a request that cannot succeed.
    store = Store("t", base=tmp_path)
    row = acquired("IND001", store, body=FILING_HTML.encode())
    row["content_type"] = "text/html"
    store.append("acquisitions.jsonl", row)
    grobid = FakeGrobid()
    list(normalize.run(store, grobid))
    assert grobid.calls == 0


def test_malformed_tei_is_recorded_not_raised(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    row = next(iter(normalize.run(store, FakeGrobid(tei=b"<TEI><body>unclosed"))))
    assert row["fulltext_confirmed"] is False
    assert row["failure_class"] == "TEI_UNREADABLE"


# --- When the bytes are not there -----------------------------------------------------------------
#
# The store is append-only and content-addressed, so a missing artifact is not routine. But the
# plan's first version read it with no guard, and one absent file aborted the sweep before any other
# source was touched. The state it must not record is "not a document": a file that is gone
# establishes nothing, and admissibility counts every unconfirmed document row as an established
# negative, which would lower the rate on an infrastructure failure.

def test_one_unreadable_artifact_does_not_abort_the_sweep(tmp_path):
    store = Store("t", base=tmp_path)
    gone = acquired("S01", store)
    __import__("pathlib").Path(gone["stored_path"]).unlink()
    store.append("acquisitions.jsonl", gone)
    store.append("acquisitions.jsonl", acquired("S02", store, body=b"%PDF two"))

    rows = list(normalize.run(store, FakeGrobid()))
    assert [r["source_id"] for r in rows] == ["S01", "S02"]
    assert rows[1]["fulltext_confirmed"] is True


def test_an_unreadable_artifact_stays_unknown_rather_than_becoming_a_negative(tmp_path):
    store = Store("t", base=tmp_path)
    gone = acquired("S01", store)
    __import__("pathlib").Path(gone["stored_path"]).unlink()
    store.append("acquisitions.jsonl", gone)

    row = next(iter(normalize.run(store, FakeGrobid())))
    assert row["failure_class"] == normalize.ARTIFACT_UNREADABLE
    assert row["fulltext_confirmed"] is None      # not False: nothing was established
    # No documents row, so admissibility leaves the source awaiting — which raises the ceiling and
    # never the figure, and keeps the round from certifying itself.
    assert list(store.read("documents.jsonl")) == []


def test_a_retry_normalizes_it_once_the_bytes_are_back(tmp_path):
    import pathlib

    store = Store("t", base=tmp_path)
    gone = acquired("S01", store)
    body = pathlib.Path(gone["stored_path"]).read_bytes()
    pathlib.Path(gone["stored_path"]).unlink()
    store.append("acquisitions.jsonl", gone)
    list(normalize.run(store, FakeGrobid()))

    pathlib.Path(gone["stored_path"]).write_bytes(body)
    row = next(iter(normalize.run(store, FakeGrobid())))
    assert row["fulltext_confirmed"] is True


def test_force_appends_rather_than_edits_and_a_consumer_must_read_the_latest(tmp_path):
    """Append-only: identical generations reuse immutable chunks; historical rows are retained.

    Stated as a test because the difference is invisible until someone counts raw rows and reports
    twice the corpus.
    """
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    grobid = FakeGrobid()
    list(normalize.run(store, grobid))
    rows_before = len(list(store.read("chunks.jsonl")))
    ids_before = set(store.latest_by("chunks.jsonl", "chunk_id"))

    list(normalize.run(store, grobid, force=True))
    assert len(list(store.read("chunks.jsonl"))) == rows_before
    assert set(store.latest_by("chunks.jsonl", "chunk_id")) == ids_before


def test_an_unreadable_artifact_leaves_the_round_unable_to_certify(tmp_path):
    """The whole point of not recording a negative: the ceiling rises, the figure does not."""
    from claimstone import admissibility

    store = Store("t", base=tmp_path)
    gone = acquired("S01", store)
    __import__("pathlib").Path(gone["stored_path"]).unlink()
    store.append("acquisitions.jsonl", gone)
    store.append("acquisitions.jsonl", acquired("S02", store, body=b"%PDF two"))
    for source_id in ("S01", "S02"):
        store.append("candidates.jsonl", {"candidate_key": f"k:{source_id}",
                                          "source_id": source_id, "source_class": "ACA",
                                          "url": f"https://x.example/{source_id}"})
    list(normalize.run(store, FakeGrobid()))

    measured = admissibility.rate(store)
    assert measured["confirmed"] == 1
    assert measured["awaiting_normalize"] == 1
    assert measured["not_a_document"] == []
    assert (measured["rate"], measured["rate_upper"]) == (0.5, 1.0)
    assert measured["final"] is False
    assert "awaiting_normalize" in measured["blocking"]


def test_the_confirm_sweep_reports_a_count_per_threshold_value(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store, body=b"%PDF one"))
    store.append("acquisitions.jsonl", acquired("IND008", store, body=b"%PDF two"))
    list(normalize.run(store, FakeGrobid(tei_by_call={1: DOC, 2: FACT_SHEET})))
    points = normalize.confirm_sweep(store, "min_references", [1, 2, 5, 40])
    assert [p["value"] for p in points] == [1, 2, 5, 40]
    assert points[0]["confirmed"] == 1      # DOC has 2 references, the fact sheet none
    assert points[-1]["confirmed"] == 0     # nothing has 40
    assert all(p["unreadable"] == 0 for p in points)


def test_the_sweep_opens_no_socket_and_calls_no_grobid(tmp_path, monkeypatch):
    import socket

    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    list(normalize.run(store, FakeGrobid()))

    def refuse(*args, **kwargs):
        raise AssertionError("the sweep must re-read the TEI on disk, not the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    normalize.confirm_sweep(store, "confirm_chars", [1000, 50000])


def test_an_unknown_threshold_is_refused(tmp_path):
    store = Store("t", base=tmp_path)
    with pytest.raises(ValueError, match="nonsense"):
        normalize.confirm_sweep(store, "nonsense", [1])


def test_the_sweep_reads_an_html_document_with_the_html_parser(tmp_path):
    """The one document that confirms on the second clause must be in the sweep of that clause.

    Parsing it as TEI would count it unreadable, and a sweep of confirm_chars that excludes the
    only source confirmed by characters reports that the threshold decides nothing.
    """
    store = Store("t", base=tmp_path)
    row = acquired("IND001", store, body=FILING_HTML.encode())
    row["content_type"] = "text/html"
    store.append("acquisitions.jsonl", row)
    list(normalize.run(store, FakeGrobid()))

    points = normalize.confirm_sweep(store, "confirm_chars", [1000, 10**9])
    assert [p["unreadable"] for p in points] == [0, 0]
    assert [p["confirmed"] for p in points] == [1, 0]


def test_the_confirmed_rate_matches_what_normalize_wrote(tmp_path):
    """End to end: acquire's ledger, normalize's verdicts, admissibility's arithmetic.

    Each side was tested against fixtures of the other's shape. This asserts they agree on rows one
    of them really produced — which is where a field name or a join key silently diverges.
    """
    from claimstone import admissibility

    store = Store("t", base=tmp_path)
    for source_id, body in (("S01", b"%PDF one"), ("S02", b"%PDF two"), ("IND008", b"%PDF three")):
        acq = acquired(source_id, store, body=body)
        store.append("candidates.jsonl", {"candidate_key": acq["candidate_key"],
                                          "source_id": source_id, "source_class": "ACA"})
        store.append("acquisitions.jsonl", acq)
    # Two real documents and one vendor fact sheet.
    list(normalize.run(store, FakeGrobid(tei_by_call={1: PAPER, 2: PAPER, 3: FACT_SHEET})))

    result = admissibility.rate(store)
    assert result["found"] == 3
    assert result["obtained"] == 3
    assert result["confirmed"] == 2
    assert result["basis"] == "confirmed"
    assert result["not_a_document"] == ["IND008"]
    assert result["awaiting_normalize"] == 0
    assert result["rate"] == 2 / 3


def test_a_source_normalize_has_not_reached_is_not_counted_against_the_corpus(tmp_path):
    from claimstone import admissibility

    store = Store("t", base=tmp_path)
    for source_id in ("S01", "S02"):
        acq = acquired(source_id, store, body=f"%PDF {source_id}".encode())
        store.append("candidates.jsonl", {"candidate_key": acq["candidate_key"],
                                          "source_id": source_id, "source_class": "ACA"})
        store.append("acquisitions.jsonl", acq)
    list(normalize.run(store, FakeGrobid(), limit=1))

    result = admissibility.rate(store)
    # One normalized and confirmed, one not reached. Counting the second as unconfirmed would make
    # the rate fall because stage 3 had not finished — measuring our own progress and reporting it as
    # a property of the corpus.
    assert result["confirmed"] == 1
    assert result["awaiting_normalize"] == 1
    assert result["not_a_document"] == []
    assert (result["rate"], result["rate_upper"]) == (0.5, 1.0)
    assert result["final"] is False


# --- D110: the image that read a PDF is recorded, and two images never share a cached TEI ---------


def test_a_pdf_row_names_the_image_that_read_it(tmp_path):
    from claimstone import grobid as grobid_module

    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    row = next(iter(normalize.run(store, FakeGrobid())))
    assert row["pdf_parser"] == grobid_module.IMAGE
    assert row["tei_path"].endswith(grobid_module.tei_relpath(row["sha256"]))


def test_legacy_tei_is_not_reused_by_another_image(tmp_path):
    """A TEI cached at the legacy flat path was produced by the legacy image. A newer image must
    read the PDF itself rather than inherit that answer under its own name."""
    from claimstone import grobid as grobid_module

    store = Store("t", base=tmp_path)
    source = acquired("S01", store)
    store.append("acquisitions.jsonl", source)
    legacy = store.root / grobid_module.tei_relpath(source["sha256"], grobid_module.LEGACY_IMAGE)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(PAPER)
    grobid = FakeGrobid()
    list(normalize.run(store, grobid))
    assert grobid.calls == 1
    assert legacy.read_bytes() == PAPER  # the legacy answer is kept, untouched


def test_paths_and_the_recorded_image():
    from claimstone import grobid as grobid_module

    assert grobid_module.tei_relpath("ab", grobid_module.LEGACY_IMAGE) == "tei/ab.xml"
    assert grobid_module.tei_relpath("ab", "grobid/grobid:0.9.1-full") == \
        "tei/grobid_grobid_0.9.1-full/ab.xml"
    assert grobid_module.document_image({"format": "pdf"}) == grobid_module.LEGACY_IMAGE
    assert grobid_module.document_image({"format": "pdf", "pdf_parser": "x"}) == "x"
    assert grobid_module.document_image({"format": "html"}) is None


def test_transferred_legacy_tei_is_read_and_recorded_as_the_legacy_images(tmp_path):
    from claimstone import grobid as grobid_module

    store = Store("t", base=tmp_path)
    source = acquired("S01", store)
    store.append("acquisitions.jsonl", source)
    legacy = store.root / grobid_module.tei_relpath(source["sha256"], grobid_module.LEGACY_IMAGE)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(PAPER)
    grobid = FakeGrobid()
    [row] = list(normalize.run(store, grobid, pdf_image=grobid_module.LEGACY_IMAGE))
    assert grobid.calls == 0
    assert row["pdf_parser"] == grobid_module.LEGACY_IMAGE
