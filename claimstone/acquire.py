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
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable, Iterator

from claimstone import fulltext, net, resolve
from claimstone.store import Store
from claimstone.request_log import RecordingFetcher

PDF_TYPES = ("application/pdf", "application/octet-stream")
HTML_TYPES = ("text/html", "application/xhtml+xml", "application/xml", "text/xml",
              "application/jats+xml", "text/plain")
JATS_TYPES = ("application/xml", "text/xml", "application/jats+xml")

ROUTINE = "routine"
DEFAULT_RETRY_AFTER_S = 6 * 3600
REUSE_VERSION = 1


class MissingSourceClass(ValueError):
    """Invariant 6: a blog post and a refereed paper never share a pool unrecorded."""


def reuse_cached(store, candidate, origin, *, origin_store, expected_sha256,
                 campaign, identity, thresholds=None, policy=None, classes=None):
    """Reuse verified acquired bytes, re-gated locally; never simulate an HTTP request."""
    if not candidate.get("source_class"):
        raise MissingSourceClass("cached candidate requires source_class")
    if not campaign or campaign == ROUTINE:
        raise ValueError("local reuse requires a named campaign")
    if not origin.get("acquired") or origin.get("url") != candidate.get("url"):
        raise ValueError("reuse requires a successful acquisition at the declared exact URL")
    if not identity.get("document_title") or not identity.get("checked_by"):
        raise ValueError("reuse requires an explicit title/identity assessment")
    payload = Path(origin["stored_path"]).read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_sha256 or digest != origin.get("sha256"):
        raise ValueError("cached byte hash does not match the reuse plan")
    existing = store.latest_by("acquisitions.jsonl", "candidate_key").get(candidate["candidate_key"])
    if existing and existing.get("acquired"):
        return existing
    th = {**fulltext.DEFAULT_THRESHOLDS, **(thresholds or {})}
    if classes is not None:
        from claimstone.config import resolve_gate_policy
        policy = resolve_gate_policy(policy or {}, classes, candidate["source_class"])
    judged = fulltext.classify(payload, origin.get("content_type", ""), candidate["url"], th,
                               policy=policy)
    _, path = store.store_bytes(payload, _suffix_for(origin.get("content_type", ""), candidate["url"]))
    row = {
        "candidate_key": candidate["candidate_key"], "source_id": candidate.get("source_id"),
        "source_class": candidate["source_class"], "campaign": campaign,
        "attempt_no": None,  # assigned under the writer lock at append time (F5)
        "acquired": judged.accepted, "sha256": digest if judged.accepted else None,
        "stored_path": str(path), "url": candidate["url"], "provenance": "store-reuse",
        "version": origin.get("version", ""), "licence": origin.get("licence"),
        "oa_status": origin.get("oa_status"), "host_type": origin.get("host_type"),
        "content_type": origin.get("content_type", ""), "bytes": len(payload),
        "gate": judged.as_row(th, policy), "failure_class": None if judged.accepted else judged.kind,
        "attempts": [], "fetched_at": origin.get("fetched_at"), "reused_at": _now(),
        "reuse_version": REUSE_VERSION, "reuse_origin": {
            "store": str(origin_store), "candidate_key": origin["candidate_key"],
            "stored_path": origin["stored_path"], "sha256": digest,
            "identity": dict(identity),
        },
    }
    # F5: the attempt number is read under the project writer lock, immediately before the
    # append — the bytes and the gate ran without the lock (no work happens under it), and a
    # concurrent writer between the earlier read and this append cannot produce a duplicate
    # attempt_no because this re-read is the one that counts.
    with store.writer_lock():
        latest = store.latest_by("acquisitions.jsonl", "candidate_key").get(
            str(candidate["candidate_key"]))
        row["attempt_no"] = int((latest or {}).get("attempt_no") or 0) + 1
        store.append("acquisitions.jsonl", row)
    return row


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _suffix_for(content_type: str, url: str) -> str:
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        return ".pdf"
    if "xml" in content_type:
        return ".xml"
    return ".html"


def _jats_licence(body: bytes) -> str | None:
    """Retain the article's declared licence, without inferring one from endpoint access."""
    root = ET.fromstring(body)
    front = next((element for element in root if element.tag.rsplit('}', 1)[-1] == 'front'), None)
    if front is None:
        return None
    for element in front.iter():
        if element.tag.rsplit('}', 1)[-1] == 'license':
            for linked in element.iter():
                for key, value in linked.attrib.items():
                    if key.rsplit('}', 1)[-1] == 'href' and value:
                        return value
            declared = element.get('license-type') or ''
            return declared if declared.lower().startswith('cc-') else None
    return None


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
    fetcher = RecordingFetcher(fetcher, store, purpose='acquisition', campaign=campaign,
                               candidate_key=candidate['candidate_key'], source_class=candidate['source_class'])
    locations, oa_status = resolve.plan(fetcher, candidate, use_apis=use_apis)
    attempts: list[dict[str, Any]] = []
    common = {
        "candidate_key": candidate["candidate_key"],
        "source_id": candidate.get("source_id"),
        "source_class": candidate["source_class"],
        "campaign": campaign,
        "fetched_at": _now(),
    }

    # A worklist rather than a loop over a fixed list: a record page names the deposited file, and the
    # cascade has to be able to add what it just learned. `followed` keeps that one level deep — a link
    # read off a page never yields more links, so this cannot become a crawl.
    pending = list(locations)
    followed = False
    while pending:
        location = pending.pop(0)
        expect = (JATS_TYPES if location.url.endswith('/fullTextXML') else
                  PDF_TYPES if location.url.lower().endswith('.pdf') else PDF_TYPES + HTML_TYPES)
        outcome = fetcher.get(location.url, expect=expect)
        attempt = outcome.as_row() | {
            "provenance": location.provenance,
            "version": location.version,
            "licence": location.licence,
            "oa_status": location.oa_status or oa_status,
            "host_type": location.host_type,
            "gate_kind": None,
            "gate_reason": None,
            "stored_path": None,
        }

        if not outcome.ok or not outcome.body:
            attempts.append(attempt)
            continue

        verdict = fulltext.classify(outcome.body, outcome.content_type, outcome.url, th,
                                    policy=policy)
        licence = (_jats_licence(outcome.body) or location.licence
                   if verdict.kind == fulltext.JATS_FULLTEXT else location.licence)
        attempt['licence'] = licence
        digest, path = store.store_bytes(
            outcome.body, _suffix_for(outcome.content_type, outcome.url)
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
            # And the page it refused may name the file. Measured on the pilot: 7 of 25 open-access
            # misses had the deposited PDF's link in bytes already on disk, because Unpaywall names a
            # Pure or DSpace record page as the free location and the cascade stopped at it.
            if (
                not followed
                and verdict.kind in (fulltext.LANDING_PAGE_ONLY, fulltext.ABSTRACT_ONLY)
                and "html" in (outcome.content_type or "").lower()
            ):
                found = resolve.deposited_files(
                    outcome.body.decode("utf-8", "replace"), outcome.url)
                if found:
                    followed = True
                    # Ahead of the rest: a file this page points at is a better warrant than the next
                    # guess, and the remaining locations are still tried if it does not pan out.
                    pending = found + pending
            continue

        return common | {
            "acquired": True,
            "sha256": digest,
            "stored_path": str(path),
            "url": location.url,
            "provenance": location.provenance,
            "version": location.version,
            "licence": licence,
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


def eligible_candidates(
    candidates: Iterable[dict[str, Any]], previous: dict[str, dict[str, Any]], *,
    retry_classes: frozenset[str] = frozenset(),
    retry_after_s: int = DEFAULT_RETRY_AFTER_S, limit: int | None = None,
    round_name: str | None = None, manifest_only: bool = False, only_oa: bool = False,
) -> Iterator[dict[str, Any]]:
    """The same scope, retry policy and attempt cap for preview and execution."""
    selected = 0
    for candidate in candidates:
        if limit is not None and selected >= limit:
            return
        if round_name is not None and candidate.get('round') != round_name:
            continue
        if manifest_only and not candidate.get('source_id'):
            continue
        if only_oa and candidate.get('is_oa') is not True:
            continue
        if not should_attempt(previous.get(str(candidate['candidate_key'])),
                              retry_classes=retry_classes, retry_after_s=retry_after_s):
            continue
        selected += 1
        yield candidate


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
    round_name: str | None = None,
    manifest_only: bool = False,
    only_oa: bool = False,
) -> Iterator[dict[str, Any]]:
    """Acquire what the retry policy allows. A candidate it declines writes no row.

    `round_name` and `manifest_only` select the population, the same two selectors `report` has. Without
    them a curated corpus could not be acquired as a corpus: measured on the pilot, which discovered 199
    candidates and then curated 28, `--limit 28` attempted the first twenty-eight unattempted candidates of
    the 199 and exactly one was on the list. The figure that came out looked plausible and was about a
    different population.

    `only_oa` is the third selector: candidates whose **discovery metadata** already records a free copy.
    It exists for two jobs. It scopes a round to literature that is legally readable, which is the honest
    alternative to lowering a floor a closed corpus cannot reach. And it isolates the population that
    measures the cascade rather than the literature — on sources where a free copy exists by definition, a
    miss is ours. Measured on the pilot: 10 of 69 such candidates attempted, 5 obtained, and four of the
    five losses were a landing page fetched instead of the PDF or a 403 from a host that publishes open.

    It reads the discovery row and makes no request of its own, so a candidate whose channel recorded
    nothing is **not** assumed closed — it is simply outside this population, and `report` still counts it
    in the denominator it belongs to.
    """
    previous = store.latest_by("acquisitions.jsonl", "candidate_key")
    for candidate in eligible_candidates(candidates, previous, retry_classes=retry_classes,
            retry_after_s=retry_after_s, limit=limit, round_name=round_name,
            manifest_only=manifest_only, only_oa=only_oa):
        try:
            row = acquire_one(
                fetcher, store, candidate, campaign=campaign, use_apis=use_apis,
                thresholds=thresholds, policy=policy, classes=classes,
            )
        except MissingSourceClass as exc:
            # The refusal is right and ending the sweep is not — the same defect shape as an unreadable
            # artifact ending a normalize sweep. Measured on the real store: 34 fetchable citation
            # candidates, and the run died on the first of the 16 carrying no class having acquired none.
            #
            # `acquire_one` still raises, because a caller handing it an unclassified candidate has made
            # a mistake. Here it is recorded so the refusal is countable, and the next candidate is
            # tried. UNCLASSIFIED is terminal: a host budget has nothing to do with it, and it stays
            # refused until the candidate gains a class — which `discover --reclassify` is for.
            row = {
                "candidate_key": candidate["candidate_key"],
                "source_id": candidate.get("source_id"),
                "source_class": None,
                "url": candidate.get("url") or "",
                "acquired": False,
                "failure_class": "UNCLASSIFIED",
                "notes": str(exc),
                "attempts": [],
                "fetched_at": _now(),
                "campaign": campaign,
                "oa_status": None,
            }
        # F5: same rule as reuse_cached — the fetch ran without the lock; the attempt number
        # is assigned from a re-read taken under the lock, immediately before the append.
        with store.writer_lock():
            latest = store.latest_by("acquisitions.jsonl", "candidate_key").get(
                str(candidate["candidate_key"]))
            row["attempt_no"] = int((latest or {}).get("attempt_no") or 0) + 1
            store.append("acquisitions.jsonl", row)
        yield row
