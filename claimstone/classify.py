"""Which source class a candidate belongs to, according to rules the project declared.

Invariant 4: the engine holds no domain knowledge. "A journal article is refereed" is domain
knowledge, so it lives in `sources.yaml` and this module only applies what it finds there — the
same arrangement as the manifest's class aliases.

A candidate no rule covers gets no class. It is not guessed and not discarded: stage 2 will refuse
it, which is correct, and `uncovered()` says which attribute values went unmatched so the remedy is
to declare a rule rather than to loosen one.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from claimstone import net
from claimstone.config import SourceClass

# Which candidate field each predicate reads, and the source_api it is restricted to. A venue type
# only means something alongside the API that reported it: "journal" from OpenAlex and
# "journal-article" from Crossref are different vocabularies.
_VENUE_PREDICATES = {
    "openalex_source_type": "openalex",
    "crossref_type": "crossref",
}

# Reported when a candidate carries nothing any predicate can read. Measured: the citation channel
# produced 37 unclassified candidates on the real corpus and `uncovered` reported `{}` — silence at the
# one moment the missing rule was the only thing worth knowing. A row with no venue type at all is a
# different gap from a row with a venue type no rule mentions, and the remedies differ: the first needs
# a resolution step or a rule on `source_api`, the second needs one more value in a list.
NOTHING_TO_MATCH = "(nothing to match on)"


def _host_matches(url: str, patterns: Sequence[str]) -> bool:
    host = net.host_of(url)
    if not host:
        return False
    # Suffix matching on a label boundary, so notnber.org is not nber.org.
    return any(host == p or host.endswith(f".{p}") for p in patterns)


def _predicate_matches(candidate: dict[str, Any], name: str, values: Sequence[str]) -> bool:
    if name == "source_api":
        return str(candidate.get("source_api") or "") in values
    if name == "host":
        return _host_matches(str(candidate.get("url") or ""), values)
    required_api = _VENUE_PREDICATES[name]
    if str(candidate.get("source_api") or "") != required_api:
        return False
    return str(candidate.get("venue_type") or "") in values


def classify(candidate: dict[str, Any], classes: Iterable[SourceClass]) -> str | None:
    """The first declared class whose rules match. Declaration order is the priority."""
    for klass in classes:
        if not klass.assign_when:
            continue
        if any(
            _predicate_matches(candidate, name, values)
            for name, values in klass.assign_when.items()
        ):
            return klass.id
    return None


def uncovered(
    candidates: Iterable[dict[str, Any]], classes: Sequence[SourceClass]
) -> dict[str, dict[str, int]]:
    """For candidates no rule covered, which attribute values were seen and how often.

    The point is that "7 unclassified" is not actionable and "7 unclassified, all
    openalex_source_type=conference" is: it names the rule that is missing.
    """
    seen: dict[str, dict[str, int]] = {}
    for candidate in candidates:
        if classify(candidate, classes) is not None:
            continue
        api = str(candidate.get("source_api") or "")
        value = str(candidate.get("venue_type") or "")
        predicate = next(
            (name for name, required in _VENUE_PREDICATES.items() if api == required), None
        )
        if predicate is not None and value:
            bucket = seen.setdefault(predicate, {})
            bucket[value] = bucket.get(value, 0) + 1
            continue
        # Nothing readable: no venue type, or an API whose vocabulary no predicate covers. Counted by
        # the API that produced it, because that is what a rule would have to name.
        bucket = seen.setdefault(NOTHING_TO_MATCH, {})
        bucket[api or "unknown"] = bucket.get(api or "unknown", 0) + 1
    return seen
