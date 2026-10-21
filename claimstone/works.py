"""Which sources are one work. A derived view: it never rewrites a candidate key or a denominator (D158).

A search result keyed by DOI and the same paper found through a repository keyed by title are two
candidates, two documents and two sets of claims. Counting both counts one study twice in a profile.
The evidence for "same work" is stated here and nothing weaker is accepted: the folded titles are
equal and long enough to mean something. A near match stays a note (`discover.near_match`); a wrong
merge loses a source's claims, and this view loses nothing because the duplicate's rows stay listed.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from claimstone import ids

# A short title ("Introduction", "Meta-analysis") is shared by unrelated papers.
MIN_TITLE_CHARS = 25
BASIS_TITLE_EQUAL = "title_equal"


def _representative(members: list[str]) -> str:
    """A DOI-keyed source first, because it is the one a reader can cite; otherwise the first by key."""
    return sorted(members, key=lambda key: (not key.startswith("doi:"), key))[0]


def groups(candidates: Iterable[Mapping[str, Any]], source_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Groups of two or more of `source_ids` that are one work, each with the evidence for it."""
    wanted = {str(source) for source in source_ids}
    by_title: dict[str, set[str]] = {}
    for row in candidates:
        key = str(row.get("candidate_key") or "")
        if key not in wanted:
            continue
        folded = ids.normalize_title(row.get("title"))
        if len(folded) >= MIN_TITLE_CHARS:
            by_title.setdefault(folded, set()).add(key)
    found = []
    for folded, members in sorted(by_title.items()):
        if len(members) < 2:
            continue
        ordered = sorted(members)
        found.append({"work": _representative(ordered), "members": ordered, "basis": BASIS_TITLE_EQUAL})
    return found


def work_of(candidates: Iterable[Mapping[str, Any]], source_ids: Iterable[str]) -> dict[str, str]:
    """Source id -> the representative of its group, for the sources that are not their own work."""
    mapping: dict[str, str] = {}
    for group in groups(candidates, source_ids):
        for member in group["members"]:
            if member != group["work"]:
                mapping[member] = group["work"]
    return mapping
