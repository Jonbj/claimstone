"""Physical transfers stop at the exact approved hosts and ceilings."""

from types import SimpleNamespace

import pytest
import requests

from tools.check_l02_repository_copies import CampaignStop, GuardedSession, PageLinks


def test_guard_refuses_unapproved_redirect_and_exhausted_limits(monkeypatch):
    seen = []

    def fake_get(self, url, **kwargs):
        seen.append(url)
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(requests.Session, "get", fake_get)
    session = GuardedSession({"archive.example"}, max_pages=1, max_robots=1)
    with pytest.raises(CampaignStop, match="outside approved hosts"):
        session.get("https://other.example/robots.txt")
    assert seen == []
    session.get("https://archive.example/robots.txt")
    session.get("https://archive.example/work.pdf")
    with pytest.raises(CampaignStop, match="robots transfer ceiling"):
        session.get("https://archive.example/robots.txt")
    with pytest.raises(CampaignStop, match="page/copy transfer ceiling"):
        session.get("https://archive.example/other.pdf")
    assert seen == ["https://archive.example/robots.txt", "https://archive.example/work.pdf"]


def test_page_links_keep_text_and_pdf_candidates_separate():
    parser = PageLinks()
    parser.feed('<h1>Media-expressed negative tone</h1><a href="paper.pdf">PDF</a>')
    assert "Media-expressed negative tone" in " ".join(parser.words)
    assert parser.links == ["paper.pdf"]
