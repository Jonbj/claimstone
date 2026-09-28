"""Offline review probes. Each FAIL is an unmet behavioral requirement, not a network test.

Run from any directory with the repository's Python. All writes use TemporaryDirectory;
the real store is never opened. Exit 1 means at least one finding still reproduces.
These probes are separate from the project's baseline test suite.
"""

from __future__ import annotations

import dataclasses
import contextlib
import io
import json
import pathlib
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from claimstone import (
    admissibility, chunk_sets, claimgate, cli, config, discover, evidence, extract,
    gate_audit, model_call, model_report, net, normalize, review, synthesize,
)
from claimstone.runners.base import RawAnswer
from claimstone.store import Store


def project(root):
    return config.Project(
        name="review-fixture", root=root, classes=(
            config.SourceClass("A", "Public studies", "declared", role="empirical"),
        ), acquisition_floor=0.8, excluded_hosts=(), topics=(),
        questions=(config.Question("Q", "Does the exposure affect the outcome?", kind="effect"),),
        registry_version=1, frozen_at="2026-09-27", registry_sha256="fixture-v1",
    )


def source(store, identifier, *, round_name="good", acquired=True, confirmed=True, klass="A"):
    store.append("candidates.jsonl", {
        "candidate_key": identifier, "source_id": identifier,
        "source_class": klass, "round": round_name,
    })
    if acquired is not None:
        store.append("acquisitions.jsonl", {
            "candidate_key": identifier, "source_id": identifier,
            "source_class": klass, "acquired": acquired,
            "failure_class": None if acquired else "PAYWALL_403",
        })
    if acquired and confirmed is not None:
        store.append("documents.jsonl", {
            "source_id": identifier, "source_class": klass,
            "fulltext_confirmed": confirmed,
        })
    if acquired and confirmed:
        store.append("chunks.jsonl", {
            "source_id": identifier, "chunk_id": identifier + "#c1",
            "text": "The measured effect is 2.", "kind": "prose",
        })


def claim(store, identifier="c", source_id="s", **extra):
    row = {
        "claim_id": identifier, "source_id": source_id, "chunk_id": source_id + "#c1",
        "source_class": "A", "question_id": "Q", "stance": "SUPPORTS",
        "claim": "The measured effect is 2.", "evidence_quote": "The measured effect is 2.",
        "backend": "reader-a", "model": "model-a", "registry_version": 1,
        "claim_gate_version": claimgate.CLAIM_GATE_VERSION,
        **extra,
    }
    store.append("claims.jsonl", row)
    store.append("reviews.jsonl", {
        "claim_id": identifier, "question_id": "Q", "verdict": "SUPPORTED", "review_version": review.REVIEW_VERSION,
        "reviewed_by": {"backend": "reader-b", "model": "model-b"},
    })
    return row


def built(store, p):
    synthesize.build(p, store)
    return synthesize.latest_profiles(store)["Q"]


def unit(store, p, *, batch="probe"):
    extract.build(p, store, batch=batch)
    q = model_call.Queue(store, lane="extract", batch=batch)
    return q, q.requests()[0]


def result(request, *, backend="reader-a", output=None):
    record = {
        "result_id": "r1", "question_id": "Q", "stance": "SUPPORTS",
        "claim": "The measured effect is 2.", "evidence_quote": "The measured effect is 2.",
    }
    return {
        "call_id": request["call_id"], "result_key": request["call_id"] + "|" + backend + "|model",
        "backend": backend, "model": "model", "harness_version": "fixture",
        "ok": True, "output": output if output is not None else [record],
        "finished_at": "2026-09-28T00:00:00+00:00",
    }


def pending_extraction(root, store, p):
    source(store, "s")
    unit(store, p)
    profile = built(store, p)
    assert profile["provisional"], "queued, unanswered extraction produces a final empty profile"


def unattempted_acquisition(root, store, p):
    for i in range(4):
        source(store, f"s{i}")
    source(store, "s4", acquired=None)
    measured = admissibility.admit(p, store)
    assert not measured["final"], f"4/5 obtained with one never attempted: final={measured['final']}"


def round_scope(root, store, p):
    source(store, "s")
    source(store, "outside", round_name="other")
    claim(store, source_id="outside")
    synthesize.build(p, store, round_name="good")
    profile = synthesize.latest_profiles(store, round_name="good")["Q"]
    assert not profile["results"], "the good round includes a result from the other round"


def round_hash(root, store, p):
    source(store, "s")
    synthesize.build(p, store)
    a = synthesize.latest_profiles(store)["Q"]
    synthesize.build(p, store, round_name="good")
    b = synthesize.latest_profiles(store, round_name="good")["Q"]
    assert a["profile_sha256"] != b["profile_sha256"], "round changes after the hash is computed"


def old_registry_claims(root, store, p):
    source(store, "s")
    claim(store)
    new = dataclasses.replace(p, registry_version=2, registry_sha256="fixture-v2", frozen_at="2026-09-28",
                              questions=(config.Question("Q", "A different question", kind="effect"),))
    profile = built(store, new)
    assert not profile["results"], "v1 evidence is emitted as an adjudicable v2 profile"


def stale_underlying_evidence(root, store, p):
    source(store, "s")
    claim(store)
    # Isolate signing from the separate extraction-completeness probe.
    q, request = unit(store, p, batch='complete-fixture')
    store.append(q.results_name, result(request, output=[]))
    profile = built(store, p)
    # Synthetic person/signature in an isolated fixture. No real adjudication is created.
    synthesize.adjudicate(store, "Q", project=p, verdict="SUPPORTED", by="synthetic fixture",
                         rationale="Synthetic audit rationale. " * 8,
                         profile_sha256=profile["profile_sha256"])
    claim(store, "new")
    assert synthesize.verdicts(store, project=p)["stale"] == 1, "new underlying evidence leaves the stored signature current"


def adjudicate_after_floor_failure(root, store, p):
    source(store, "s")
    claim(store)
    # Isolate signing from the separate extraction-completeness probe.
    q, request = unit(store, p, batch='complete-fixture')
    store.append(q.results_name, result(request, output=[]))
    profile = built(store, p)
    source(store, "missing", acquired=False)
    assert admissibility.admit(p, store)["status"] == admissibility.INSUFFICIENT
    try:
        synthesize.adjudicate(store, "Q", project=p, verdict="SUPPORTED", by="synthetic fixture",
                             rationale="Synthetic audit rationale. " * 8,
                             profile_sha256=profile["profile_sha256"])
    except (synthesize.NotAdmissible, synthesize.Provisional, synthesize.StaleProfile):
        return
    raise AssertionError("a cached final profile can still be signed after the current corpus falls below its floor")


def numeric_boundaries(root, store, p):
    admitted = []
    for quote in ("The measured effect is -2.", "The measured effect is 0.2.", "The measured effect is 2.7."):
        v = claimgate.check({"question_id": "Q", "claim": "The measured effect is 2.",
                             "evidence_quote": quote, "stance": "SUPPORTS"},
                            chunk=quote, questions=p.questions, lane="effect")
        if v.ok:
            admitted.append(quote)
    assert not admitted, f"claim of 2 passes on quotes {admitted!r}"


def review_all_fields(root, store, p):
    row = {"claim": "An effect was found.", "evidence_quote": "A result was reported.",
           "estimate_as_written": "999", "sample": "invented population", "design": "invented design"}
    text = review.review_unit(p.questions[0], row, "A result was reported.")
    assert "999" in text and "invented population" in text, "reviewer never sees estimate, sample, or design"


def cross_reader_identity(root, store, p):
    source(store, "s")
    q, request = unit(store, p)
    q.store.append(q.results_name, result(request, backend="reader-a"))
    r = result(request, backend="reader-b")
    r["output"][0]["claim"] = "A differently worded effect is 2."
    q.store.append(q.results_name, r)
    extract.harvest(p, store, batch="probe")
    rows = list(store.read("claims.jsonl"))
    assert len(rows) == 2, f"two readers' distinct annotations collapse to {len(rows)} claim"


def harvest_rejudged_answer(root, store, p):
    source(store, "s")
    q, request = unit(store, p)
    r = result(request)
    r.update(ok=False, output=None, failure_class="NOT_JSON")
    store.append(q.results_name, r)
    r = result(request)
    r["rejudged_from"] = "2026-09-28T00:00:00+00:00"
    store.append(q.results_name, r)
    extract.harvest(p, store, batch="probe")
    assert list(store.read("claims.jsonl")), "a currently valid rejudged answer is skipped"


def prompt_mismatch_rejudge(root, store, p):
    source(store, "s")
    q, request = unit(store, p)
    raw = json.dumps(result(request)["output"]).encode()
    digest, path = store.store_bytes_at(q.root + "/raw", raw, ".txt")
    r = model_call.build_result(request, RawAnswer(body=raw, model="model", prompt_sent="different prompt"),
                               backend="reader-a", model="model", harness_version="fixture", raw_path=str(path),
                               raw_sha256=digest, started_at="start", finished_at="finish", latency_s=0)
    assert r["failure_class"] == "PROMPT_MISMATCH"
    store.append(q.results_name, r)
    changed = list(model_call.rejudge(q))[0]
    assert not changed["ok"], f"PROMPT_MISMATCH becomes ok={changed['ok']} on rejudge"


def rechunk_ghosts(root, store, p):
    payload = b"<html><body><p>First paragraph has evidence.</p><p>Second paragraph has evidence.</p></body></html>"
    digest, path = store.store_bytes(payload, ".html")
    store.append("acquisitions.jsonl", {"candidate_key": "s", "source_id": "s", "source_class": "A",
                                         "acquired": True, "sha256": digest, "stored_path": str(path),
                                         "content_type": "text/html"})
    th = {"confirm_chars": 1, "min_section_chars": 0, "merge_below": 0, "max_chunk_chars": 30}
    list(normalize.run(store, None, thresholds=th))
    list(normalize.run(store, None, thresholds={**th, "max_chunk_chars": 9000}, force=True))
    reported = store.latest_by("documents.jsonl", "source_id")["s"]["chunks"]
    active = len(chunk_sets.current(store))
    assert active == reported, f"document says {reported} chunk, downstream reads {active}"


def confirmed_class_floor(root, store, p):
    p = dataclasses.replace(p, classes=p.classes + (config.SourceClass("B", "Other studies", "declared"),))
    for i in range(8):
        source(store, f"a{i}")
    source(store, "b0", klass="B")
    source(store, "b1", klass="B", confirmed=False)
    measured = admissibility.admit(p, store)
    assert measured["status"] == admissibility.INSUFFICIENT, (
        f"overall confirmed 9/10, class B confirmed 1/2: status={measured['status']}, "
        f"class B rate={measured['by_class']['B']['rate']}"
    )


def regate_class_policy(root, store, p):
    payload = ("<html><body><p>" + "Public guidance. " * 300 + "</p></body></html>").encode()
    digest, path = store.store_bytes(payload, ".html")
    store.append("candidates.jsonl", {"candidate_key": "s", "source_class": "A"})
    store.append("acquisitions.jsonl", {
        "candidate_key": "s", "source_id": "s", "source_class": "A", "acquired": True,
        "sha256": digest, "stored_path": str(path), "content_type": "text/html",
        "url": "https://public.example/guidance", "fetched_at": "2026-09-28T00:00:00+00:00",
    })
    # This source class's acquisition policy requires length only. regate has no classes input.
    from claimstone.fulltext import classify
    assert classify(payload, "text/html", "", policy={"structural_signal": "none"}).accepted
    changed = list(gate_audit.regate(store, campaign="offline-review", policy={},
                                      classes=(dataclasses.replace(p.classes[0], gate_policy={"structural_signal": "none"}),)))[0]
    assert changed["acquired"], "regate drops class policy and refutes previously valid guidance"


def redirect_guards(root, store, p):
    visited = []
    class Session:
        def get(self, url, **kwargs):
            visited.append(url)
            if kwargs.get("allow_redirects"):
                visited.append("https://excluded.example/document")
                return SimpleNamespace(status_code=200, url=visited[-1],
                                       headers={"Content-Type": "text/plain"}, content=b"document")
            return SimpleNamespace(status_code=302, url=url, headers={"Location": "https://excluded.example/document"},
                                   content=b"redirect")
    with patch.dict("os.environ", {"CLAIMSTONE_CONTACT_EMAIL": "audit@example.org"}):
        f = net.Fetcher(excluded_hosts=frozenset({"excluded.example"}), pause_s=0)
    f._session = Session()
    f._robots_allows = lambda url: True
    outcome = f.get("https://allowed.example/document")
    assert "https://excluded.example/document" not in visited and not outcome.ok, (
        "an allowed initial URL follows a redirect to an excluded host without checking it"
    )


def discovery_failure(root, store, p):
    p = dataclasses.replace(p, topics=(config.Topic("T", "Exposure", ("exposure",)),))
    class FailedFetcher:
        def get_json(self, url):
            return None, net.Outcome(url, False, failure_class=net.TIMEOUT)
    with patch.dict("os.environ", {"CLAIMSTONE_CONTACT_EMAIL": "audit@example.org"}):
        r = discover.run(p, store, FailedFetcher(), apis=("openalex",))
    rows = [path for path in store.root.rglob("*.jsonl")] if store.root.exists() else []
    assert r.get("failures") or rows, f"search timeout reports {r['returned']} returned, {r['queries']} queries, no failure ledger"


def qualified_class(root, store, p):
    source(store, "s")
    row = claim(store, stance="QUALIFIES")
    profile = evidence.profile(p.questions[0], claims=[row], reviews={"c": {"verdict": "SUPPORTED"}})
    assert profile["by_class"]["for"] == {}, "QUALIFIES is counted on the agreeing side"


def historical_rejections(root, store, p):
    source(store, "s")
    claim(store)
    store.append("rejections.jsonl", {"claim_id": "c", "failure": "UNPARSEABLE_VALUE",
                                       "record": {"question_id": "Q"}})
    profile = built(store, p)
    assert not profile["gate_rejected"], "an accepted claim is also counted as currently rejected"


def registry_rollback(root, store, p):
    config.check_registry_drift(p, store)
    new = dataclasses.replace(p, registry_version=2, registry_sha256="fixture-v2", frozen_at="2026-09-28")
    config.check_registry_drift(new, store)
    try:
        config.check_registry_drift(p, store)
    except config.RegistryDrift:
        return
    raise AssertionError("returning to an already recorded lower registry version is accepted")


def unchecked_cli_registry(root, store, p):
    config.check_registry_drift(p, store)
    changed = dataclasses.replace(p, registry_sha256="changed-without-bump")
    with patch.object(cli, "load_project", return_value=changed), contextlib.redirect_stdout(io.StringIO()):
        status = cli.main(["discover", str(root), "--store", str(root), "--reclassify"])
    assert status == 2, f"discover --reclassify accepts same-version registry drift with exit {status}"


def reader_report_totals(root, store, p):
    q = model_call.Queue(store, lane="extract", batch="comparison")
    for model in ("model-a", "model-b"):
        store.append(q.results_name, {
            "call_id": "one-call", "backend": "one-backend", "model": model,
            "result_key": "one-call|one-backend|" + model, "ok": True,
        })
    r = model_report.summarise(store, lane="extract", batch="comparison")
    parts = sum(bucket["calls"] for bucket in r["by_reader"].values())
    assert r["calls"] == parts, f"report total={r['calls']}, sum of reader buckets={parts}"


PROBES = (
    pending_extraction, unattempted_acquisition, round_scope, round_hash, old_registry_claims,
    stale_underlying_evidence, numeric_boundaries, review_all_fields, cross_reader_identity,
    harvest_rejudged_answer, prompt_mismatch_rejudge, rechunk_ghosts, confirmed_class_floor,
    regate_class_policy, redirect_guards, discovery_failure, qualified_class, historical_rejections,
    registry_rollback, adjudicate_after_floor_failure, unchecked_cli_registry, reader_report_totals,
)


def snapshot():
    """Read-only measurement of the actual store; no CLI registry registration or stage writes."""
    repo = pathlib.Path(__file__).resolve().parents[2]
    for name in ("alembic-s4", "pilot-screen-time", "pmc-screen-time"):
        p = config.load_project(repo / "projects" / name)
        s = Store(name, base=repo / "store")
        measured = admissibility.admit(p, s)
        manifest = admissibility.admit(p, s, manifest_only=True)
        from claimstone import claim_records
        claims = claim_records.current(s)[0]
        chunks = chunk_sets.current(s)
        reviews = review.current(s)
        profiles = synthesize.latest_profiles(s)
        print(name, json.dumps({
            "found": measured["found"], "obtained": measured["obtained"],
            "confirmed": measured["confirmed"], "rate": measured["rate"],
            "basis": measured["basis"], "final": measured["final"], "status": measured["status"],
            "manifest_rate": manifest["rate"], "claims": len(claims), "chunks": len(chunks),
            "sources_chunked": len({c["source_id"] for c in chunks.values()}),
            "reviews": len(reviews), "historical_reviews": len(s.latest_by("reviews.jsonl", "claim_id")),
            "profiles": len(profiles),
            "adjudications": len(synthesize.adjudications(s)),
        }, sort_keys=True))
        for path in sorted(s.root.glob("calls/*/*/requests.jsonl")):
            lane, batch = path.parts[-3:-1]
            q = model_call.Queue(s, lane=lane, batch=batch)
            requests = q.requests()
            ok = {r["call_id"] for r in q.results().values() if r.get("ok")}
            from collections import Counter
            missing = [u for u in requests if u["call_id"] not in ok]
            print("batch", lane, batch, json.dumps({
                "requests": len(requests), "without_current_ok": len(missing),
                "unanswered_by_kind": dict(Counter(u.get("kind") for u in missing)),
            }, sort_keys=True))
            if name == "alembic-s4" and batch == "hetero-probe":
                report = model_report.summarise(s, lane=lane, batch=batch)
                print("hetero_probe_report_totals", json.dumps({
                    "total_calls": report["calls"],
                    "sum_reader_calls": sum(r["calls"] for r in report["by_reader"].values()),
                    "total_ok": report["ok"],
                    "sum_reader_ok": sum(r["ok"] for r in report["by_reader"].values()),
                    "readers": len(report["by_reader"]),
                }, sort_keys=True))
        if name == "pmc-screen-time":
            q4 = profiles["Q04"]
            print("Q04_historical", json.dumps({k: q4.get(k) for k in (
                "profile_sha256", "provisional", "coverage", "awaiting_review", "direction_count",
            )}, sort_keys=True))
            rejections = s.latest_by("rejections.jsonl", "claim_id")
            print("accepted_and_historically_rejected", len(set(claims) & set(rejections)))
            print("stored_profile_digests_match_full_payload", all(
                evidence._digest(row) == row.get("profile_sha256") for row in profiles.values()
            ))
        print("torn_tails", s.torn_tail)
    return 0


def main():
    if sys.argv[1:] == ["--snapshot"]:
        return snapshot()
    failures = 0
    for probe in PROBES:
        with tempfile.TemporaryDirectory(prefix="claimstone-review-") as temp:
            root = pathlib.Path(temp)
            s = Store("review-fixture", base=root)
            try:
                probe(root, s, project(root))
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {probe.__name__}: {exc}")
            else:
                print(f"PASS {probe.__name__}")
    print(f"{failures}/{len(PROBES)} unmet requirements reproduced; no real store or network used")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
