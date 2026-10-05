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
import hashlib
import pathlib
from typing import Any, Iterator

from claimstone import chunk as chunking
from claimstone import html_doc, jats, tei, model_call
from claimstone.store import sha256_text
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
JATS_UNREADABLE = "JATS_UNREADABLE"
JATS_UNSUPPORTED = "JATS_UNSUPPORTED"


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
    done = store.latest_by("documents.jsonl", "source_id")
    references = _reference_rows(store)
    attempted = 0

    for source in _acquired(store):
        if limit is not None and attempted >= limit:
            return
        digest = str(source.get("sha256") or "")
        source_id = str(source.get("source_id") or source.get("candidate_key"))
        if done.get(source_id, {}).get("sha256") == digest and not force:
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
        media_type = str(source.get("content_type") or "").lower().split(";", 1)[0].strip()
        is_jats = not is_pdf and media_type in {"application/xml", "text/xml", "application/jats+xml"}
        parser_fields = {"jats_parser_version": jats.JATS_PARSER_VERSION} if is_jats else {}
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
                parse, parsed_from = jats.parse if is_jats else html_doc.parse, str(stored)
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
        except jats.UnsupportedJats as exc:
            # Unsupported structure is our limitation, not an established negative about the source.
            attempted += 1
            yield common | parser_fields | {
                "fulltext_confirmed": None, "failure_class": JATS_UNSUPPORTED,
                "reason": str(exc)[:200], "chunks": 0, "stored_path": parsed_from,
            }
            continue
        except tei.TeiError as exc:
            row = common | parser_fields | {"fulltext_confirmed": False,
                            "failure_class": JATS_UNREADABLE if is_jats else TEI_UNREADABLE,
                            "reason": str(exc)[:200], "chunks": 0, "chunk_ids": [], "tei_path": parsed_from}
            store.append("documents.jsonl", row)
            attempted += 1
            yield row
            continue

        confirmed, reason = confirm(doc, th)
        result = chunking.chunk_document(doc, source_id=source_id, thresholds=th) if confirmed \
            else chunking.ChunkResult(chunks=[])

        generation = sha256_text(model_call.canonical({
            'payload_sha256': hashlib.sha256(payload).hexdigest(),
            'source_sha256': digest, 'chunk_version': chunking.CHUNK_VERSION, 'thresholds': th,
            'html_parser_version': None if is_pdf or is_jats else html_doc.HTML_PARSER_VERSION,
        } | parser_fields))
        chunk_ids = []
        existing = store.latest_by('chunks.jsonl', 'chunk_id')
        for one in result.chunks:
            identifier = f"{source_id}#{generation}#{one.chunk_id.split('#')[-1]}"
            chunk_ids.append(identifier)
            if identifier not in existing:
                store.append('chunks.jsonl', one.as_row() | {
                    'chunk_id': identifier, 'generation_sha256': generation,
                    'document_sha256': digest})

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

        row = common | parser_fields | {
            "tei_path": parsed_from,
            "format": "pdf" if is_pdf else ("jats" if is_jats else "html"),
            # Which parser read it. The PDF side is the GROBID image, pinned by digest in compose.yaml and
            # checked against `grobid.IMAGE`; the HTML side is code in this repository and carries a
            # version of its own, because what it extracts decides `references` and so `fulltext_confirmed`.
            "html_parser_version": None if is_pdf or is_jats else html_doc.HTML_PARSER_VERSION,
            "fulltext_confirmed": confirmed,
            "failure_class": None if confirmed else NOT_A_DOCUMENT,
            "reason": reason,
            "title": doc.title,
            "body_chars": doc.body_chars,
            "references": len(doc.references),
            "tables": len(doc.tables),
            "notes": len(doc.notes),
            "chunks": len(result.chunks),
            "chunk_ids": chunk_ids, "generation_sha256": generation,
            "dropped_sections": result.dropped_sections,
            "merged_sections": result.merged_sections,
            "oversized_chunks": result.oversized_chunks,
            "chunk_version": chunking.CHUNK_VERSION,
            "thresholds": {k: th[k] for k in sorted(th)},
        }
        store.append("documents.jsonl", row)
        done[source_id] = row
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
        parse = {"html": html_doc.parse, "jats": jats.parse}.get(row.get("format"), tei.parse)
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
