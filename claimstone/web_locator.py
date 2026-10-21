"""Find where a work we already know about might be read for free on the open web (D145, issue #4).

This is a **locator for a known work**, not a discovery channel: the title is known, so a result can be checked
against it; at discovery nothing could be. It changes the numerator (obtained), never the denominator (found).

How it is kept honest:

* **Results are leads before they are files.** The search writes every result it saw, with the host policy's
  decision on it, to `web_locator.jsonl`. The portal shows the leads; a person may open one and upload the PDF
  themselves. Claimstone fetches one only when the project declared `web_locator` in `sources.yaml` *and* a
  plan named that exact host (the same gate every acquisition passes).
* **Host policy is project data** (invariant 4): `allow_host_patterns`, `allow_hosts`, `deny_hosts`. The
  project's `excluded_hosts` (shadow libraries) always win. A host that is neither allowed nor denied is
  `UNCLASSIFIED` and never fetched; it is listed so a person can classify it once, never promoted silently.
  There is no "author site" heuristic: a personal site stays unclassified until a person allows its host.
* **Identity is checked on what was read.** A web result carries no warrant that it is the work. After the file is
  parsed, its own title is compared with the candidate's; a clear mismatch is `WRONG_DOCUMENT` and a file with no
  usable title is `IDENTITY_UNVERIFIED`. Neither counts toward the floor. The bytes are kept.
* **Not reproducible, so stored.** Web rankings change; what is reproducible is the result list, the bytes and
  their hashes, all recorded.
"""

from __future__ import annotations

import datetime as _dt
import difflib
import fnmatch
import urllib.parse
from typing import Any, Iterable

from claimstone import ids, net
from claimstone.store import sha256_text

LOCATOR_VERSION = 1
IDENTITY_CHECK_VERSION = 2
LEDGER = "web_locator.jsonl"
PROVIDER = "brave"
ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

ALLOWED = "ALLOWED"
DENIED = "DENIED"
DENIED_EXCLUDED = "DENIED_EXCLUDED"
UNCLASSIFIED = "UNCLASSIFIED"
DECISIONS = (ALLOWED, DENIED, DENIED_EXCLUDED, UNCLASSIFIED)

WRONG_DOCUMENT = "WRONG_DOCUMENT"
IDENTITY_UNVERIFIED = "IDENTITY_UNVERIFIED"

POLICY_KEYS = ("enabled", "provider", "allow_host_patterns", "allow_hosts", "deny_hosts", "max_results")
DEFAULT_MAX_RESULTS = 5
# Similarity of the parsed title to the candidate's title at or above which a file is the work. Declared here as
# the instrument's own constant (identity_check_version 1) and to be measured, not tuned per file.
TITLE_SIMILARITY = 0.88


# --- policy -------------------------------------------------------------------------------------------

def validate_policy(raw: Any) -> dict[str, Any]:
    """The `web_locator` block of `sources.yaml`, checked. A misspelt key is an error, not a silent default."""
    from claimstone.config import ConfigError

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError("sources.yaml: 'web_locator' must be a mapping")
    unknown = sorted(set(raw) - set(POLICY_KEYS))
    if unknown:
        raise ConfigError(f"sources.yaml: 'web_locator' has unknown key(s) {', '.join(unknown)}; "
                          f"allowed: {', '.join(POLICY_KEYS)}")
    if not isinstance(raw.get("enabled", False), bool):
        raise ConfigError("sources.yaml: web_locator.enabled must be true or false")
    if raw.get("provider", PROVIDER) != PROVIDER:
        raise ConfigError(f"sources.yaml: web_locator.provider must be '{PROVIDER}' (the only adapter)")
    for key in ("allow_host_patterns", "allow_hosts", "deny_hosts"):
        value = raw.get(key, [])
        if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
            raise ConfigError(f"sources.yaml: web_locator.{key} must be a list of non-empty strings")
    limit = raw.get("max_results", DEFAULT_MAX_RESULTS)
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ConfigError("sources.yaml: web_locator.max_results must be an integer from 1 to 10")
    return {"enabled": bool(raw.get("enabled", False)), "provider": PROVIDER,
            "allow_host_patterns": [v.strip().lower() for v in raw.get("allow_host_patterns", [])],
            "allow_hosts": [v.strip().lower() for v in raw.get("allow_hosts", [])],
            "deny_hosts": [v.strip().lower() for v in raw.get("deny_hosts", [])],
            "max_results": limit}


def policy_digest(policy: dict[str, Any]) -> str:
    import json

    return sha256_text(json.dumps(policy, sort_keys=True, ensure_ascii=False))


def _matches(host: str, patterns: Iterable[str]) -> bool:
    for pattern in patterns:
        if "*" in pattern or "?" in pattern:
            if fnmatch.fnmatchcase(host, pattern):
                return True
        elif host == pattern or host.endswith("." + pattern):
            return True
    return False


def decide(url: str, policy: dict[str, Any], excluded_hosts: Iterable[str] = ()) -> tuple[str, str]:
    """(decision, reason) for one result address. Order: excluded, denied, allowed, otherwise unclassified."""
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        return DENIED, "not an http(s) address"
    if _matches(host, [h.lower() for h in excluded_hosts]):
        return DENIED_EXCLUDED, f"{host} is in the project's excluded hosts"
    if _matches(host, policy.get("deny_hosts", [])):
        return DENIED, f"{host} is on the project's deny list"
    if host in policy.get("allow_hosts", []) or _matches(host, policy.get("allow_host_patterns", [])):
        return ALLOWED, f"{host} is allowed by the project's policy"
    return UNCLASSIFIED, f"{host} is neither allowed nor denied by the project's policy"


# --- search -------------------------------------------------------------------------------------------

def queries_for(candidate: dict[str, Any]) -> list[str]:
    """The exact-title query first, the bare title second (asked only if the first returned nothing)."""
    title = " ".join(str(candidate.get("title") or "").split())
    if len(title) < 15:  # the floor `resolve_doi_by_title` already uses: a short fragment matches anything
        return []
    return [f'"{title}" filetype:pdf', f'"{title}"']


def search_url(query: str, count: int) -> str:
    return ENDPOINT + "?" + urllib.parse.urlencode({"q": query, "count": min(max(count, 1), 20)})


def parse_results(payload: Any) -> list[dict[str, Any]]:
    rows = (((payload or {}).get("web") or {}).get("results")) if isinstance(payload, dict) else None
    out = []
    for rank, item in enumerate(rows or [], start=1):
        if isinstance(item, dict) and isinstance(item.get("url"), str):
            out.append({"rank": rank, "url": item["url"], "title": str(item.get("title") or ""),
                        "description": str(item.get("description") or "")[:300]})
    return out


def observation(candidate: dict[str, Any], query: str, results: list[dict[str, Any]], policy: dict[str, Any],
                excluded_hosts: Iterable[str], *, ok: bool, failure_class: str | None, policy_source: str,
                campaign: str | None = None) -> dict[str, Any]:
    """One ledger row: the query, every result seen with the policy's decision on it. Nothing is dropped."""
    judged = []
    for item in results:
        decision, reason = decide(item["url"], policy, excluded_hosts)
        judged.append(item | {"host": (urllib.parse.urlsplit(item["url"]).hostname or "").lower(),
                              "decision": decision, "reason": reason})
    return {
        "locator_version": LOCATOR_VERSION, "provider": PROVIDER,
        "candidate_key": candidate.get("candidate_key"), "doi": candidate.get("doi"),
        "title": candidate.get("title"), "query": query, "query_sha256": sha256_text(query),
        "queried_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "ok": ok, "failure_class": failure_class, "campaign": campaign,
        "policy_source": policy_source, "policy_sha256": policy_digest(policy),
        "max_results": int(policy.get("max_results", DEFAULT_MAX_RESULTS)),
        "results": judged, "allowed": sum(1 for r in judged if r["decision"] == ALLOWED),
    }


def latest_by_candidate(store) -> dict[str, list[dict[str, Any]]]:
    """Every observation of a candidate, oldest first. An absent ledger is an empty answer."""
    out: dict[str, list[dict[str, Any]]] = {}
    try:
        for row in store.read(LEDGER):
            out.setdefault(str(row.get("candidate_key")), []).append(row)
    except FileNotFoundError:
        return {}
    return out


def leads(store, candidate_key: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Distinct result addresses for a candidate, best-ranked first, with the decision on each.

    Only results inside the policy's `max_results` window count as leads; a result below it is recorded in
    the ledger and never offered. Decisions come from the row that recorded them."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in latest_by_candidate(store).get(candidate_key, []):
        if not row.get("ok"):
            continue
        window = int(row.get("max_results") or DEFAULT_MAX_RESULTS)
        for item in row.get("results") or []:
            if item.get("rank", 0) > window or item["url"] in seen:
                continue
            seen.add(item["url"])
            out.append({"url": item["url"], "host": item.get("host"), "title": item.get("title"),
                        "rank": item.get("rank"), "decision": item.get("decision"), "reason": item.get("reason")})
    out.sort(key=lambda lead: (lead["decision"] != ALLOWED, lead["rank"] or 99))
    return out[:limit] if limit else out


def unclassified_hosts(store) -> dict[str, int]:
    """Hosts the policy neither allowed nor denied, with how many distinct leads point at each.

    They are never fetched; listing them is how a person classifies a host once (invariant: never promoted silently)."""
    seen: dict[str, set[str]] = {}
    for candidate_key in latest_by_candidate(store):
        for lead in leads(store, candidate_key):
            if lead["decision"] == UNCLASSIFIED and lead.get("host"):
                seen.setdefault(lead["host"], set()).add(lead["url"])
    return dict(sorted(((h, len(u)) for h, u in seen.items()), key=lambda kv: (-kv[1], kv[0])))


def fetch_locations(store, candidate_key: str, allowed_hosts) -> list[Any]:
    """`resolve.Location`s for ALLOWED leads whose exact host a plan named. Appended last in the cascade."""
    from claimstone.resolve import Location

    if allowed_hosts is None:
        return []
    out = []
    for lead in leads(store, candidate_key):
        if lead["decision"] == ALLOWED and lead["host"] in allowed_hosts:
            out.append(Location(url=lead["url"], provenance="web_locator", host_type="web"))
    return out


# --- identity -----------------------------------------------------------------------------------------

def identity_check(parsed_title: str | None, candidate_title: str | None,
                   *, parsed_authors: list[str] | tuple[str, ...] | None = None,
                   candidate_authors: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    """Is the file we read the work we asked for? Compared on the parsed document's own title,
    and — since v2, when both sides carry authors — on their surnames (#4: D145 called this
    check impossible until candidates carried authors; discovery version 6 makes them carry
    them).

    `passed` only on a title that matches; a title that is clearly different is `WRONG_DOCUMENT`, and a file
    whose title could not be read is `IDENTITY_UNVERIFIED` — not a mismatch, and still not accepted.
    A title that matches while *no* author surname does — both sides naming authors — is also
    `WRONG_DOCUMENT`: same title, different people, different work. Author agreement never
    rescues a title that failed, and a side with no authors leaves the title verdict standing.
    """
    wanted = ids.normalize_title(candidate_title)
    got = ids.normalize_title(parsed_title)
    base = {"identity_check_version": IDENTITY_CHECK_VERSION, "threshold": TITLE_SIMILARITY,
            "candidate_title": candidate_title, "parsed_title": parsed_title}
    title_row = _title_verdict(base, wanted, got, candidate_title, parsed_title)
    if not title_row["passed"]:
        return title_row | {"authors_checked": False, "shared_surnames": None}
    surnames = {ids.surname(str(name)) for name in (candidate_authors or [])} - {""}
    document = {ids.surname(str(name)) for name in (parsed_authors or [])} - {""}
    if not surnames or not document:
        return title_row | {"authors_checked": False, "shared_surnames": None}
    shared = sorted(surnames & document)
    if not shared:
        return title_row | {"authors_checked": True, "shared_surnames": 0, "passed": False,
                            "failure_class": WRONG_DOCUMENT,
                            "reason": "titles match but no author surname does"}
    return title_row | {"authors_checked": True, "shared_surnames": len(shared),
                        "reason": f"{title_row['reason']}; {len(shared)} shared author surname(s)"}


def _title_verdict(base: dict[str, Any], wanted: str, got: str,
                   candidate_title: str | None, parsed_title: str | None) -> dict[str, Any]:
    if not wanted:
        return base | {"passed": False, "failure_class": IDENTITY_UNVERIFIED, "similarity": None,
                       "reason": "the candidate has no title to compare with"}
    if not got:
        return base | {"passed": False, "failure_class": IDENTITY_UNVERIFIED, "similarity": None,
                       "reason": "the parsed document has no readable title"}
    score = difflib.SequenceMatcher(None, wanted, got).ratio()
    # A subtitle often travels on one side only; the part before a colon counts when it is long enough to mean something.
    lead_wanted = ids.normalize_title(str(candidate_title).split(":")[0])
    lead_got = ids.normalize_title(str(parsed_title).split(":")[0])
    if len(lead_wanted) >= 25 and lead_wanted == lead_got:
        score = max(score, TITLE_SIMILARITY)
    if score >= TITLE_SIMILARITY:
        return base | {"passed": True, "failure_class": None, "similarity": round(score, 3),
                       "reason": "titles match"}
    return base | {"passed": False, "failure_class": WRONG_DOCUMENT, "similarity": round(score, 3),
                   "reason": f"title similarity {score:.2f} is below {TITLE_SIMILARITY}"}
