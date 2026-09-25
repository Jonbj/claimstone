"""Stage 2 — acquire: candidates become frozen texts, legally, with every attempt recorded.

This is the binding constraint on the science, not extraction quality: the corpus that
motivated this project sits at 0.42 because publishers return 403. Every attempt is recorded,
successful or not, because a swallowed failure inflates the rate that decides whether a round
may produce verdicts at all.

Where a copy might live is `resolve`'s problem; whether what came back is a document is
`fulltext`'s. This module does neither — it walks the cascade, applies the gate, stores the
bytes and writes the row.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterable, Iterator

from claimstone import fulltext, net, resolve
from claimstone.store import Store

PDF_TYPES = ("application/pdf", "application/octet-stream")
HTML_TYPES = ("text/html", "application/xhtml+xml", "application/xml", "text/xml", "text/plain")

ROUTINE = "routine"
DEFAULT_RETRY_AFTER_S = 6 * 3600


class MissingSourceClass(ValueError):
    """Invariant 6: a blog post and a refereed paper never share a pool unrecorded."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _suffix_for(content_type: str, url: str) -> str:
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        return ".pdf"
    if "xml" in content_type:
        return ".xml"
    return ".html"


def acquire_one(
    fetcher: net.FetcherLike,
    store: Store,
    candidate: dict[str, Any],
    *,
    campaign: str = ROUTINE,
    use_apis: bool = True,
    thresholds: dict[str, int] | None = None,
    policy: dict[str, Any] | None = None,
    classes: Any = None,
) -> dict[str, Any]:
    """Try the cascade for one candidate. Returns the ledger row; never raises on a fetch."""
    if not candidate.get("source_class"):
        raise MissingSourceClass(
            f"candidate {candidate.get('candidate_key')!r} carries no source_class; "
            "a pool that mixes classes unrecorded cannot be synthesised (invariant 6)"
        )

    th = {**fulltext.DEFAULT_THRESHOLDS, **(thresholds or {})}
    # The gate's policy comes from the candidate's own class where that class declares one: a
    # filing that cites nothing and a paper that must are not judged by one rule.
    if classes is not None:
        from claimstone.config import resolve_gate_policy

        policy = resolve_gate_policy(policy or {}, classes, candidate.get("source_class"))
    locations, oa_status = resolve.plan(fetcher, candidate, use_apis=use_apis)
    attempts: list[dict[str, Any]] = []
    common = {
        "candidate_key": candidate["candidate_key"],
        "source_id": candidate.get("source_id"),
        "source_class": candidate["source_class"],
        "campaign": campaign,
        "fetched_at": _now(),
    }

    for location in locations:
        expect = PDF_TYPES if location.url.lower().endswith(".pdf") else PDF_TYPES + HTML_TYPES
        outcome = fetcher.get(location.url, expect=expect)
        attempt = outcome.as_row() | {
            "provenance": location.provenance,
            "version": location.version,
            "gate_kind": None,
            "gate_reason": None,
            "stored_path": None,
        }

        if not outcome.ok or not outcome.body:
            attempts.append(attempt)
            continue

        verdict = fulltext.classify(outcome.body, outcome.content_type, location.url, th,
                                    policy=policy)
        digest, path = store.store_bytes(
            outcome.body, _suffix_for(outcome.content_type, location.url)
        )
        attempt |= {
            "gate_kind": verdict.kind,
            "gate_reason": verdict.reason,
            "stored_path": str(path),
        }
        attempts.append(attempt)

        if not verdict.accepted:
            # A 200 carrying a landing page or an abstract page is a failure of acquisition.
            # Keep going: a later location in the cascade may hold the real thing.
            #
            # The bytes are kept regardless. Without them the threshold audit cannot re-run
            # the gate and the by-hand rejection check has nothing to look at — and the
            # thresholds that produced the headline rate were chosen at a desk.
            attempt["failure_class"] = verdict.kind
            continue

        return common | {
            "acquired": True,
            "sha256": digest,
            "stored_path": str(path),
            "url": location.url,
            "provenance": location.provenance,
            "version": location.version,
            "licence": location.licence,
            "oa_status": location.oa_status or oa_status,
            "host_type": location.host_type,
            "content_type": outcome.content_type,
            "bytes": len(outcome.body),
            "gate": verdict.as_row(th, policy),
            "attempts": attempts,
            "failure_class": None,
        }

    return common | {
        "acquired": False,
        "sha256": None,
        "stored_path": None,
        "url": str(candidate.get("url") or ""),
        "oa_status": oa_status,
        "gate": None,
        "attempts": attempts,
        # The class of the last attempt is the honest headline: it says what stopped us.
        "failure_class": attempts[-1]["failure_class"] if attempts else net.NO_LOCATIONS,
    }


def _age_seconds(row: dict[str, Any]) -> float:
    stamp = row.get("fetched_at")
    if not stamp:
        return float("inf")
    try:
        when = _dt.datetime.fromisoformat(str(stamp))
    except ValueError:
        return float("inf")
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.timezone.utc)
    return (_dt.datetime.now(_dt.timezone.utc) - when).total_seconds()


def should_attempt(
    previous: dict[str, Any] | None,
    *,
    retry_classes: frozenset[str],
    retry_after_s: int = DEFAULT_RETRY_AFTER_S,
) -> bool:
    """Decide whether to knock again.

    Terminal failures are left alone unless their class was explicitly named, which is the
    named-campaign rule: a host that returned 403 is not re-requested on a routine run.
    Transient failures come back on their own once the TTL has passed, so a downloader blocked
    for an afternoon does not quietly leave those sources out of the denominator.
    """
    if previous is None:
        return True
    if previous.get("acquired"):
        return False
    failure_class = previous.get("failure_class")
    if failure_class in retry_classes:
        return True
    if net.is_terminal(failure_class):
        return False
    return _age_seconds(previous) >= retry_after_s


def run(
    candidates: Iterable[dict[str, Any]],
    store: Store,
    fetcher: net.FetcherLike,
    *,
    campaign: str = ROUTINE,
    retry_classes: frozenset[str] = frozenset(),
    retry_after_s: int = DEFAULT_RETRY_AFTER_S,
    use_apis: bool = True,
    thresholds: dict[str, int] | None = None,
    policy: dict[str, Any] | None = None,
    classes: Any = None,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Acquire what the retry policy allows. A candidate it declines writes no row."""
    previous = store.latest_by("acquisitions.jsonl", "candidate_key")
    attempted = 0
    for candidate in candidates:
        if limit is not None and attempted >= limit:
            return
        prior = previous.get(str(candidate["candidate_key"]))
        if not should_attempt(prior, retry_classes=retry_classes, retry_after_s=retry_after_s):
            continue
        row = acquire_one(
            fetcher, store, candidate, campaign=campaign, use_apis=use_apis,
            thresholds=thresholds, policy=policy, classes=classes,
        )
        row["attempt_no"] = int((prior or {}).get("attempt_no") or 0) + 1
        store.append("acquisitions.jsonl", row)
        attempted += 1
        yield row
