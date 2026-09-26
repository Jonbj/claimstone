"""What the queue cost and how fast it went — per backend, because the rates differ hugely."""

from claimstone import model_report
from claimstone.store import Store


def result(call_id, *, backend, model="m", cost=None, latency=2.0, ok=True, failure=None,
           usage=None):
    return {"call_id": call_id, "backend": backend, "model": model, "ok": ok,
            "failure_class": failure, "cost_usd": cost, "latency_s": latency,
            "usage": usage or {"input_tokens": 100, "output_tokens": 50}}


def _store(tmp_path, rows):
    store = Store("t", base=tmp_path)
    for row in rows:
        store.append("calls/extract/b1/results.jsonl", row)
    return store


def test_a_retry_is_two_payments_not_one(tmp_path):
    # A timeout that cost money and was retried was paid for twice. Summing the collapse would
    # report one, and "what did this batch cost" is the question the report exists to answer.
    store = _store(tmp_path, [
        result("a", backend="x", cost=0.001, ok=False, failure="TIMEOUT"),
        result("a", backend="x", cost=0.002),
    ])
    summary = model_report.summarise(store, lane="extract", batch="b1")
    assert summary["calls"] == 1
    assert summary["attempts"] == 2
    assert summary["by_backend"]["x"]["cost_usd"] == 0.003


def test_two_backends_over_the_same_calls_are_not_collapsed(tmp_path):
    store = _store(tmp_path, [result("a", backend="x"), result("a", backend="y")])
    summary = model_report.summarise(store, lane="extract", batch="b1")
    assert summary["calls"] == 2
    assert set(summary["by_backend"]) == {"x", "y"}


def test_cost_is_summed_per_backend_and_model(tmp_path):
    store = _store(tmp_path, [result("a", backend="ollama-cloud", cost=0.001),
                              result("b", backend="ollama-cloud", cost=0.002)])
    summary = model_report.summarise(store, lane="extract", batch="b1")
    bucket = summary["by_backend"]["ollama-cloud"]
    assert bucket["calls"] == 2
    assert bucket["cost_usd"] == 0.003


def test_an_unpriced_call_is_counted_but_not_summed(tmp_path):
    # Folding a null price into a total would make the total a number that is not true.
    store = _store(tmp_path, [result("a", backend="claude-cli", cost=None),
                              result("b", backend="claude-cli", cost=None)])
    bucket = model_report.summarise(store, lane="extract", batch="b1")["by_backend"]["claude-cli"]
    assert bucket["calls"] == 2
    assert bucket["unpriced"] == 2
    assert bucket["cost_usd"] is None


def test_a_mixed_backend_reports_both_the_total_and_what_it_excludes(tmp_path):
    store = _store(tmp_path, [result("a", backend="x", cost=0.5),
                              result("b", backend="x", cost=None)])
    bucket = model_report.summarise(store, lane="extract", batch="b1")["by_backend"]["x"]
    assert bucket["cost_usd"] == 0.5
    assert bucket["unpriced"] == 1


def test_throughput_is_per_backend(tmp_path):
    # ~5 calls an hour locally against an afternoon for the same queue on a hosted endpoint:
    # an aggregate figure across the two would describe neither.
    store = _store(tmp_path, [result("a", backend="llamacpp", latency=696.0),
                              result("b", backend="ollama-cloud", latency=3.0)])
    by_backend = model_report.summarise(store, lane="extract", batch="b1")["by_backend"]
    assert round(by_backend["llamacpp"]["attempts_per_hour"], 1) == 5.2
    assert round(by_backend["ollama-cloud"]["attempts_per_hour"]) == 1200


def test_failures_are_broken_down_by_class(tmp_path):
    store = _store(tmp_path, [result("a", backend="x", ok=False, failure="SCHEMA_INVALID"),
                              result("b", backend="x", ok=False, failure="SCHEMA_INVALID"),
                              result("c", backend="x", ok=True)])
    bucket = model_report.summarise(store, lane="extract", batch="b1")["by_backend"]["x"]
    assert bucket["ok"] == 1
    assert bucket["attempt_failures_by_class"] == {"SCHEMA_INVALID": 2}


def test_an_empty_batch_has_no_throughput_rather_than_zero(tmp_path):
    store = _store(tmp_path, [])
    summary = model_report.summarise(store, lane="extract", batch="b1")
    assert summary["by_backend"] == {}
    assert summary["calls"] == 0


def test_the_parts_add_up_to_the_totals(tmp_path):
    """A report whose per-backend numbers do not sum to its totals is a report nobody can use.

    They did not. One field named `calls` held attempts per backend and distinct calls at the top,
    so summary["calls"] said 2 while the buckets summed to 3, with nothing to say which was meant.
    """
    store = _store(tmp_path, [
        result("a", backend="x", cost=0.001, ok=False, failure="TIMEOUT"),
        result("a", backend="x", cost=0.002),
        result("b", backend="x", cost=0.004),
        result("a", backend="y", cost=0.010),
    ])
    summary = model_report.summarise(store, lane="extract", batch="b1")
    assert summary["attempts"] == sum(b["attempts"] for b in summary["by_backend"].values())
    assert summary["calls"] == sum(b["calls"] for b in summary["by_backend"].values())
    assert (summary["calls"], summary["attempts"]) == (3, 4)
    assert (summary["by_backend"]["x"]["calls"], summary["by_backend"]["x"]["attempts"]) == (2, 3)


def test_throughput_counts_every_attempt_because_every_attempt_took_time(tmp_path):
    store = _store(tmp_path, [
        result("a", backend="x", latency=1800.0, ok=False, failure="TIMEOUT"),
        result("a", backend="x", latency=1800.0),
    ])
    bucket = model_report.summarise(store, lane="extract", batch="b1")["by_backend"]["x"]
    # One call answered, one hour spent across two attempts. 2.0 attempts an hour is what the
    # backend did; 1.0 would be the rate if the timed-out half hour had not happened, and it did.
    assert bucket["calls"] == 1
    assert round(bucket["attempts_per_hour"], 2) == 2.0


def test_a_rejudgement_is_current_but_is_not_an_attempt(tmp_path):
    """D14 again, in the report. A re-judgement re-reads bytes already paid for, so counting it
    would inflate what the queue cost and deflate how fast it went — while its verdict is the one
    that now stands."""
    store = _store(tmp_path, [
        result("a", backend="x", cost=0.002, latency=60.0, ok=False, failure="NOT_JSON"),
        {**result("a", backend="x", cost=None, latency=0.0, ok=True), "rejudged_from": "then"},
    ])
    summary = model_report.summarise(store, lane="extract", batch="b1")
    bucket = summary["by_backend"]["x"]
    assert summary["attempts"] == 1
    assert (bucket["attempts"], bucket["calls"]) == (1, 1)
    assert bucket["cost_usd"] == 0.002
    assert round(bucket["attempts_per_hour"]) == 60
    # And the answer that stands is the re-read one.
    assert summary["ok"] == 1
    assert bucket["ok"] == 1


def test_a_batch_that_is_only_rejudgements_has_no_throughput_rather_than_infinity(tmp_path):
    store = _store(tmp_path, [
        {**result("a", backend="x", cost=None, latency=0.0, ok=True), "rejudged_from": "then"}])
    bucket = model_report.summarise(store, lane="extract", batch="b1")["by_backend"]["x"]
    assert bucket["attempts"] == 0
    assert bucket["calls"] == 1
    assert bucket["attempts_per_hour"] is None
