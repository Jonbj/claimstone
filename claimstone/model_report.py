"""What a queue cost and how fast it went.

Two rules, both about not producing a figure that describes nothing. A `null` cost is reported
as unpriced rather than folded into a total, because a subscription has no per-call price and a
total that absorbed it would be wrong without saying so. And throughput is stated per backend:
the local server runs at about five calls an hour where a hosted endpoint finishes the same
queue in an afternoon, so an average across them describes neither.
"""

from __future__ import annotations

from typing import Any

from claimstone.store import Store


def summarise(store: Store, *, lane: str, batch: str) -> dict[str, Any]:
    """Per backend and model: calls, outcomes, tokens, cost, observed throughput."""
    # Every attempt, not the latest per call: a timeout that cost money and was retried is two
    # payments, and collapsing them reports one. Correctness is counted on the collapse below.
    attempts = list(store.read(f"calls/{lane}/{batch}/results.jsonl"))
    current: dict[str, dict[str, Any]] = {}
    for row in attempts:
        current[f"{row.get('call_id')}|{row.get('backend')}"] = row

    by_backend: dict[str, dict[str, Any]] = {}
    for row in attempts:
        key = str(row.get("backend") or "unknown")
        bucket = by_backend.setdefault(key, {
            # `attempts` is what was paid for and waited on; `calls` is how many distinct calls
            # this backend answered. They are different numbers and a retry is what separates
            # them, so they have different names — a single field called `calls` made
            # sum(by_backend[*]["calls"]) disagree with summary["calls"] with no explanation,
            # inside the one artifact whose whole job is to be trusted about numbers.
            "attempts": 0, "calls": 0, "ok": 0, "unpriced": 0,
            "cost_usd": None, "latency_total_s": 0.0,
            "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
            "models": set(), "answered": set(), "failures_by_class": {},
        })
        bucket["attempts"] += 1
        bucket["answered"].add(str(row.get("call_id")))
        bucket["models"].add(str(row.get("model") or "unknown"))
        if row.get("ok"):
            bucket["ok"] += 1
        else:
            name = str(row.get("failure_class"))
            bucket["failures_by_class"][name] = bucket["failures_by_class"].get(name, 0) + 1

        cost = row.get("cost_usd")
        if cost is None:
            bucket["unpriced"] += 1
        else:
            bucket["cost_usd"] = round((bucket["cost_usd"] or 0.0) + float(cost), 8)

        bucket["latency_total_s"] += float(row.get("latency_s") or 0.0)
        usage = row.get("usage") or {}
        for field_name in ("input_tokens", "cached_input_tokens", "output_tokens"):
            bucket[field_name] += int(usage.get(field_name) or 0)

    for bucket in by_backend.values():
        spent = bucket.pop("latency_total_s")
        bucket["calls"] = len(bucket.pop("answered"))
        # Observed, not promised: the rate this queue actually ran at on this backend. Named for
        # attempts because that is what it counts — every attempt is time the queue spent, and it is
        # the figure that answers "how long will the rest of this take".
        bucket["attempts_per_hour"] = (bucket["attempts"] / spent * 3600) if spent else None
        bucket["models"] = sorted(bucket["models"])
        bucket["failures_by_class"] = dict(
            sorted(bucket["failures_by_class"].items(), key=lambda kv: -kv[1])
        )

    # Both totals are the sum of their per-backend parts, by construction. A report whose parts do
    # not add up to its total is a report nobody can use.
    return {
        "lane": lane,
        "batch": batch,
        # Distinct (call, backend) pairs currently answered, and how many of those stand valid.
        "calls": len(current),
        "ok": sum(1 for row in current.values() if row.get("ok")),
        # What was actually paid for and waited on, retries included.
        "attempts": len(attempts),
        "by_backend": dict(sorted(by_backend.items())),
    }
