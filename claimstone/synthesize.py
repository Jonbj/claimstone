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
from typing import Any, Mapping

from . import admissibility, claimgate, evidence, profile_inputs
from .config import Project, check_registry_drift
from .store import Store

# All five are outcomes an adjudicator records. None is produced by a threshold here or anywhere.
VERDICTS = ("SUPPORTED", "CONTRADICTED", "CONTESTED_IN_LITERATURE",
            "UNANSWERED_IN_LITERATURE", "NEVER_ASKED")

# A rationale is the whole justification for a verdict, and a verdict whose reasoning does not survive
# being written down is not one. Short enough to be honest about, long enough to have an argument in it.
MIN_RATIONALE_CHARS = 120

PROFILE_VERSION = 5

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


def preview(
    project: Project,
    store: Store,
    *,
    round_name: str | None = None,
    manifest_only: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Recompute the current profiles without appending or making a request."""
    check_registry_drift(project, store, record=False)
    verdict = admissibility.admit(project, store, round_name=round_name,
                                  manifest_only=manifest_only)
    if verdict["status"] == admissibility.INSUFFICIENT:
        raise NotAdmissible(
            f"{verdict['status']}: {verdict['rate']} against floor {verdict['floor']}"
            + (f", classes below their own floor: {', '.join(verdict['classes_below_floor'])}"
               if verdict["classes_below_floor"] else ""))
    inputs = profile_inputs.collect(project, store, round_name=round_name,
                                    manifest_only=manifest_only)
    roles = {c.id: c.role for c in project.classes if c.role}
    written: list[dict[str, Any]] = []
    for question in project.questions:
        if question.kind not in evidence.FIELDS_BY_KIND:
            row = evidence.not_applicable(question)
        else:
            completion = inputs["completion"][question.kind]
            blocking = list(verdict["blocking"])
            for count, reason in (("unanswered", "awaiting_extract"),
                                  ("unharvested", "awaiting_harvest"),
                                  ("unregated", "awaiting_regate"),
                                  ("unchunked_sources", "awaiting_chunks")):
                if completion[count]:
                    blocking.append(reason)
            if store.torn_tail:
                blocking.append("torn_ledger_tail")
            row = evidence.profile(
                question, claims=inputs["claims"], reviews=inputs["reviews"],
                rejections=inputs["rejections"], examined=inputs["examined"], roles=roles,
                registry_version=project.registry_version, registry_sha256=project.registry_sha256,
                provisional=bool(blocking), blocking=blocking)
            row["extraction"] = completion
        row.update({"profile_version": PROFILE_VERSION, "claim_gate_version": claimgate.CLAIM_GATE_VERSION,
                    "round": round_name,
                    "manifest_only": manifest_only, "registry_version": project.registry_version,
                    "registry_sha256": project.registry_sha256,
                    "population": inputs["sources"],
                    "evidence_sha256": inputs["evidence_sha256"][str(question.id)],
                    "acquisition": {key: verdict[key] for key in
                                    ("found", "obtained", "confirmed", "rate", "basis", "floor",
                                     "floor_version", "floor_set_at", "final", "blocking")}})
        row["profile_sha256"] = evidence._digest(row)
        written.append(row)
    return written, verdict


def build(
    project: Project,
    store: Store,
    *,
    round_name: str | None = None,
    manifest_only: bool = False,
) -> dict[str, Any]:
    """Write one profile per question, or refuse the round. Never both."""
    written, verdict = preview(project, store, round_name=round_name, manifest_only=manifest_only)
    check_registry_drift(project, store)
    for row in written:
        row["built_at"] = _now()
        store.append(PROFILES, row)

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
        "final": all(not row.get("provisional") for row in profiles),
        "acquisition_final": verdict["final"],
        "admissibility": verdict["status"],
        "rate": verdict["rate"],
        "floor": verdict["floor"],
        # Mandatory, and never to be printed as a correction: it is a disclosure that none was made.
        "no_controlled_error_rate_across": len(profiles),
    }


def _scope(row: Mapping[str, Any], round_name: str | None, manifest_only: bool) -> bool:
    return row.get("round") == round_name and bool(row.get("manifest_only")) == manifest_only


def latest_profiles(store: Store, *, round_name: str | None = None,
                    manifest_only: bool = False) -> dict[str, dict[str, Any]]:
    return {str(row["question_id"]): dict(row) for row in store.read(PROFILES)
            if _scope(row, round_name, manifest_only)}


def adjudications(store: Store, *, round_name: str | None = None,
                  manifest_only: bool = False) -> dict[str, dict[str, Any]]:
    return {str(row["question_id"]): dict(row) for row in store.read(ADJUDICATIONS)
            if _scope(row, round_name, manifest_only)}


def adjudicate(
    store: Store,
    question_id: str,
    *,
    project: Project,
    round_name: str | None = None,
    manifest_only: bool = False,
    verdict: str,
    rationale: str,
    by: str,
    profile_sha256: str = "",
) -> dict[str, Any]:
    """Record one person's judgement about one profile. The only verdict-producing call in the project.

    The whole transaction — read the stored profile, compare it against the live preview, append
    the signature — holds the project writer lock (F5): a synthesize racing this call either
    finishes before it (the check sees the new profile and the old hash is refused) or waits
    until after (the signature precedes the new profile, and the report's staleness rule is
    what the reader sees). What can no longer happen is the third outcome: a profile change
    landing between the check and the append, leaving a signature on a hash that was already
    old when it was written.
    """
    if verdict not in VERDICTS:
        raise ValueError(f"{verdict!r} is not one of {list(VERDICTS)}")
    with store.writer_lock():
        profiles = latest_profiles(store, round_name=round_name, manifest_only=manifest_only)
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
        fresh, _ = preview(project, store, round_name=round_name, manifest_only=manifest_only)
        current_profile = next((r for r in fresh if str(r["question_id"]) == str(question_id)), None)
        if current_profile is None or current_profile["profile_sha256"] != profile.get("profile_sha256"):
            raise StaleProfile("stored profile differs from current evidence; run synthesize and read it again")
        if not profile_sha256:
            raise ValueError("the profile hash shown to the adjudicator is required")
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
            "round": round_name,
            "manifest_only": manifest_only,
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


def verdicts(store: Store, *, project: Project, round_name: str | None = None,
             manifest_only: bool = False) -> dict[str, Any]:
    """Every profile with whatever judgement has been recorded against it, stale ones named as stale."""
    profiles = latest_profiles(store, round_name=round_name, manifest_only=manifest_only)
    recorded = adjudications(store, round_name=round_name, manifest_only=manifest_only)
    try:
        fresh, _ = preview(project, store, round_name=round_name, manifest_only=manifest_only)
        current = {str(row["question_id"]): row for row in fresh}
        unavailable = ""
    except NotAdmissible as exc:
        current = {}
        unavailable = str(exc)
    rows: list[dict[str, Any]] = []
    for question_id, profile in sorted(profiles.items()):
        live = current.get(question_id)
        outdated = live is None or live.get("profile_sha256") != profile.get("profile_sha256")
        row: dict[str, Any] = {"profile": live or profile, "verdict": None, "stale": False,
                               "stored_profile_stale": outdated, "unavailable": unavailable}
        found = recorded.get(question_id)
        if found is not None:
            # A judgement made against different evidence is a judgement about a different question,
            # and quietly keeping it on screen is how a verdict outlives its reason. With a live
            # profile, its hash decides. Without one the round is inadmissible now — and since
            # `build` refuses an inadmissible round, a profile it wrote records a round that
            # passed when the premise was signed, so the refusal itself is the movement. The
            # three recorded counts cannot prove admissibility, only refuse to disprove it: a
            # `discover --reclassify` row flipping a candidate's class can break that class's own
            # floor at identical found/obtained/confirmed, and comparing counts there would call
            # the stale verdict fresh. A stored profile with no acquisition block is a hand-written
            # row, not one `build` wrote, so only there does the hash the adjudicator signed decide.
            if live is not None:
                row["stale"] = (bool(live.get("provisional"))
                                or str(found.get("profile_sha256")) != str(live.get("profile_sha256")))
            else:
                row["stale"] = (bool(profile.get("acquisition"))
                                or str(found.get("profile_sha256"))
                                != str(profile.get("profile_sha256")))
            row["verdict"] = found
        rows.append(row)
    return {
        "rows": rows,
        "adjudicated": sum(1 for r in rows if r["verdict"] and not r["stale"]),
        "stale": sum(1 for r in rows if r["stale"]),
        "awaiting_adjudication": sum(
            1 for r in rows
            if not r["verdict"] and not r["unavailable"] and not r["profile"].get("provisional")
            and r["profile"].get("state") != evidence.NOT_APPLICABLE),
        "no_controlled_error_rate_across": sum(
            1 for r in rows if r["profile"].get("state") != evidence.NOT_APPLICABLE),
    }
