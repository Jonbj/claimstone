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
    """Every artifact this project ever kept, per candidate, deduplicated by path.

    The whole log is read, not just the latest row per candidate. The store is
    content-addressed and append-only, so a pointer to bytes never goes stale: an artifact named
    three rows ago is still on disk under the same hash. Reading only the newest row loses
    artifacts whenever a later row happens not to mention them — which a rejection does, because
    at row level `stored_path` means "the artifact we accepted" and a rejection accepted none.

    Two places a row can name bytes: each attempt's `stored_path`, which the current `acquire`
    writes for every body that arrived, and the row-level field, which is all an older round
    left behind — under `stored_at` in the first schema.
    """
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    facts: dict[str, dict[str, Any]] = {}
    for row in store.read("acquisitions.jsonl"):
        key = row.get("candidate_key")
        if key is None:
            continue
        key = str(key)
        # Later rows describe the candidate better; artifacts accumulate across all of them.
        facts[key] = {
            "candidate_key": key,
            "source_id": row.get("source_id") or facts.get(key, {}).get("source_id"),
            "source_class": row.get("source_class") or facts.get(key, {}).get("source_class"),
        }
        held = grouped.setdefault(key, {})
        for attempt in row.get("attempts") or []:
            path = attempt.get("stored_path")
            if path:
                held.setdefault(str(path), {
                    "url": attempt.get("url"),
                    "content_type": attempt.get("content_type") or "",
                    "stored_path": str(path),
                })
        path = row.get("stored_path") or row.get("stored_at")
        if path:
            held.setdefault(str(path), {
                "url": row.get("url"),
                "content_type": row.get("content_type") or "",
                "stored_path": str(path),
            })

    return [
        facts[key] | artifact
        for key, artifacts in grouped.items()
        for artifact in artifacts.values()
    ]


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
        # The candidate is the authority on its own class, not a ledger row that copied it:
        # an earlier round recorded the manifest's own word for the class rather than the id it
        # resolves to, and preferring the row would preserve that split.
        source_class = classes.get(key) or prior.get("source_class")
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
            # One synthetic attempt recording which artifact was re-judged. Without it a
            # rejection would null out stored_path at row level and the pointer to the bytes
            # would be lost, so the next gate_version could not re-judge what is still on disk.
            "attempts": [{
                "url": artifact["url"],
                "http_status": None,
                "failure_class": None if verdict.accepted else verdict.kind,
                "content_type": artifact["content_type"],
                "provenance": prior.get("provenance"),
                "version": prior.get("version"),
                "gate_kind": verdict.kind,
                "gate_reason": verdict.reason,
                "stored_path": artifact["stored_path"],
            }],
            "failure_class": None if verdict.accepted else verdict.kind,
            "fetched_at": prior.get("fetched_at"),
            "regated_from": prior.get("fetched_at"),
        }
        store.append("acquisitions.jsonl", row)
        yield row
