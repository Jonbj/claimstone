"""Re-run the content gate over bytes already on disk, at thresholds other than the ones used.

The thresholds in fulltext.py were chosen at a desk. Nothing measured them, and a wrong one
moves the headline rate silently. Two properties make that recoverable for free: the bytes are
content-addressed under their hash, and the gate does no I/O. So the question "is this constant
load-bearing?" is answerable by arithmetic instead of by argument.

A flat sweep means the threshold is not deciding anything. A sweep that swings means it is
deciding the result, and the boundary cases have to be read by a human.
"""

from __future__ import annotations

import pathlib
from typing import Any, Iterator

from claimstone import fulltext
from claimstone.store import Store

MISSING = "BYTES_MISSING"


def _artifacts(store: Store) -> list[dict[str, Any]]:
    """Every kept artifact, accepted or not, latest row per candidate.

    Both places a row records bytes are read. The attempts carry `stored_path` for every body
    that arrived, which is what a round written by the current `acquire` produces; a row also
    records the artifact it accepted at the top level, which is all an older round left behind.
    Reading only the attempts would make the audit silently empty on an existing corpus.
    """
    out: list[dict[str, Any]] = []
    for key, row in store.latest_by("acquisitions.jsonl", "candidate_key").items():
        seen: set[str] = set()
        common = {
            "candidate_key": key,
            "source_id": row.get("source_id"),
            "source_class": row.get("source_class"),
        }
        for attempt in row.get("attempts") or []:
            path = attempt.get("stored_path")
            if path and path not in seen:
                seen.add(str(path))
                out.append(common | {
                    "url": attempt.get("url"),
                    "content_type": attempt.get("content_type") or "",
                    "stored_path": path,
                })
        # `stored_at` is the older schema's name for the same field.
        path = row.get("stored_path") or row.get("stored_at")
        if path and str(path) not in seen:
            out.append(common | {
                "url": row.get("url"),
                "content_type": row.get("content_type") or "",
                "stored_path": str(path),
            })
    return out


def _classify_stored(artifact: dict[str, Any], thresholds: dict[str, int]) -> fulltext.FullText:
    path = pathlib.Path(artifact["stored_path"])
    if not path.exists():
        return fulltext.FullText(MISSING, None, f"no bytes at {path}")
    return fulltext.classify(
        path.read_bytes(), artifact["content_type"], artifact["url"] or "", thresholds
    )


def sweep(store: Store, name: str, values: list[int]) -> list[dict[str, Any]]:
    """How the acquisition rate moves as one threshold moves. No network, no re-fetch."""
    if name not in fulltext.DEFAULT_THRESHOLDS:
        raise ValueError(f"unknown threshold {name!r}: {sorted(fulltext.DEFAULT_THRESHOLDS)}")
    by_candidate: dict[str, list[dict[str, Any]]] = {}
    for artifact in _artifacts(store):
        by_candidate.setdefault(artifact["candidate_key"], []).append(artifact)

    # The denominator is every candidate in the ledger, not only those whose bytes we hold. A
    # source that returned 403 cannot pass the gate at any threshold, so leaving it out would
    # make this "rate" a different number from the one `report` prints under the same name.
    total = len(store.latest_by("acquisitions.jsonl", "candidate_key"))

    points: list[dict[str, Any]] = []
    for value in values:
        thresholds = {**fulltext.DEFAULT_THRESHOLDS, name: value}
        # A candidate counts as acquired if *any* of its kept artifacts passes: that is what
        # the cascade would have done at this threshold.
        accepted = sum(
            1
            for group in by_candidate.values()
            if any(_classify_stored(a, thresholds).accepted for a in group)
        )
        points.append({
            "value": value,
            "accepted": accepted,
            "attempted": total,
            "rate": (accepted / total) if total else None,
        })
    return points


def rejections(store: Store, thresholds: dict[str, int] | None = None) -> list[dict[str, Any]]:
    """Every artifact the gate turns down, with what it counted and what triggered it.

    Printed for a by-hand check. On a 25-source manifest this is ten minutes of reading and it
    is the only way to learn whether a paywall phrase is catching a legitimate open article.
    """
    th = {**fulltext.DEFAULT_THRESHOLDS, **(thresholds or {})}
    out: list[dict[str, Any]] = []
    for artifact in _artifacts(store):
        verdict = _classify_stored(artifact, th)
        if verdict.accepted:
            continue
        out.append({
            "source_id": artifact["source_id"],
            "source_class": artifact["source_class"],
            "url": artifact["url"],
            "stored_path": artifact["stored_path"],
            "kind": verdict.kind,
            "chars": verdict.chars,
            "reason": verdict.reason,
        })
    return out


def regate(
    store: Store,
    *,
    campaign: str,
    thresholds: dict[str, int] | None = None,
) -> Iterator[dict[str, Any]]:
    """Re-judge bytes already held, under the gate as it stands now.

    A round recorded before the gate existed, or under an earlier `gate_version`, carries
    `acquired` flags that the current rule would not agree with. Re-fetching to find that out
    would be wrong twice over: the bytes are already on disk, and knocking on eighteen hosts to
    learn what a pure function can tell us offline is not conduct this project permits.

    So this takes no fetcher — it cannot reach the network by construction — and appends a
    corrected row per candidate whose bytes are held. The ledger stays append-only: the old row
    is not edited, and `regated_from` carries the timestamp of the row being re-judged, so the
    history shows a re-reading rather than a second fetch.
    """
    from claimstone.acquire import MissingSourceClass

    th = {**fulltext.DEFAULT_THRESHOLDS, **(thresholds or {})}
    classes = {
        key: row.get("source_class")
        for key, row in store.latest_by("candidates.jsonl", "candidate_key").items()
    }
    previous = store.latest_by("acquisitions.jsonl", "candidate_key")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for artifact in _artifacts(store):
        grouped.setdefault(artifact["candidate_key"], []).append(artifact)

    for key, artifacts in grouped.items():
        prior = previous.get(key, {})
        source_class = prior.get("source_class") or classes.get(key)
        if not source_class:
            raise MissingSourceClass(
                f"candidate {key!r} carries no source_class, in its ledger row or its candidate; "
                "a pool that mixes classes unrecorded cannot be synthesised (invariant 6)"
            )

        best: tuple[fulltext.FullText, dict[str, Any]] | None = None
        for artifact in artifacts:
            verdict = _classify_stored(artifact, th)
            # Prefer whatever passes; otherwise keep the first verdict as the honest headline.
            if best is None or (verdict.accepted and not best[0].accepted):
                best = (verdict, artifact)
        assert best is not None
        verdict, artifact = best

        row = {
            "candidate_key": key,
            "source_id": prior.get("source_id"),
            "source_class": source_class,
            "campaign": campaign,
            "attempt_no": int(prior.get("attempt_no") or 1),
            "acquired": verdict.accepted,
            "sha256": pathlib.Path(artifact["stored_path"]).stem if verdict.accepted else None,
            "stored_path": artifact["stored_path"] if verdict.accepted else None,
            "url": artifact["url"],
            "provenance": prior.get("provenance"),
            "version": prior.get("version"),
            "licence": prior.get("licence"),
            "oa_status": prior.get("oa_status"),
            "content_type": artifact["content_type"],
            "gate": verdict.as_row(th),
            "attempts": [],
            "failure_class": None if verdict.accepted else verdict.kind,
            "fetched_at": prior.get("fetched_at"),
            "regated_from": prior.get("fetched_at"),
        }
        store.append("acquisitions.jsonl", row)
        yield row
