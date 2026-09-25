"""Stage 3 — normalize: bytes become chunks, and a PDF that is not a document says so.

Three ledgers, owned here and written by nothing else: `documents.jsonl`, `chunks.jsonl` and
`references.jsonl`.

The confirmation rule has the same shape as the content gate's HTML rule, because it is the same
question asked of a different format: does this argue from evidence, or is it a page about a
product? A document with no reference list and little text is the PDF twin of an abstract page,
and stage 2's gate cannot see it — which is exactly what that spec said stage 3 would send back.
"""

from __future__ import annotations

import datetime as _dt
import pathlib
from typing import Any, Iterator

from claimstone import chunk as chunking
from claimstone import html_doc, tei
from claimstone.store import Store

CONFIRM_DEFAULTS: dict[str, int] = {
    # The lowest legitimate reference count in the measured corpus is 8 (MET005); the fact
    # sheet has 0.
    "min_references": 5,
    # A long document without a reference list is still a document — a regulatory filing, say.
    "confirm_chars": 15000,
}

NOT_A_DOCUMENT = "NOT_A_DOCUMENT"
TEI_UNREADABLE = "TEI_UNREADABLE"
# Not a verdict about the source. It writes no `documents.jsonl` row, so admissibility leaves
# the source awaiting: the ceiling rises, the figure does not move, and the round cannot certify
# itself until someone looks. Recording it as unconfirmed instead would count an absent file as
# an established negative and lower the rate on an infrastructure failure.
ARTIFACT_UNREADABLE = "ARTIFACT_UNREADABLE"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def confirm(doc: tei.Document, thresholds: dict[str, int]) -> tuple[bool, str]:
    """Is this a document? Same rule shape as the HTML gate, on a different format."""
    references = len(doc.references)
    body_chars = doc.body_chars
    if references >= thresholds["min_references"]:
        return True, f"{references} references"
    if body_chars >= thresholds["confirm_chars"]:
        return True, f"{body_chars} body_chars without a reference list"
    return False, (
        f"{references} references and body_chars {body_chars}: below both "
        f"min_references {thresholds['min_references']} and "
        f"confirm_chars {thresholds['confirm_chars']}"
    )


def _acquired(store: Store) -> list[dict[str, Any]]:
    from claimstone import admissibility

    return [row for row in admissibility.collapse(store).values() if row.get("acquired")]


def _reference_rows(store: Store) -> dict[str, dict[str, Any]]:
    return store.latest_by("references.jsonl", "key")


def run(
    store: Store,
    grobid: Any,
    *,
    thresholds: dict[str, int] | None = None,
    force: bool = False,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Normalize every acquired source not already done. Idempotent by content hash."""
    th = {**chunking.DEFAULT_THRESHOLDS, **CONFIRM_DEFAULTS, **(thresholds or {})}
    done = {
        str(row.get("sha256"))
        for row in store.latest_by("documents.jsonl", "source_id").values()
    }
    references = _reference_rows(store)
    attempted = 0

    for source in _acquired(store):
        if limit is not None and attempted >= limit:
            return
        digest = str(source.get("sha256") or "")
        source_id = str(source.get("source_id") or source.get("candidate_key"))
        if digest in done and not force:
            continue

        common = {
            "source_id": source_id,
            "sha256": digest,
            "source_class": source.get("source_class"),
            "normalized_at": _now(),
        }
        stored = source.get("stored_path") or source.get("stored_at")

        # Decided on the recorded content type, not on the stored suffix: the suffix is chosen
        # by acquire from that same type, so reading it back would just be the answer twice.
        is_pdf = "pdf" in str(source.get("content_type") or "").lower()
        tei_path = store.root / "tei" / f"{digest}.xml"

        try:
            if is_pdf:
                if tei_path.exists():
                    payload = tei_path.read_bytes()
                else:
                    payload = grobid.full_text(pathlib.Path(stored).read_bytes(),
                                               filename=f"{source_id}.pdf")
                    tei_path.parent.mkdir(parents=True, exist_ok=True)
                    tei_path.write_bytes(payload)
                parse, parsed_from = tei.parse, str(tei_path)
            else:
                # GROBID reads PDFs; handing it markup is a request that cannot succeed. And a
                # source without a PDF is still a document — the confirmation rule's second clause,
                # long enough to stand without a bibliography, admits a regulatory filing.
                payload = pathlib.Path(stored).read_bytes()
                parse, parsed_from = html_doc.parse, str(stored)
        except (OSError, TypeError) as exc:
            # The bytes are gone, unreadable, or were never recorded. One such source used to end
            # the sweep before any other was touched.
            attempted += 1
            yield common | {
                "fulltext_confirmed": None,
                "failure_class": ARTIFACT_UNREADABLE,
                "reason": f"{type(exc).__name__}: {str(exc)[:160]}",
                "stored_path": str(stored) if stored else None,
                "chunks": 0,
            }
            continue

        try:
            doc = parse(payload)
        except tei.TeiError as exc:
            row = common | {"fulltext_confirmed": False, "failure_class": TEI_UNREADABLE,
                            "reason": str(exc)[:200], "chunks": 0, "tei_path": parsed_from}
            store.append("documents.jsonl", row)
            attempted += 1
            yield row
            continue

        confirmed, reason = confirm(doc, th)
        result = chunking.chunk_document(doc, source_id=source_id, thresholds=th) if confirmed \
            else chunking.ChunkResult(chunks=[])

        for one in result.chunks:
            store.append("chunks.jsonl", one.as_row())

        if confirmed:
            for reference in doc.references:
                if not reference.key:
                    continue
                held = references.get(reference.key)
                cited_by = sorted(set((held or {}).get("cited_by", [])) | {source_id})
                references[reference.key] = {
                    "key": reference.key,
                    "title": reference.title,
                    "year": reference.year,
                    "authors": list(reference.authors),
                    "doi": reference.doi or (held or {}).get("doi"),
                    "cited_by": cited_by,
                    "citations_in_corpus": len(cited_by),
                    "seen_at": _now(),
                }
                store.append("references.jsonl", references[reference.key])

        row = common | {
            "tei_path": parsed_from,
            "format": "pdf" if is_pdf else "html",
            "fulltext_confirmed": confirmed,
            "failure_class": None if confirmed else NOT_A_DOCUMENT,
            "reason": reason,
            "title": doc.title,
            "body_chars": doc.body_chars,
            "references": len(doc.references),
            "tables": len(doc.tables),
            "notes": len(doc.notes),
            "chunks": len(result.chunks),
            "dropped_sections": result.dropped_sections,
            "merged_sections": result.merged_sections,
            "oversized_chunks": result.oversized_chunks,
            "chunk_version": chunking.CHUNK_VERSION,
            "thresholds": {k: th[k] for k in sorted(th)},
        }
        store.append("documents.jsonl", row)
        done.add(digest)
        attempted += 1
        yield row


def confirm_sweep(store: Store, name: str, values: list[int]) -> list[dict[str, Any]]:
    """How many documents confirm as one threshold moves. Re-reads what is on disk; no network.

    `min_references: 5` and `confirm_chars: 15000` were chosen by looking at fourteen documents. Two
    constants chosen at a desk are two constants to interrogate, and the bytes are on disk under
    their hash, so interrogating them is free — the same arrangement as gate-audit.
    """
    if name not in CONFIRM_DEFAULTS:
        raise ValueError(f"unknown threshold {name!r}: {sorted(CONFIRM_DEFAULTS)}")

    parsed: list[tei.Document] = []
    missing = 0
    for row in store.latest_by("documents.jsonl", "source_id").values():
        path = pathlib.Path(str(row.get("tei_path") or ""))
        if not path.exists():
            missing += 1
            continue
        # The parser follows the recorded format, never the stored suffix. Handing markup to the
        # TEI parser would count the one source confirmed by characters as unreadable, and a sweep
        # of `confirm_chars` that excludes it would report that the threshold decides nothing.
        parse = html_doc.parse if row.get("format") == "html" else tei.parse
        try:
            parsed.append(parse(path.read_bytes()))
        except tei.TeiError:
            missing += 1

    points = []
    for value in values:
        th = {**CONFIRM_DEFAULTS, name: value}
        confirmed = sum(1 for doc in parsed if confirm(doc, th)[0])
        points.append({
            "value": value,
            "confirmed": confirmed,
            "documents": len(parsed),
            # Counted, not hidden: a document that cannot be re-read is a gap in the audit, and an
            # audit that silently skips what it cannot read reports a cleaner corpus than exists.
            "unreadable": missing,
        })
    return points
