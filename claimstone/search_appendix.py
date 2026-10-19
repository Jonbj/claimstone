"""A reader-facing appendix of what was searched, and what was not (issue #11, D150).

The appendix is derived from the same frozen ledger prefix as every other export output, so
`claimstone export-verify` recomputes it byte for byte. It answers a reader's question — which
exact query, against which provider, on what date, with what cap, what came back and what
failed — without opening the ledgers, and it refuses to turn those counts into a claim about
the literature: a returned page is not a completeness estimate (D10), and the stage counts are
not a synthesis or a vote (invariant 7).
"""

from __future__ import annotations

from typing import Any, Mapping

from claimstone import (admissibility, chunk_sets, claim_records, review, scope)
from claimstone.config import Project
from claimstone.store import Store

OUTPUT = "search_appendix.md"


def _cell(value: Any) -> str:
    """One markdown table cell: no newline, no unescaped pipe."""
    text = str(value if value is not None else "—")
    return " ".join(text.replace("|", "\\|").split())


def _query_rows(store: Store, selector: scope.Selector) -> list[dict[str, Any]]:
    """The queries this selector claims, latest outcome per query id.

    A manifest-only flow has no discovery population of its own (`requests.md`), so it claims no
    query even if the store happens to hold one from another round.
    """
    if selector.manifest_only:
        return []
    rows = store.latest_by("queries.jsonl", "query_id").values()
    return sorted(
        (row for row in rows
         if selector.round is None or row.get("round") == selector.round),
        key=lambda row: (str(row.get("source_api") or ""),
                         str(row.get("completed_at") or ""),
                         str(row.get("topic_id") or ""),
                         str(row.get("query") or "")))


def _query_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (str(row.get("round") or ""), str(row.get("source_api") or ""),
            str(row.get("topic_id") or ""), str(row.get("query") or ""))


def _request_index(store: Store) -> dict[tuple[str, str, str, str], list[dict[str, Any]]]:
    """Discovery response rows by query context, in request order.

    Only `purpose: discovery` rows are search payloads; an acquisition response carrying the
    same query text is a different request and is never listed here.
    """
    index: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in store.read("requests.jsonl"):
        if row.get("purpose") != "discovery":
            continue
        if row.get("event") not in {"response", "validated_response"}:
            continue
        index.setdefault(_query_key(row), []).append(row)
    for rows in index.values():
        rows.sort(key=lambda row: (str(row.get("recorded_at") or ""),
                                   str(row.get("raw_sha256") or "")))
    return index


def _payloads(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per distinct stored payload, first observation wins."""
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        digest = str(row.get("raw_sha256") or "")
        if digest and digest not in seen:
            seen[digest] = row
    return list(seen.values())


def _round_rows(store: Store, ledger: str, selector: scope.Selector) -> list[dict[str, Any]]:
    rows = list(store.read(ledger))
    if selector.whole_store:
        return rows
    return [row for row in rows
            if row.get("round") == selector.round
            and bool(row.get("manifest_only")) == selector.manifest_only]


def render(project: Project, store: Store, selector: scope.Selector, *,
           admitted: dict[str, Any] | None = None) -> bytes:
    """The appendix as UTF-8 markdown, from `store` alone (plus the live project's floor)."""
    if admitted is None:
        admitted = admissibility.admit(project, store, round_name=selector.round,
                                       manifest_only=selector.manifest_only)
    queries = _query_rows(store, selector)
    requests = _request_index(store)

    lines: list[str] = []
    lines.append(f"# Search appendix — {project.name}")
    lines.append("")
    if selector.whole_store:
        scope_text = "whole store"
    elif selector.manifest_only:
        scope_text = "manifest-only population (all rounds)"
    else:
        scope_text = f"round {selector.round}"
    lines.append(f"Selector: {scope_text}")
    lines.append("")
    lines.append("This appendix is derived from the frozen ledger prefix of an export. It "
                 "records the queries that were run and what they returned; it is not a "
                 "completeness estimate (D10) and it does not pool evidence or count votes "
                 "(invariant 7).")
    lines.append("")

    # Provider summary, from recorded rows only: a provider with no query is not invented.
    summary: dict[str, dict[str, Any]] = {}
    for row in queries:
        provider = str(row.get("source_api") or "unknown")
        bucket = summary.setdefault(provider, {
            "queries": 0, "completed": 0, "failed": 0, "returned": 0,
            "further": 0, "discovery": set(), "fetch": set(),
        })
        bucket["queries"] += 1
        if row.get("ok"):
            bucket["completed"] += 1
        else:
            bucket["failed"] += 1
        bucket["returned"] += int(row.get("returned") or 0)
        if row.get("depth_capped") is True:
            bucket["further"] += 1
        if row.get("discovery_version") is not None:
            bucket["discovery"].add(str(row["discovery_version"]))
        for request in requests.get(_query_key(row), []):
            if request.get("fetch_version") is not None:
                bucket["fetch"].add(str(request["fetch_version"]))

    lines.append("## Searches per provider")
    lines.append("")
    if summary:
        lines.append("| provider | queries | completed | failed | returned | further hits "
                     "reported | discovery versions | fetch versions |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for provider in sorted(summary):
            bucket = summary[provider]
            lines.append(
                f"| {_cell(provider)} | {bucket['queries']} | {bucket['completed']} "
                f"| {bucket['failed']} | {bucket['returned']} | {bucket['further']} "
                f"| {_cell(', '.join(sorted(bucket['discovery'])) or '—')} "
                f"| {_cell(', '.join(sorted(bucket['fetch'])) or '—')} |")
    else:
        lines.append("No query is recorded for this selector.")
    lines.append("")

    lines.append("## Queries")
    lines.append("")
    named = 0
    if queries:
        lines.append("| provider | topic | query | cap | pages | returned | provider count "
                     "| stop | outcome | completed (UTC) |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for row in queries:
            budget = row.get("page_budget")
            requested = row.get("pages_requested")
            pages = (f"{requested}/{budget}" if budget is not None
                     else ("—" if requested is None else str(requested)))
            outcome = "OK" if row.get("ok") else (
                str(row.get("failure_class") or "FAILED"))
            lines.append(
                f"| {_cell(row.get('source_api'))} | {_cell(row.get('topic_id'))} "
                f"| {_cell(row.get('query'))} | {_cell(row.get('per_query'))} "
                f"| {_cell(pages)} | {_cell(row.get('returned'))} "
                f"| {_cell(row.get('total_available'))} "
                f"| {_cell(row.get('stop_reason'))} | {_cell(outcome)} "
                f"| {_cell(row.get('completed_at'))} |")
        lines.append("")
        lines.append("`pages` is pages requested / page budget; `provider count` is the "
                     "provider's own `meta.count`, not a total of the literature.")
        lines.append("")
        lines.append("### Payload hashes")
        lines.append("")
        for row in queries:
            payloads = _payloads(requests.get(_query_key(row), []))
            if not payloads:
                continue
            named += 1
            parts = []
            for payload in payloads:
                parts.append(f"`sha256:{payload['raw_sha256']}` "
                             f"(HTTP {payload.get('http_status')}, "
                             f"{payload.get('recorded_at')})")
            lines.append(f"- {_cell(row.get('source_api'))} · "
                         f"{_cell(row.get('topic_id'))} · "
                         f"`{_cell(row.get('query'))}`: " + ", ".join(parts))
        if not named:
            lines.append("No discovery payload hash is recorded for this selector.")
        else:
            lines.append("")
            lines.append("Hashes are of the raw response bodies stored by this run, in request "
                         "order. Only `purpose: discovery` responses are search payloads; "
                         "acquisition and citation requests are not listed.")
    lines.append("")

    lines.append("## Failed searches and pages")
    lines.append("")
    failed = [row for row in queries if not row.get("ok")]
    page_failures = [(row, failure) for row in queries
                     for failure in (row.get("page_failures") or [])]
    if failed:
        lines.append("| provider | topic | query | failure | detail |")
        lines.append("|---|---|---|---|---|")
        for row in failed:
            lines.append(
                f"| {_cell(row.get('source_api'))} | {_cell(row.get('topic_id'))} "
                f"| {_cell(row.get('query'))} "
                f"| {_cell(row.get('failure_class'))} | {_cell(row.get('detail'))} |")
    else:
        lines.append("No failed query is recorded for this selector.")
    if page_failures:
        lines.append("")
        for row, failure in page_failures:
            lines.append(
                f"- {_cell(row.get('source_api'))} · {_cell(row.get('topic_id'))} · "
                f"`{_cell(row.get('query'))}` page {failure.get('page')}: "
                f"{_cell(failure.get('failure_class'))} — {_cell(failure.get('detail'))}")
    lines.append("")

    lines.append("## What was not searched")
    lines.append("")
    capped = [row for row in queries if row.get("depth_capped") is True]
    if capped:
        names = ", ".join(f"{row.get('source_api')} · {row.get('topic_id')} · "
                          f"`{row.get('query')}`" for row in capped)
        label = "query" if len(capped) == 1 else "queries"
        lines.append(f"- {len(capped)} {label} report further provider hits "
                     f"(`depth_capped`): the returned page omits works the provider says "
                     f"exist. {names}.")
    else:
        lines.append("- No query reports further provider hits (`depth_capped` is false or "
                     "unavailable).")
    stop_counts: dict[str, int] = {}
    for row in queries:
        reason = str(row.get("stop_reason") or "unrecorded")
        stop_counts[reason] = stop_counts.get(reason, 0) + 1
    if stop_counts:
        lines.append("- Stop reasons: " + ", ".join(
            f"{name} {count}" for name, count in sorted(stop_counts.items())) + ".")
    if failed:
        lines.append(f"- {len(failed)} queries failed (listed above); a failed query is not "
                     "an empty search.")
    lines.append(f"- Payload hashes were recorded for {named} of {len(queries)} queries.")
    if selector.manifest_only:
        lines.append("- This is a manifest-only flow: its population is independently "
                     "declared, and no discovery query is claimed as its source.")
    elif queries:
        lines.append("- `returned` is what one page or a bounded page run gave; it is not the "
                     "literature available.")
    lines.append("")

    # Stage denominators, from the same scoped readers every figure uses (scope.py, F1).
    sources = scope.source_ids(store, selector)
    documents = {source: row for source, row
                 in store.latest_by("documents.jsonl", "source_id").items()
                 if source in sources}
    chunks = {key: row for key, row in chunk_sets.current(store).items()
              if str(row.get("source_id")) in sources}
    held_claims, held_rejections = claim_records.current(store)
    claims = {key: row for key, row in held_claims.items()
              if str(row.get("source_id")) in sources}
    rejections = {key: row for key, row in held_rejections.items()
                  if str(row.get("source_id")) in sources}
    reviews = {key: row for key, row in review.current(store).items() if key in claims}
    profiles = _round_rows(store, "profiles.jsonl", selector)
    adjudications = _round_rows(store, "adjudications.jsonl", selector)

    lines.append("## Stage denominators (row counts, not a result)")
    lines.append("")
    lines.append("These are counts of rows in the selected population, not a synthesis and not "
                 "a vote count. Vote counting is not synthesis (invariant 7).")
    lines.append("")
    lines.append("| stage | count |")
    lines.append("|---|---|")
    lines.append(f"| candidates found | {admitted.get('found')} |")
    lines.append(f"| with a source class | {admitted.get('classified')} |")
    lines.append(f"| unclassified | {admitted.get('unclassified')} |")
    lines.append(f"| acquisition attempted | {admitted.get('attempted')} |")
    lines.append(f"| obtained | {admitted.get('obtained')} |")
    lines.append(f"| confirmed | {admitted.get('confirmed')} |")
    lines.append(f"| awaiting normalize | {admitted.get('awaiting_normalize')} |")
    lines.append(f"| documents | {len(documents)} |")
    lines.append(f"| active chunks | {len(chunks)} |")
    lines.append(f"| claims accepted | {len(claims)} |")
    lines.append(f"| claims rejected | {len(rejections)} |")
    lines.append(f"| claims with a current review | {len(reviews)} |")
    lines.append(f"| profiles | {len(profiles)} |")
    lines.append(f"| signed adjudications | {len(adjudications)} |")
    lines.append("")

    rate = admitted.get("rate")
    rate_text = f"{rate:.2f}" if isinstance(rate, (int, float)) else "—"
    by_class = admitted.get("by_class") or {}
    basis = admitted.get("basis") or "obtained"
    basis_count = sum(int(bucket.get(basis) or 0) for bucket in by_class.values())
    floor = admitted.get("floor")
    floor_text = f"{floor:.2f}" if isinstance(floor, (int, float)) else str(floor)
    lines.append(f"Floor: {basis} {basis_count} of {admitted.get('found')} = {rate_text} "
                 f"against floor {floor_text} "
                 f"(v{admitted.get('floor_version')}, {admitted.get('floor_set_at')}) — "
                 f"{admitted.get('status')}.")
    if by_class:
        lines.append("")
        lines.append("| class | found | basis | count | rate | floor | meets |")
        lines.append("|---|---|---|---|---|---|---|")
        for klass in sorted(by_class):
            bucket = by_class[klass]
            basis = bucket.get("basis") or "obtained"
            class_rate = bucket.get("rate")
            class_rate_text = (f"{class_rate:.2f}"
                               if isinstance(class_rate, (int, float)) else "—")
            lines.append(
                f"| {_cell(klass)} | {bucket.get('found')} | {basis} "
                f"| {bucket.get(basis)} | {class_rate_text} | {bucket.get('floor')} "
                f"| {bucket.get('meets_floor')} |")
    lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")
