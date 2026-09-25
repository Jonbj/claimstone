"""The container client. No container is started and no socket is opened."""

import pytest

from claimstone import grobid


class FakeTransport:
    """Stands in for the two requests calls grobid makes."""

    def __init__(self, alive=True, tei=b"<TEI/>", status=200):
        self.alive, self.tei, self.status = alive, tei, status
        self.posted: list[tuple[str, dict]] = []

    def get(self, url, timeout=None):
        outer = self

        class R:
            status_code = 200 if outer.alive else 503
            text = "true" if outer.alive else ""

        return R()

    def post(self, url, files=None, data=None, timeout=None):
        self.posted.append((url, dict(data or {})))
        outer = self

        class R:
            status_code = outer.status
            content = outer.tei
            text = "server said no"

        return R()


def test_a_live_server_reports_alive():
    assert grobid.Grobid(transport=FakeTransport()).is_alive() is True


def test_a_dead_server_reports_not_alive():
    assert grobid.Grobid(transport=FakeTransport(alive=False)).is_alive() is False


def test_the_error_names_the_workaround_not_just_the_url():
    # The cgroup v2 failure cost twenty minutes to diagnose. The error message is where that
    # belongs, not in someone's memory.
    client = grobid.Grobid(transport=FakeTransport(alive=False))
    with pytest.raises(grobid.GrobidUnavailable) as caught:
        client.full_text(b"%PDF-1.4")
    message = str(caught.value)
    assert "JAVA_TOOL_OPTIONS=-XX:-UseContainerSupport" in message
    assert "docker run" in message
    assert "cgroup v2" in message


def test_the_error_names_the_image_the_figures_were_measured_with():
    # latest-crf produces five times the TEI of 0.8.1 on the same PDF, so the two are not
    # interchangeable and every corpus figure depends on which one ran.
    client = grobid.Grobid(transport=FakeTransport(alive=False))
    with pytest.raises(grobid.GrobidUnavailable, match=grobid.IMAGE):
        client.full_text(b"%PDF-1.4")


def test_a_pdf_comes_back_as_tei():
    transport = FakeTransport(tei=b"<TEI>ok</TEI>")
    assert grobid.Grobid(transport=transport).full_text(b"%PDF-1.4") == b"<TEI>ok</TEI>"


def test_consolidation_is_off_by_default():
    # 803 references across 14 documents would be 803 Crossref lookups, and this stage is
    # otherwise pure local parsing. Resolution is not stage 3's job.
    transport = FakeTransport()
    grobid.Grobid(transport=transport).full_text(b"%PDF-1.4")
    _, data = transport.posted[-1]
    assert data["consolidateHeader"] == "0"
    assert data["consolidateCitations"] == "0"


def test_a_server_error_is_reported_with_its_status():
    client = grobid.Grobid(transport=FakeTransport(status=500))
    with pytest.raises(grobid.GrobidFailed, match="500"):
        client.full_text(b"%PDF-1.4")
