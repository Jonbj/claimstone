"""Stage 6 — claims into an evidence profile per question. Deterministic, and it concludes nothing.

**No model, no network, and no statistics.** D15 refused to specify this stage until a verdict was
defined; D16 defined one, and defining it removed most of what this stage was going to do. Read what the
verdict contract's rules require and none of them needs an aggregated estimate — they are counting and
coverage rules, so there is no pool here, no R, and no publication-bias correction. Pooling stays a
separate deliverable for whoever wants a magnitude; the project's contract is "a verdict per question",
not "an effect size per question", and conflating the two is how a verdict acquires a false precision.

**No multiplicity correction either, and the disclosure is mandatory.** Multiplicity control was wanted
because the design assumed significance testing. These rules test no significance: there is no p-value
in them and so no family-wise error rate to control, and a Benjamini-Hochberg adjustment over
count-based rules would be rigour-shaped output with no object. What is required instead is disclosure —
how many questions were asked, of which kinds, and that no error rate is controlled across them.

**Two gates, both refusals.**

The round must be admissible. `INSUFFICIENT_ACQUISITION` stops this stage and writes nothing: invariant
3, and this is the first place in the project with something to gate. A corpus read at 42% that certifies
itself complete is worse than no corpus.

The round must be final to be adjudicated. A profile built while anything is still arriving is labelled
`provisional` and `adjudicate` refuses it, because a judgement recorded against evidence that was still
changing is a judgement about something that no longer exists.

**And no verdict is produced here.** Layer 1 describes; a person judges and signs. `adjudicate` is the
only command in this project that writes a judgement, and the only place a verdict can come from.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterable, Mapping

from . import admissibility, evidence
from .config import Project
from .store import Store

# All five are outcomes an adjudicator records. None is produced by a threshold here or anywhere.
VERDICTS = ("SUPPORTED", "CONTRADICTED", "CONTESTED_IN_LITERATURE",
            "UNANSWERED_IN_LITERATURE", "NEVER_ASKED")

# A rationale is the whole justification for a verdict, and a verdict whose reasoning does not survive
# being written down is not one. Short enough to be honest about, long enough to have an argument in it.
MIN_RATIONALE_CHARS = 120

PROFILES = "profiles.jsonl"
ADJUDICATIONS = "adjudications.jsonl"


class NotAdmissible(RuntimeError):
    """The round is below its acquisition floor. Invariant 3: nothing waives it, including a flag."""


class Provisional(RuntimeError):
    """The profile can still change, so a judgement against it would be about something else."""


class StaleProfile(RuntimeError):
    """The hash the adjudicator was shown is not the hash of the profile now."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _reviews(store: Store) -> dict[str, dict[str, Any]]:
    return {str(k): dict(v) for k, v in store.latest_by("reviews.jsonl", "claim_id").items()}


def build(
    project: Project,
    store: Store,
    *,
    round_name: str | None = None,
    manifest_only: bool = False,
) -> dict[str, Any]:
    """Write one profile per question, or refuse the round. Never both."""
    verdict = admissibility.admit(project, store, round_name=round_name,
                                  manifest_only=manifest_only)
    if verdict["status"] == admissibility.INSUFFICIENT:
        # No profiles at all. Not a warning, and not a partial run: a round that did not obtain what it
        # found produces no verdicts, and producing profiles from it would invite one anyway.
        raise NotAdmissible(
            f"{verdict['status']}: {verdict['rate']} against floor {verdict['floor']}"
            + (f", classes below their own floor: {', '.join(verdict['classes_below_floor'])}"
               if verdict["classes_below_floor"] else "")
        )

    claims = [dict(row) for row in store.latest_by("claims.jsonl", "claim_id").values()]
    rejections = list(store.read("rejections.jsonl"))
    reviews = _reviews(store)
    roles = {c.id: c.role for c in project.classes if c.role}

    # Sources actually read, which is the honest denominator for "sources speaking to this question":
    # a source that was never chunked cannot speak to anything, and counting the manifest instead would
    # make coverage a statement about the reading list rather than about the corpus.
    examined = len({str(row.get("source_id")) for row in store.read("chunks.jsonl")
                    if row.get("source_id")})

    blocking = list(verdict["blocking"])
    written: list[dict[str, Any]] = []
    for question in project.questions:
        if question.kind not in evidence.FIELDS_BY_KIND:
            # An operational question. A row, not a silence.
            row = evidence.not_applicable(question)
        else:
            row = evidence.profile(
                question,
                claims=claims,
                reviews=reviews,
                rejections=rejections,
                examined=examined,
                roles=roles,
                registry_version=project.registry_version,
                registry_sha256=project.registry_sha256,
                provisional=not verdict["final"],
                blocking=blocking,
            )
        row["built_at"] = _now()
        row["round"] = round_name
        store.append(PROFILES, row)
        written.append(row)

    profiles = [r for r in written if r.get("kind") in evidence.FIELDS_BY_KIND]
    return {
        "profiles": len(profiles),
        "not_applicable": len(written) - len(profiles),
        "questions": len(written),
        "by_kind": {k: sum(1 for r in written if r.get("kind") == k)
                    for k in sorted({str(r.get("kind")) for r in written})},
        "no_verified_claim": sum(1 for r in profiles
                                 if r.get("state") == evidence.NO_VERIFIED_CLAIM),
        "provisional": sum(1 for r in profiles if r.get("provisional")),
        "final": verdict["final"],
        "admissibility": verdict["status"],
        "rate": verdict["rate"],
        "floor": verdict["floor"],
        # Mandatory, and never to be printed as a correction: it is a disclosure that none was made.
        "no_controlled_error_rate_across": len(profiles),
    }


def latest_profiles(store: Store) -> dict[str, dict[str, Any]]:
    return {str(k): dict(v) for k, v in store.latest_by(PROFILES, "question_id").items()}


def adjudications(store: Store) -> dict[str, dict[str, Any]]:
    return {str(k): dict(v) for k, v in store.latest_by(ADJUDICATIONS, "question_id").items()}


def adjudicate(
    store: Store,
    question_id: str,
    *,
    verdict: str,
    rationale: str,
    by: str,
    profile_sha256: str = "",
) -> dict[str, Any]:
    """Record one person's judgement about one profile. The only verdict-producing call in the project."""
    if verdict not in VERDICTS:
        raise ValueError(f"{verdict!r} is not one of {list(VERDICTS)}")
    profiles = latest_profiles(store)
    profile = profiles.get(str(question_id))
    if profile is None:
        raise KeyError(f"no profile for {question_id}: run synthesize first")
    if profile.get("state") == evidence.NOT_APPLICABLE:
        raise ValueError(
            f"{question_id} is kind {profile.get('kind')!r} and receives no verdict — "
            "a sixth state is not how that is recorded")
    if profile.get("provisional"):
        raise Provisional(
            f"{question_id}'s profile is provisional ({', '.join(profile.get('blocking') or [])}): "
            "a verdict recorded against evidence still arriving is a verdict about something else")
    text = (rationale or "").strip()
    if len(text) < MIN_RATIONALE_CHARS:
        raise ValueError(
            f"a rationale of {len(text)} characters is below the declared minimum of "
            f"{MIN_RATIONALE_CHARS}: the reasoning is the verdict's only defence")
    current = str(profile.get("profile_sha256") or "")
    if profile_sha256 and profile_sha256 != current:
        raise StaleProfile(f"shown {profile_sha256[:12]}, current {current[:12]}")

    row = {
        "question_id": str(question_id),
        "verdict": verdict,
        "rationale": text,
        # What makes this auditable: if the evidence changes, the judgement is stale and the report says
        # so rather than continuing to display it.
        "profile_sha256": current,
        "decision_contract_version": profile.get("decision_contract_version"),
        "registry_version": profile.get("registry_version"),
        "registry_sha256": profile.get("registry_sha256"),
        "adjudicated_by": by,
        "adjudicated_at": _now(),
    }
    store.append(ADJUDICATIONS, row)
    return row


def verdicts(store: Store) -> dict[str, Any]:
    """Every profile with whatever judgement has been recorded against it, stale ones named as stale."""
    profiles = latest_profiles(store)
    recorded = adjudications(store)
    rows: list[dict[str, Any]] = []
    for question_id, profile in sorted(profiles.items()):
        row: dict[str, Any] = {"profile": profile, "verdict": None, "stale": False}
        found = recorded.get(question_id)
        if found is not None:
            # A judgement made against different evidence is a judgement about a different question,
            # and quietly keeping it on screen is how a verdict outlives its reason.
            row["stale"] = str(found.get("profile_sha256")) != str(profile.get("profile_sha256"))
            row["verdict"] = found
        rows.append(row)
    return {
        "rows": rows,
        "adjudicated": sum(1 for r in rows if r["verdict"] and not r["stale"]),
        "stale": sum(1 for r in rows if r["stale"]),
        "awaiting_adjudication": sum(
            1 for r in rows
            if not r["verdict"] and r["profile"].get("state") != evidence.NOT_APPLICABLE),
        "no_controlled_error_rate_across": sum(
            1 for r in rows if r["profile"].get("state") != evidence.NOT_APPLICABLE),
    }
