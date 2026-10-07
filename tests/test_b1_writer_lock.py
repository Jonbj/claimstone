"""B1 (F5): the project writer lock makes every read-modify-write a transaction.

The two windows the triage found — adjudicate's check-then-append and acquire's attempt
number read outside the lock — are each demonstrated by a test verified to fail against
the pre-B1 code (checked at 286a356, 2026-10-07), not by an assertion about implementation
details. The two-process test pins the lock primitive itself: it passed before B1 because
the primitive already existed, and it exists to keep it true. The flows lock is the project
lock by construction, and the test says so out loud so a future second lock cannot be
added without breaking it.
"""

import os
import pathlib
import subprocess
import sys
import threading

from claimstone import acquire, flows, synthesize
from claimstone.store import Store
from tests.test_adjudicate import RATIONALE
from tests.test_synthesize import _project, _store, claim, review

# A candidate shaped like the acquisition tests': source class present (invariant 6).
CANDIDATE = {"candidate_key": "doi:10.1234/abc", "source_id": "S01", "source_class": "ACA",
             "doi": "10.1234/abc", "url": "https://repo.example/paper.pdf", "title": "A paper"}

# What each child process runs: the read-modify-write an acquire does, fifteen times, through
# the writer. The code is passed on the command line so the test needs no helper file.
_CHILD = """
import sys
from claimstone.store import Store
store = Store("race", base=sys.argv[1])
key = sys.argv[2]
for _ in range(15):
    with store.writer_lock():
        latest = store.latest_by("acquisitions.jsonl", "candidate_key").get(key)
        attempt_no = int((latest or {}).get("attempt_no") or 0) + 1
        store.append("acquisitions.jsonl", {"candidate_key": key, "attempt_no": attempt_no})
"""


def test_two_processes_appending_through_the_writer_leave_no_duplicate_and_no_torn_tail(tmp_path):
    repo_root = str(pathlib.Path(__import__("claimstone").__file__).resolve().parent.parent)
    env = dict(os.environ, PYTHONPATH=repo_root)
    procs = [subprocess.Popen([sys.executable, "-c", _CHILD, str(tmp_path), f"doi:10.1234/{i}"],
                              env=env) for i in ("a", "b")]
    for proc in procs:
        assert proc.wait(timeout=60) == 0

    store = Store("race", base=tmp_path)
    rows = list(store.read("acquisitions.jsonl"))
    # Thirty appends landed, none lost and none interleaved mid-line.
    assert len(rows) == 30
    assert (tmp_path / "race" / "acquisitions.jsonl").read_bytes().endswith(b"\n")
    assert store.torn_tail == []
    seen = {(r["candidate_key"], r["attempt_no"]) for r in rows}
    # No duplicate attempt number: the one failure mode the lock exists to prevent.
    assert len(seen) == 30
    for key in ("doi:10.1234/a", "doi:10.1234/b"):
        assert sorted(r["attempt_no"] for r in rows if r["candidate_key"] == key) == list(range(1, 16))


def test_a_competing_acquisition_landing_after_the_prior_read_gets_no_duplicate_attempt_no(
        tmp_path, monkeypatch):
    """The race B1.2 closes: `run` reads the ledger once up front, and a writer appending
    between that read and the append used to produce two rows with attempt_no 1."""
    store = Store("race", base=tmp_path)

    def racing_acquire_one(fetcher, store_, candidate_, **kwargs):
        # A concurrent writer lands its row for the same candidate between run's earlier
        # read and the append. Pre-B1 this produced two attempt_no 1 rows.
        store_.append("acquisitions.jsonl",
                      {"candidate_key": candidate_["candidate_key"], "attempt_no": 1,
                       "acquired": False})
        return {"candidate_key": candidate_["candidate_key"], "source_class": candidate_["source_class"],
                "acquired": False, "failure_class": "NO_LOCATIONS", "attempts": []}

    monkeypatch.setattr(acquire, "acquire_one", racing_acquire_one)
    rows = list(acquire.run([CANDIDATE], store, fetcher=None, use_apis=False))
    assert [r["attempt_no"] for r in rows] == [2]
    # And both rows stand in the ledger, distinct and in order.
    assert [r["attempt_no"] for r in store.read("acquisitions.jsonl")] == [1, 2]


def test_adjudicate_holds_the_lock_across_the_check_and_the_signature(tmp_path, monkeypatch):
    """The race B1.1 closes: a profile change could land between the staleness check and the
    append, leaving a signature on a hash that was already old. The lock makes the three steps
    one transaction, which this test observes from inside it: while adjudicate runs its
    preview, a competing append cannot complete and the lock is reported held."""
    store = _store(tmp_path, claims=[claim()], reviews=[review()])
    synthesize.build(_project(tmp_path), store)
    project = _project(tmp_path)
    profile_sha256 = synthesize.latest_profiles(store)["H02"]["profile_sha256"]

    real_preview = synthesize.preview
    observed = {}

    def watched_preview(project_, store_, **kwargs):
        observed["lock_held"] = store_.writer_busy()
        competing = threading.Thread(
            target=lambda: store_.append("race_probe.jsonl", {"probe": True}), daemon=True)
        competing.start()
        competing.join(0.5)
        observed["competing_append_finished"] = not competing.is_alive()
        observed["competing"] = competing
        return real_preview(project_, store_, **kwargs)

    monkeypatch.setattr(synthesize, "preview", watched_preview)
    synthesize.adjudicate(store, "H02", project=project, verdict="SUPPORTED",
                          rationale=RATIONALE, by="an operator", profile_sha256=profile_sha256)
    assert observed["lock_held"] is True
    # Blocked on the same hold adjudicate has not released yet — the third window is closed.
    assert observed["competing_append_finished"] is False
    # And the hold ends with the call: the competing append lands afterwards, not during.
    observed["competing"].join(5)
    assert store.writer_busy() is False
    assert list(store.read("race_probe.jsonl")) == [{"probe": True}]


def test_the_flows_lock_is_the_project_writer_lock_by_construction(tmp_path):
    """There is one lock, not two to order: `flows._flows_lock` delegates to
    `Store.writer_lock`, so a flow transaction and an acquire append cannot interleave, and
    no lock-order rule has anything to invert."""
    store = Store("flows-lock", base=tmp_path)
    with flows._flows_lock(store):
        assert store.writer_busy() is True
    assert store.writer_busy() is False