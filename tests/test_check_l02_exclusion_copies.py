"""A bounded copy plan must tie each URL to the exact cached DOI identity."""

import hashlib
import json

import pytest

from tools import check_l02_exclusion_copies as campaign


def test_plan_rejects_replaced_cached_copy_url(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    targets = []
    for key, host, url in [
        ("doi:10.2308/accr-51865", "utoronto.scholaris.ca",
         "https://utoronto.scholaris.ca/bitstreams/copy/download"),
        ("doi:10.1080/23322039.2016.1142847", "iris.unimore.it",
         "https://iris.unimore.it/bitstream/copy.pdf"),
    ]:
        body = json.dumps({"doi": "https://doi.org/" + key[4:],
                           "locations": [{"pdf_url": url}]}).encode()
        digest = hashlib.sha256(body).hexdigest()
        (raw / f"{digest}.bin").write_bytes(body)
        targets.append({"candidate_key": key, "allowed_host": host, "copy_url": url,
                        "cached_openalex_sha256": digest})

    frozen = {}
    for name in campaign.FROZEN:
        path = tmp_path / name
        if name == "ai_screening_sha256":
            path.write_text(json.dumps({"cases": [
                {"candidate_key": t["candidate_key"], "decision": "EXCLUDE"}
                for t in targets]}))
        else:
            path.write_text(name)
        frozen[name] = path
    plan = {"version": 1, "question_id": "L02", "project": "projects/alembic-s4-lungo",
            "campaign": "l02-v2-exclusion-check-institutional-copies-2026-10-06",
            "ceilings": {"candidate_copy_requests": 2}, "targets": targets,
            "frozen_inputs": {name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for name, path in frozen.items()}}
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    monkeypatch.setattr(campaign, "FROZEN", frozen)
    monkeypatch.setattr(campaign, "RAW", raw)
    monkeypatch.setattr(campaign, "EXPECTED_PLAN_SHA256",
                        hashlib.sha256(plan_path.read_bytes()).hexdigest())
    campaign.validate_plan(plan_path)

    cached = raw / f'{targets[0]["cached_openalex_sha256"]}.bin'
    replacement = json.dumps({"doi": "https://doi.org/" + targets[0]["candidate_key"][4:],
                              "locations": [{"pdf_url": "https://utoronto.scholaris.ca/other.pdf"}]})
    cached.write_text(replacement)
    with pytest.raises(ValueError, match="cached OpenAlex bytes changed"):
        campaign.validate_plan(plan_path)


def test_resume_only_after_second_copy_was_never_requested():
    first = "doi:10.2308/accr-51865"
    second = "doi:10.1080/23322039.2016.1142847"
    plan = {"targets": [{"candidate_key": first}, {"candidate_key": second}]}
    prior = [
        {"candidate_key": first, "status": "COPY_REQUIRES_IDENTITY_REVIEW"},
        {"candidate_key": second, "status": "STOPPED_BY_GUARD",
         "stop_reason": "page/copy transfer ceiling reached",
         "transfers_so_far": {"pages_or_copies": 2}},
    ]
    robots = [{"candidate_key": second, "event": "robots", "http_status": 200}]
    assert campaign.second_target_resume_allowed(plan, prior, robots)
    assert not campaign.second_target_resume_allowed(
        plan, prior, robots + [{"candidate_key": second, "event": "transport", "http_status": 403}])
    assert not campaign.second_target_resume_allowed(
        plan, prior + [prior[-1]], robots)
