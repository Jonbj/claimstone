"""The bounded copy campaign must refuse any unapproved transfer before transport."""

import hashlib
import json

import pytest
import requests

from tools import recover_l02_durham as campaign
from tools.recover_l02_durham import CampaignStop, GuardedSession


def test_frozen_plan_rejects_changed_metadata(tmp_path, monkeypatch):
    urls = ["http://dro.dur.ac.uk/14223/",
            "https://durham-repository.worktribe.com/output/1415750"]
    inputs = {}
    for key in campaign.INPUTS:
        path = tmp_path / key
        path.write_text(json.dumps({"doi": "https://doi.org/10.17578/19-1-1",
                                    "locations": [{"landing_page_url": url} for url in urls]})
                        if key == "openalex_payload_sha256" else key)
        inputs[key] = path
    plan = {
        "version": 1, "candidate_key": "doi:10.17578/19-1-1",
        "project": "projects/alembic-s4-lungo",
        "campaign": "l02-uk-press-durham-recovery-2026-10-06",
        "allowed_institutional_hosts": ["dro.dur.ac.uk", "durham-repository.worktribe.com"],
        "ceilings": {"landing_page_requests": 2, "candidate_copy_requests": 1},
        "landing_urls": urls,
        "frozen_inputs": {key: hashlib.sha256(path.read_bytes()).hexdigest()
                          for key, path in inputs.items()},
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    monkeypatch.setattr(campaign, "INPUTS", inputs)
    monkeypatch.setattr(campaign, "EXPECTED_PLAN_SHA256",
                        hashlib.sha256(plan_path.read_bytes()).hexdigest())
    assert campaign.load_plan(plan_path)["candidate_key"] == "doi:10.17578/19-1-1"
    inputs["openalex_payload_sha256"].write_text("{}")
    with pytest.raises(ValueError, match="frozen input changed"):
        campaign.load_plan(plan_path)


def test_session_rejects_redirect_host_and_transfer_overrun(monkeypatch):
    sent = []
    monkeypatch.setattr(requests.Session, "get", lambda self, url, **kwargs: sent.append(url))
    session = GuardedSession({"dro.dur.ac.uk"}, max_pages=2, max_robots=1)

    session.get("http://dro.dur.ac.uk/robots.txt")
    session.get("http://dro.dur.ac.uk/14223/")
    session.get("https://dro.dur.ac.uk/14223/")
    with pytest.raises(CampaignStop, match="outside approved"):
        session.get("https://publisher.example/paper.pdf")
    with pytest.raises(CampaignStop, match="ceiling"):
        session.get("https://dro.dur.ac.uk/paper.pdf")
    with pytest.raises(CampaignStop, match="robots transfer ceiling"):
        session.get("https://dro.dur.ac.uk/robots.txt")
    assert len(sent) == 3
