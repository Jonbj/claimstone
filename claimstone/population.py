"""A declared metadata population, independent of acquisition success or study conclusions."""
from __future__ import annotations

import datetime
import hashlib
import json
from urllib.parse import urlsplit

POPULATION_VERSION = 1


def validate(raw):
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("population must be a mapping")
    allowed = {"version", "declared_at", "rationale", "hosts", "source_apis", "venues"}
    if set(raw) - allowed:
        raise ValueError(f"unknown population fields: {sorted(set(raw) - allowed)}")
    if type(raw.get("version")) is not int or raw["version"] < 1:
        raise ValueError("population.version must be a positive integer")
    try:
        datetime.date.fromisoformat(str(raw.get("declared_at", "")))
    except ValueError as exc:
        raise ValueError("population.declared_at must be an ISO date") from exc
    if not isinstance(raw.get("rationale"), str) or not raw["rationale"].strip():
        raise ValueError("population.rationale is required")
    result = dict(raw)
    for name in ("hosts", "source_apis", "venues"):
        values = raw.get(name, [])
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError(f"population.{name} must be a list of nonempty strings")
        result[name] = sorted(set(v.strip().lower() for v in values))
    if not any(result[name] for name in ("hosts", "source_apis", "venues")):
        raise ValueError("population requires at least one metadata predicate")
    if any("/" in host or "*" in host or ":" in host for host in result["hosts"]):
        raise ValueError("population.hosts requires exact hostnames, without wildcards")
    return result


def digest(policy):
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def decide(policy, candidate):
    if not policy:
        return True, "unrestricted"
    # Seed membership was declared before outcomes. It is not a discovered downloadable subset.
    if candidate.get("source_api") == "manifest":
        return True, "declared_seed"
    if str(candidate.get("source_api", "")).lower() in policy["source_apis"]:
        return True, "source_api"
    try:
        host = (urlsplit(str(candidate.get("url") or "")).hostname or "").lower()
    except ValueError:
        host = ""  # Malformed external metadata cannot match a declared hostname.
    if host in policy["hosts"]:
        return True, "host"
    if str(candidate.get("venue", "")).strip().lower() in policy["venues"]:
        return True, "venue"
    return False, "no_declared_metadata_match"


def check_round(store, policy, round_name, *, record=True):
    """Freeze the actual predicate per round, including its absence. Changes need a new round."""
    if not policy:
        # Legacy unrestricted stores are unchanged. Refuse removing a held declaration.
        held = store.latest_by("populations.jsonl", "round").get(round_name)
        if held and held["policy_sha256"] != digest({}):
            raise ValueError("population removed from a declared round")
        return
    held = store.latest_by("populations.jsonl", "round").get(round_name)
    if held and held["policy_sha256"] != digest(policy):
        raise ValueError("population changed in an existing round; declare a new round")
    if not held:
        if any(row.get("round") == round_name for row in store.read("candidates.jsonl")):
            raise ValueError("cannot retrofit population onto a round that already has candidates")
        if record:
            store.append("populations.jsonl", {
                "round": round_name, "population_version": POPULATION_VERSION,
                "policy_sha256": digest(policy), "policy": policy,
                "declared_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })


def observe(store, policy, candidate):
    admitted, reason = decide(policy, candidate)
    if policy:
        store.append("discovery_population.jsonl", {
            **candidate, "population_version": POPULATION_VERSION,
            "policy_sha256": digest(policy), "admitted": admitted, "population_reason": reason,
        })
    return admitted
