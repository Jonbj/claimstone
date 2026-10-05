"""dashboard: wiring and the two refusals — spec §12 table, row two.

The HTTP layer is tested for routing, the 405, the torn tail and the loopback rule; content is
`round_state`'s business and is tested there. One real GET against a port-0 bind proves wiring.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager

import pytest

from claimstone import dashboard
from claimstone.config import load_project
from claimstone.store import Store


@pytest.fixture()
def project():
    return load_project("projects/example-news-and-returns")


@pytest.fixture()
def server(project, tmp_path):
    store = Store("fixture", base=tmp_path)
    store.append("claims.jsonl", {
        "claim_id": "c1", "question_id": "Q01", "harvested_at": "2026-09-28T10:00:00+00:00"})
    store.append("profiles.jsonl", {
        "question_id": "Q01", "round": None, "manifest_only": False,
        "coverage": {"sources": 1, "examined": 3}, "provisional": False,
        "state": None, "profile_sha256": "a" * 64})
    httpd = dashboard.make_server(project, store, host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    thread.join(timeout=5)


def _get(url: str):
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


@contextmanager
def _served(project, store):
    """A real server on a real port around a caller-built store, torn down cleanly."""
    httpd = dashboard.make_server(project, store, host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _base(httpd) -> str:
    return f"http://127.0.0.1:{httpd.server_address[1]}"


def test_one_real_get_proves_the_wiring(server):
    status, body = _get(f"http://127.0.0.1:{server.server_address[1]}/")
    assert status == 200
    assert body.startswith("<!doctype html>")
    # Self-contained (§11): no external reference of any kind.
    assert "http://" not in body.replace("http://127.0.0.1", "")
    assert "https://" not in body and "<link" not in body
    # Honesty probes are behaviour, not template prose. The spine's coverage fraction is the
    # fixture profile's own 1 of 3, and the discover node — the engine's computed detail — carries
    # the not-estimable note with no meter and no percentage anywhere in it (§6; D10 forbids
    # inventing the denominator).
    assert "1 / 3" in body
    discover = body.split('id="stage-discover">')[1].split('id="stage-acquire"')[0]
    assert "completeness not estimable" in discover
    assert "meter" not in discover and "%" not in discover


def test_api_routes_answer_json(server):
    base = f"http://127.0.0.1:{server.server_address[1]}"
    _, state = _get(f"{base}/api/state")
    assert set(json.loads(state)) == {"ledgers", "running", "pid_note"}
    _, rounds = _get(f"{base}/api/round")
    payload = json.loads(rounds)
    assert payload["project"]
    assert len(payload["stages"]) == 6
    _, questions = _get(f"{base}/api/questions")
    # The spine is one object serving two routes: /api/round and /api/questions must agree.
    assert payload["questions"] == json.loads(questions)["questions"]
    assert json.loads(questions)["questions"]
    _, activity = _get(f"{base}/api/activity?limit=1")
    assert len(json.loads(activity)["rows"]) == 1


def test_post_answers_405_and_so_does_every_non_routed_request(server):
    base = f"http://127.0.0.1:{server.server_address[1]}"
    request = urllib.request.Request(f"{base}/", data=b"{}", method="POST")
    with pytest.raises(urllib.error.HTTPError) as raised:
        urllib.request.urlopen(request, timeout=5)
    assert raised.value.code == 405
    # Spec §9, literally: anything that is not a routed GET — including an unknown path.
    with pytest.raises(urllib.error.HTTPError) as unknown:
        urllib.request.urlopen(f"{base}/api/secret", timeout=5)
    assert unknown.value.code == 405


def _raw_verb(server, verb: str, path: str = "/") -> bytes:
    import socket
    with socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=5) as sock:
        sock.sendall(f"{verb} {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
                     .encode())
        chunks = []
        while True:
            data = sock.recv(65536)
            if not data:
                break
            chunks.append(data)
    return b"".join(chunks)


def test_head_is_refused_without_a_body(server):
    """§9 refuses HEAD with 405; RFC 9110 §9.3.2 forbids the body the old refusal wrote."""
    for path in ("/", "/api/state"):
        raw = _raw_verb(server, "HEAD", path)
        head, _, body = raw.partition(b"\r\n\r\n")
        assert raw.startswith(b"HTTP/1.0 405"), path
        assert b"Allow: GET" in head
        assert body == b"", path


def test_options_and_unknown_verbs_answer_405_not_501(server):
    """§9 is every verb — including ones http.server would dispatch to a 501."""
    for verb in ("OPTIONS", "TRACE", "BICYCLE"):
        assert _raw_verb(server, verb).startswith(b"HTTP/1.0 405"), verb


def test_torn_final_line_still_serves(project, tmp_path):
    """A stage writing while the dashboard reads: the reader skips the fragment and answers."""
    store = Store("fixture", base=tmp_path)
    store.append("profiles.jsonl", {
        "question_id": "Q01", "round": None, "manifest_only": False,
        "coverage": {"sources": 0, "examined": 2}, "provisional": True,
        "blocking": ["awaiting_review"], "state": "NO_VERIFIED_CLAIM",
        "profile_sha256": "b" * 64})
    with store.path("claims.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"claim_id": "c9", "question_i')      # a crash's half-written row
    with _served(project, store) as httpd:
        status, page = _get(_base(httpd) + "/")             # the promise is that it *serves*
    assert status == 200                                    # 200 over the wire, not just rendered
    assert page.startswith("<!doctype html>")
    assert "NO_VERIFIED_CLAIM" in page                      # the complete rows carried on


def test_concurrent_reads_while_a_stage_appends_with_torn_tails(server):
    """§9 concurrency: two live GETs beside a writer that keeps crash-ending its lines."""
    base = f"http://127.0.0.1:{server.server_address[1]}"
    store = server.RequestHandlerClass.store
    failures = []

    def writer():
        for i in range(100):
            store.append("extract_requests.jsonl", {"seq": i,
                                                    "at": f"2026-09-28T10:00:{i % 60:02d}+00:00"})
            with store.path("normalize_events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write('{"seq": 999, "half_wri')   # a crash's half-written row, on purpose

    def reader():
        for _ in range(50):
            for path in ("/", "/api/state"):
                try:
                    status, body = _get(base + path)
                    if status != 200 or (path == "/" and not body.startswith("<!doctype html>")) \
                            or (path == "/api/state" and not isinstance(json.loads(body), dict)):
                        failures.append(path)
                except Exception as exc:              # noqa: BLE001 - the assertion is "none"
                    failures.append((path, repr(exc)))

    threads = [threading.Thread(target=writer)] + [threading.Thread(target=reader) for _ in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert failures == []
    status, body = _get(f"{base}/")
    assert status == 200 and body.startswith("<!doctype html>")   # the page still renders


def test_loopback_by_default_and_warning_names_the_rule_when_not():
    assert dashboard.host_warning("127.0.0.1") is None
    assert dashboard.host_warning("::1") is None
    assert dashboard.host_warning("127.0.0.2") is None   # the whole 127/8 is loopback (§10)
    warning = dashboard.host_warning("0.0.0.0")
    assert warning is not None
    # §10: the warning names the privacy rule and why it exists, not a generic best practice.
    assert "reading list" in warning
    assert "gitignored" in warning


def test_page_carries_the_five_states_plus_the_engine_one(server):
    """Five verdict states, visually five — and NO_VERIFIED_CLAIM never among them as a verdict."""
    _, body = _get(f"http://127.0.0.1:{server.server_address[1]}/")
    # Colour never carries meaning alone (§8): every state chip pairs its dot with its word, so
    # each name must appear *inside* a dot-chip, not merely somewhere on the page.
    for state in ("SUPPORTED", "CONTRADICTED", "CONTESTED_IN_LITERATURE",
                  "UNANSWERED_IN_LITERATURE", "NEVER_ASKED", "NO_VERIFIED_CLAIM"):
        assert f'<span class="dot"></span>{state}</span>' in body, state
    assert '<span class="dot"></span></span>' not in body      # no chip is ever left empty
    assert body.count('<span class="dot"></span>') >= 6        # every state chip carries a dot


def test_a_stale_verdict_is_shown_as_stale_and_never_hidden(server):
    """§8: an adjudication whose evidence moved is still rendered, annotated as stale."""
    store = server.RequestHandlerClass.store
    store.append("adjudications.jsonl", {
        "question_id": "Q01", "round": None, "manifest_only": False,
        "verdict": "CONTRADICTED", "profile_sha256": "e" * 64,
        "adjudicated_at": "2026-09-28T11:00:00+00:00"})
    _, body = _get(_base(server) + "/")
    # Two CONTRADICTED chips now: the legend's, and the question's — the verdict was not hidden.
    assert body.count('<span class="dot"></span>CONTRADICTED</span>') == 2
    assert '<span class="chip bad"><span class="dot"></span>stale — evidence moved</span>' in body
    assert "1 stale" in body                                   # the counts line says it too


def test_api_round_reports_an_unavailable_spine_instead_of_crashing(project, tmp_path):
    """An inadmissible store is state, not a stack trace: the refusal must reach the page."""
    store = Store("fixture", base=tmp_path)
    store.append("registry.jsonl", {
        "registry_version": project.registry_version, "registry_sha256": "0" * 64,
        "frozen_at": project.frozen_at})                      # same version, changed text (inv. 5)
    with _served(project, store) as httpd:
        status, payload = _get(_base(httpd) + "/api/round")
        data = json.loads(payload)
        assert status == 200                                   # a refusal is not an error code
        assert "registry changed" in data["unavailable"]
        assert "invariant 5" in data["unavailable"]
        assert [q["id"] for q in data["questions"]] == [q.id for q in project.questions]
        status, page = _get(_base(httpd) + "/")
    assert status == 200
    assert "<h2>corpus</h2>" in page                           # the page shows why, in words
    assert "invariant 5" in page


def test_activity_limit_is_clamped_over_http_not_trusted(project, tmp_path):
    """§9's promise on the wire: default 50, capped at 500, and no limit flips the slice."""
    store = Store("fixture", base=tmp_path)
    for i in range(600):
        store.append("claims.jsonl", {
            "claim_id": f"c{i}", "question_id": "Q01",
            "harvested_at": f"2026-09-28T10:00:{i % 60:02d}+00:00"})
    with _served(project, store) as httpd:
        base = _base(httpd)
        negative = json.loads(_get(f"{base}/api/activity?limit=-5")[1])["rows"]
        assert len(negative) == 1                              # newest only; never a wrapped slice
        assert negative[0]["row"]["claim_id"]
        huge = json.loads(_get(f"{base}/api/activity?limit=9999")[1])["rows"]
        assert len(huge) == 500                                # six hundred rows, five hundred shown
        nonsense = json.loads(_get(f"{base}/api/activity?limit=nonsense")[1])["rows"]
        assert len(nonsense) == 50                             # unparsable falls back to the default
        _, page = _get(base + "/")
        assert page.count('<div class="r">') == 50             # the page shows its own 50 of 600
