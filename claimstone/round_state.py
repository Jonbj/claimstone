"""The state of one round, derived from the ledgers — the dashboard's pure core.

This module is the `round_state.py` of the dashboard spec (§3): it reads the JSONL ledgers and
computes, with no HTTP anywhere, so that "how far along are we" stays testable and available to
the CLI as well as to `dashboard.py`.

**Counting follows one rule per question, and the rules are imported, not reinvented.** Accepted
annotations and rejections are whatever `claim_records.current` says — the last outcome per
`claim_id` with cross-ledger supersede (D46) — and the question spine is whatever
`synthesize.verdicts` computes, because that is the same evidence a person would sign against.
A second counting rule in the same page is how a dashboard comes to disagree with `report`.

**A round means one selector (review F1/F3).** Every figure this module shows for a selector is
filtered through `claimstone.scope`, so a claim, review, chunk or document written by another
round cannot appear in this round's counts. The whole-store selector keeps the historical
behaviour byte for byte.

**Errors are not zeros (review F2).** A damaged ledger surfaces as an entry in
`RoundState.errors` with the affected figures withheld (`None`), never as a zero the reader
would trust. `Store.read` already refuses to skip interior damage; this module refuses to turn
the refusal into a number.

**None is not zero (§4).** `inputs`, `outputs` and `rejected` are `int | None` throughout: None
means *not knowable in principle* — discover has no denominator for what exists in the world,
review discards nothing — while a countable zero is returned as `0`. Rendering them alike is the
defect the spec's honesty rule 2 exists to prevent.

**Discover never gets a percentage (§6, D10).** How much relevant work exists is unknown. The
state carries the candidate count and the channels that found them. Even two channels do not
make literature completeness estimable for this corpus; a second channel instead exposes works
the first missed.

**Coverage is post-review.** A question that has not been read shows the coverage the current
profile actually certifies (often 0 of examined), never a count of raw claims — coverage measured
after extraction is a statement about the extractor (D40/D44).
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
from dataclasses import dataclass
from typing import Any

from claimstone import scope
from claimstone.config import Project
from claimstone.store import LedgerCorrupt, Store

# The six stages, in pipeline order. All are implemented; `implemented` stays in the state so a
# future stage can declare itself the way the CLI's placeholders do — present, empty, and saying
# why, rather than rendering zero.
STAGES: tuple[str, ...] = ("discover", "acquire", "normalize", "extract", "review", "synthesize")

# Which ledger each stage last wrote, for `last_write` and the activity log.
PROFILES = "profiles.jsonl"
ADJUDICATIONS = "adjudications.jsonl"
STAGE_LEDGERS: dict[str, tuple[str, ...]] = {
    "discover": ("candidates.jsonl",),
    "acquire": ("acquisitions.jsonl",),
    "normalize": ("documents.jsonl", "chunks.jsonl"),
    "extract": ("claims.jsonl", "rejections.jsonl"),
    "review": ("reviews.jsonl",),
    "synthesize": (PROFILES,),
    # Not a stage: the only place a verdict comes from, shown on the strip for that reason.
    "adjudicate": (ADJUDICATIONS,),
}
ACTIVITY_LEDGERS: tuple[str, ...] = (
    "candidates.jsonl", "acquisitions.jsonl", "documents.jsonl", "chunks.jsonl",
    "claims.jsonl", "rejections.jsonl", "reviews.jsonl", PROFILES, ADJUDICATIONS,
)

# Timestamp keys a row may carry, tried in order for the activity log. Absent everywhere falls
# back to the ledger's mtime, which the caller is told happened.
_ROW_TIMES = ("harvested_at", "reviewed_at", "built_at", "adjudicated_at", "repaired_at",
              "requested_at", "fetched_at", "discovered_at")

# The withheld-stage note: a damaged ledger's figures are absent on purpose, and the reader must
# be told that rather than read a zero.
_WITHHELD = "ledger damaged: figures withheld"


@dataclass(frozen=True)
class Progress:
    done: int
    total: int | None  # None where no denominator exists (§6)
    label: str


@dataclass(frozen=True)
class StageState:
    name: str
    implemented: bool
    inputs: int | None
    outputs: int | None
    rejected: int | None
    progress: Progress | None
    last_write: str | None  # ISO timestamp of the newest row this stage wrote
    detail: str | None = None  # the honesty note a stage owes when a number would lie


@dataclass(frozen=True)
class QuestionRow:
    """One entry of the question spine (§5): the registry is what the tool is for."""

    id: str
    text: str
    kind: str
    claims: int | None                      # current accepted annotations citing it
    claims_by_class: dict[str, int]         # per class before the aggregate (invariant 6)
    coverage_sources: int | None            # post-review: sources that speak to it
    coverage_examined: int | None           # sources examined, the honest denominator
    provisional: bool
    blocking: tuple[str, ...]
    state: str | None                       # the profile's own state, e.g. NO_VERIFIED_CLAIM
    profile_sha256: str | None
    extraction: dict[str, int] | None       # expected / unanswered / unharvested / unregated
    verdict: str | None                     # only ever a person's, from adjudications.jsonl
    verdict_stale: bool


@dataclass(frozen=True)
class RoundState:
    project: str
    round: str | None
    stages: tuple[StageState, ...]
    questions: tuple[QuestionRow, ...]
    verdicts_recorded: int      # a knowable count: rows in adjudications.jsonl
    verdicts_stale: int
    floor: dict[str, Any] | None    # what `report` judged the round on, verbatim
    rejections_by_reason: dict[str, int]  # current, same supersede rule as outputs (§6)
    unavailable: str           # non-empty when the corpus is inadmissible and profiles refused
    # Named integrity failures (review F2). Empty when every ledger read cleanly; each entry
    # starts with a class prefix (LEDGER_CORRUPT / CHUNK_SET_INVALID). Last field: every
    # constructor call that predates it keeps working, and `as_dict` carries it to the page.
    errors: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _mtime_iso(path) -> str | None:
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return None
    return _dt.datetime.fromtimestamp(stamp, tz=_dt.timezone.utc).isoformat(timespec="seconds")


def _row_time(row: dict[str, Any], ledger: str, store: Store) -> str:
    for key in _ROW_TIMES:
        value = row.get(key)
        if value:
            return str(value)
    return _mtime_iso(store.path(ledger)) or ""


def _row_time_keyed(row: dict[str, Any]) -> str | None:
    """The row's own timestamp, or None when it carries none. A scoped read never falls back to
    a file's mtime (review F17): that mtime belongs to whichever round wrote the ledger last."""
    for key in _ROW_TIMES:
        value = row.get(key)
        if value:
            return str(value)
    return None


def _last_write(store: Store, ledgers: tuple[str, ...], *, selector: scope.Selector | None = None,
                keys: set[str] | None = None, sources: set[str] | None = None,
                claim_sources: dict[str, str] | None = None) -> str | None:
    """The newest write a selector can see. Whole store keeps the mtime behaviour; a scoped
    selector sees only rows `scope.row_in_scope` admits, and rows without their own timestamp
    have no trustworthy time at all (review F17), so they cannot be the newest write."""
    if selector is None or selector.whole_store:
        stamps = [_mtime_iso(store.path(name)) for name in ledgers]
        stamps = [s for s in stamps if s]
        return max(stamps) if stamps else None
    best: str | None = None
    for name in ledgers:
        for row in store.read(name):
            if not scope.row_in_scope(name, row, selector=selector, keys=keys or set(),
                                      sources=sources or set(),
                                      claim_sources=claim_sources or {}):
                continue
            when = _row_time_keyed(row)
            if when and (best is None or when > best):
                best = when
    return best


def _stage_discover(store: Store, *, selector: scope.Selector,
                    keys: set[str] | None = None) -> StageState:
    in_scope = [
        row for row in store.latest_by("candidates.jsonl", "candidate_key").values()
        if scope.candidate_in_scope(row, selector)
    ]
    channels = sorted({str(row.get("channel") or "manifest") for row in in_scope}) or ["none"]
    if {"keyword", "citation"} <= set(channels):
        note = "keyword and citation channels observed: literature completeness remains unknown"
    elif len(in_scope) == 0:
        # Zero candidates still has no denominator for the relevant literature (§6): saying so
        # keeps the 0 from reading as "found everything".
        note = "no candidates in scope yet: completeness not estimable"
    else:
        # A manifest round has one channel. §6: show the count, say completeness is not estimable.
        note = "single channel (" + ", ".join(channels) + "): completeness not estimable"
    return StageState(
        name="discover", implemented=True,
        # No denominator exists for the relevant literature. The count and the channels are the
        # honest whole of it; a percentage here would invent the denominator (§6).
        inputs=None, outputs=len(in_scope), rejected=None,
        progress=None, detail=note,
        last_write=_last_write(store, STAGE_LEDGERS["discover"], selector=selector, keys=keys),
    )


def _stage_acquire(project: Project, store: Store, *, selector: scope.Selector,
                   keys: set[str] | None, errors: list[str]) -> tuple[StageState, dict[str, Any] | None]:
    from claimstone import admissibility

    try:
        admitted = admissibility.admit(project, store, round_name=selector.round,
                                       manifest_only=selector.manifest_only)
    except LedgerCorrupt as exc:
        # F2: a damaged acquisitions ledger is an error the page names, never "zero acquired".
        errors.append(f"LEDGER_CORRUPT: {exc}")
        return StageState("acquire", True, None, None, None, None, None,
                          detail=_WITHHELD), None
    found = int(admitted["found"])
    obtained = int(admitted["obtained"])
    basis = str(admitted["basis"])
    confirmed = admitted.get(basis)
    outputs = int(confirmed) if confirmed is not None else None
    progress = None
    if outputs is not None and found:
        progress = Progress(done=outputs, total=found,
                            label=f"{basis} of candidates found")
    state = StageState(
        name="acquire", implemented=True,
        inputs=found, outputs=outputs,
        # Rejected here is what acquire itself failed to obtain; a 200 that was not a document
        # is rejected by normalize, not by acquire, and the split is visible in `report`.
        rejected=found - obtained if found else None,
        progress=progress,
        last_write=_last_write(store, STAGE_LEDGERS["acquire"], selector=selector, keys=keys),
    )
    return state, admitted


def _stage_normalize(store: Store, acquired_count: int | None, *, selector: scope.Selector,
                     keys: set[str] | None, sources: set[str] | None,
                     errors: list[str]) -> tuple[StageState, int | None]:
    from claimstone import admissibility, chunk_sets

    try:
        documents = store.latest_by("documents.jsonl", "source_id")
        if not selector.whole_store:
            documents = {key: row for key, row in documents.items() if str(key) in (sources or set())}
        acquired_rows = admissibility.collapse(store)
    except LedgerCorrupt as exc:
        errors.append(f"LEDGER_CORRUPT: {exc}")
        return StageState("normalize", True, None, None, None, None, None,
                          detail=_WITHHELD), None
    acquired = sum(1 for key, row in acquired_rows.items()
                   if row.get("acquired") and (selector.whole_store or key in (keys or set())))
    confirmed = sum(1 for row in documents.values() if row.get("fulltext_confirmed"))
    try:
        chunks_map = chunk_sets.current(store)
    except LedgerCorrupt as exc:
        errors.append(f"LEDGER_CORRUPT: {exc}")
        return StageState("normalize", True, None, None, None, None, None,
                          detail=_WITHHELD), None
    except ValueError as exc:  # an inconsistent chunk set (D48), not a damaged ledger line
        errors.append(f"CHUNK_SET_INVALID: {exc}")
        return StageState("normalize", True, None, None, None, None, None,
                          detail=_WITHHELD), None
    chunks = sum(1 for row in chunks_map.values()
                 if selector.whole_store or str(row.get("source_id")) in (sources or set()))
    inputs = acquired_count if acquired_count is not None else (acquired or None)
    outputs = confirmed or None  # zero documents is "nothing happened yet", not a corpus
    rejected = (inputs - outputs) if (inputs is not None and outputs is not None) else None
    return StageState(
        name="normalize", implemented=True,
        inputs=inputs, outputs=outputs, rejected=rejected,
        progress=None,  # the confirmation split is `report`'s to state with its thresholds
        last_write=_last_write(store, STAGE_LEDGERS["normalize"], selector=selector,
                               keys=keys, sources=sources),
    ), chunks


def state(project: Project, store: Store, *, round_name: str | None = None,
          manifest_only: bool = False,
          precomputed_verdicts: dict[str, Any] | BaseException | None = None) -> RoundState:
    """Compute the round's state. Pure: reads the store, touches nothing else.

    `precomputed_verdicts` lets a caller that already ran `synthesize.verdicts` for the same
    selector, in the same request, hand over its result (or the exception it raised) instead of
    paying for the same computation twice. It is the identical computation on the identical
    ledgers, not a cache: nothing survives the request.
    """
    from claimstone import claim_records, review, synthesize
    from claimstone.config import RegistryDrift

    selector = scope.Selector(round_name, manifest_only)
    errors: list[str] = []
    whole = selector.whole_store
    keys: set[str] = set() if whole else set(scope.candidates(store, selector))
    sources: set[str] = set() if whole else scope.source_ids(store, selector)

    discover_state = _stage_discover(store, selector=selector, keys=keys)
    acquire_state, admitted = _stage_acquire(project, store, selector=selector, keys=keys,
                                             errors=errors)
    obtained = None
    if admitted is not None:
        obtained = int(admitted["obtained"]) or None
    normalize_state, chunk_count = _stage_normalize(store, obtained, selector=selector,
                                                    keys=keys, sources=sources, errors=errors)

    claims, rejections = claim_records.current(store)
    if not whole:
        claims = {key: row for key, row in claims.items()
                  if str(row.get("source_id")) in sources}
        rejections = {key: row for key, row in rejections.items()
                      if str(row.get("source_id")) in sources}
    claim_sources = {key: str(row.get("source_id")) for key, row in claims.items()}

    # The spine comes from `verdicts` because that is what a person reads before signing: the
    # same computation, or the dashboard would be a second opinion the project never asked for.
    try:
        if precomputed_verdicts is None:
            result = synthesize.verdicts(store, project=project, round_name=round_name,
                                         manifest_only=manifest_only)
        elif isinstance(precomputed_verdicts, BaseException):
            raise precomputed_verdicts
        else:
            result = precomputed_verdicts
        verdict_rows = result["rows"]
        unavailable = ""
    except synthesize.NotAdmissible as exc:  # an inadmissible corpus is a state, not a crash
        verdict_rows, unavailable = [], str(exc)
    except RegistryDrift as exc:             # a drifted registry is a state too (invariant 5)
        verdict_rows, unavailable = [], str(exc)
    except LedgerCorrupt as exc:             # corruption is a state *and* an error (review F2)
        verdict_rows, unavailable = [], str(exc)
        errors.append(f"LEDGER_CORRUPT: {exc}")

    # Aggregate completeness from the *live* profiles the spine is showing, so the stage fraction
    # and the per-question numbers can never disagree (they are the same rows).
    live_profiles = [row["profile"] for row in verdict_rows]
    extraction_expected = sum(int((row.get("extraction") or {}).get("expected") or 0)
                              for row in live_profiles)
    extraction_unanswered = sum(int((row.get("extraction") or {}).get("unanswered") or 0)
                                for row in live_profiles)
    progress = None
    if extraction_expected:
        # The honest extract fraction is readings answered over readings expected (D45), not
        # chunks over chunks: a chunk is asked about every question of its kind.
        progress = Progress(done=extraction_expected - extraction_unanswered,
                            total=extraction_expected,
                            label="readings answered of expected")
    extract_state = StageState(
        name="extract", implemented=True,
        inputs=chunk_count or None, outputs=len(claims) or None,
        rejected=len(rejections) or None, progress=progress,
        last_write=_last_write(store, STAGE_LEDGERS["extract"], selector=selector,
                               keys=keys, sources=sources),
    )

    reviews = review.current(store)
    if not whole:
        reviews = {key: row for key, row in reviews.items() if key in claims}
    total_claims = len(claims)
    review_state = StageState(
        name="review", implemented=True,
        inputs=total_claims or None, outputs=len(reviews) or None,
        # Review discards nothing: an OVERSTATED row is the most informative row in the ledger,
        # so `rejected` is None in principle, not zero (§4).
        rejected=None,
        progress=Progress(len(reviews), total_claims, "annotations reviewed of accepted")
        if total_claims else None,
        last_write=_last_write(store, STAGE_LEDGERS["review"], selector=selector,
                               keys=keys, sources=sources, claim_sources=claim_sources),
    )

    synthesize_state = StageState(
        name="synthesize", implemented=True,
        inputs=len(project.questions) or None,
        outputs=len({str(r["profile"].get("question_id")) for r in verdict_rows}) or None,
        rejected=None,  # it either runs or refuses; there is no progress to show (§6)
        progress=None,
        last_write=_last_write(store, STAGE_LEDGERS["synthesize"], selector=selector,
                               keys=keys, sources=sources, claim_sources=claim_sources),
    )

    spine = _question_spine(project, claims, verdict_rows)

    reasons: dict[str, int] = {}
    for row in rejections.values():
        reason = str(row.get("failure") or "unknown")
        reasons[reason] = reasons.get(reason, 0) + 1

    return RoundState(
        project=project.name, round=round_name,
        stages=(discover_state, acquire_state, normalize_state, extract_state, review_state,
                synthesize_state),
        questions=tuple(spine),
        verdicts_recorded=sum(1 for r in verdict_rows if r["verdict"] and not r["stale"]),
        verdicts_stale=sum(1 for r in verdict_rows if r["stale"]),
        floor=None if admitted is None else {
            key: admitted[key] for key in
            ("floor", "floor_version", "floor_set_at", "status", "basis", "rate", "found",
             "obtained", "confirmed", "final", "blocking", "failures_by_class", "failures_by_host")
            if key in admitted
        },
        rejections_by_reason=dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        unavailable=unavailable,
        # De-duplicated in first-seen order: two stages reading the same damaged ledger name
        # the same error, and the page should carry the fact once, not twice.
        errors=tuple(dict.fromkeys(errors)),
    )


def _profiles_for_spine(store: Store, round_name: str | None,
                        manifest_only: bool, errors: list[str]) -> list[dict[str, Any]]:
    """Current stored profiles in scope, without recomputation (for aggregate completeness)."""
    from claimstone import synthesize

    try:
        return list(synthesize.latest_profiles(store, round_name=round_name,
                                               manifest_only=manifest_only).values())
    except LedgerCorrupt as exc:
        errors.append(f"LEDGER_CORRUPT: {exc}")
        return []


def _question_spine(project: Project, claims: dict[str, dict[str, Any]],
                    verdict_rows: list[dict[str, Any]]) -> list[QuestionRow]:
    from claimstone import evidence

    per_question: dict[str, int] = {}
    per_class: dict[str, dict[str, int]] = {}
    for row in claims.values():
        qid = str(row.get("question_id"))
        per_question[qid] = per_question.get(qid, 0) + 1
        klass = str(row.get("source_class") or "unclassified")
        per_class.setdefault(qid, {})
        per_class[qid][klass] = per_class[qid].get(klass, 0) + 1

    by_id = {str(row["profile"].get("question_id")): row for row in verdict_rows}
    rows: list[QuestionRow] = []
    for question in project.questions:  # registry order, always (§5)
        row = by_id.get(question.id)
        profile = (row or {}).get("profile") or {}
        coverage = profile.get("coverage") or {}
        recorded = (row or {}).get("verdict")
        extraction = profile.get("extraction") or None
        rows.append(QuestionRow(
            id=question.id, text=question.text, kind=question.kind,
            claims=per_question.get(question.id, 0),
            claims_by_class=dict(sorted(per_class.get(question.id, {}).items())),
            coverage_sources=coverage.get("sources"),
            coverage_examined=coverage.get("examined"),
            provisional=bool(profile.get("provisional")),
            blocking=tuple(profile.get("blocking") or ()),
            # The engine's own categorical outcome, never silently a human verdict: NO_VERIFIED_CLAIM
            # is not NEVER_ASKED, and only screening by a person can say "never asked".
            state=str(profile.get("state")) if profile.get("state") else (
                evidence.NOT_APPLICABLE if question.kind == "operational" else None),
            profile_sha256=profile.get("profile_sha256"),
            extraction=extraction,
            verdict=str(recorded["verdict"]) if recorded else None,
            verdict_stale=bool((row or {}).get("stale")),
        ))
    return rows


def activity(store: Store, limit: int = 50, selector: scope.Selector | None = None) -> list[dict[str, Any]]:
    """The newest rows across ledgers, newest first, each with the stage that wrote it.

    A torn final line is skipped by `Store.read` — the reader's contract — and this reports the
    rows it actually read, never a count the file does not support. With a scoped selector only
    rows `scope.row_in_scope` admits are shown, and a row without its own timestamp is excluded:
    it has no trustworthy time, and this log is ordered by time (review F17).
    """
    cap = max(1, min(int(limit), 500))
    keys: set[str] = set()
    sources: set[str] = set()
    claim_sources: dict[str, str] = {}
    scoped = selector is not None and not selector.whole_store
    if scoped:
        keys = set(scope.candidates(store, selector))
        sources = scope.source_ids(store, selector)
        for row in store.latest_by("claims.jsonl", "claim_id").values():
            identifier = row.get("source_id")
            if identifier is not None and str(identifier) in sources:
                claim_sources[str(row.get("claim_id"))] = str(identifier)
    collected: list[tuple[str, str, str, dict[str, Any]]] = []
    for ledger in ACTIVITY_LEDGERS:
        stage = next((name for name, names in STAGE_LEDGERS.items() if ledger in names), ledger)
        for row in store.read(ledger):
            if scoped:
                if not scope.row_in_scope(ledger, row, selector=selector, keys=keys,
                                          sources=sources, claim_sources=claim_sources):
                    continue
                when = _row_time_keyed(row)
                if when is None:
                    continue
            else:
                when = _row_time(row, ledger, store)
            collected.append((when, stage, ledger, row))
    collected.sort(key=lambda item: item[0], reverse=True)
    return [
        {"when": when, "stage": stage, "ledger": ledger,
         "row": {k: row[k] for k in sorted(row) if k in (
             "source_id", "candidate_key", "question_id", "claim_id", "verdict", "failure",
             "failure_class", "state", "provisional", "acquired", "http_status", "licence",
             "backend", "model", "adjudicated_by", "decision", "note")}}
        for when, stage, ledger, row in collected[:cap]
    ]


def cheap_state(store: Store) -> dict[str, Any]:
    """Mtimes and row counts per ledger, plus the running inference — the poll endpoint (§9).

    `running` is an inference from mtime within the last 30 seconds and is labelled as one:
    "last write Ns ago", never a claim that a process is alive (§7).
    """
    now = _dt.datetime.now(_dt.timezone.utc)
    ledgers: dict[str, Any] = {}
    running: list[str] = []
    for ledger in ACTIVITY_LEDGERS:
        path = store.path(ledger)
        iso = _mtime_iso(path)
        if iso is None:
            ledgers[ledger] = {"mtime": None, "rows": None}  # absent: not knowable, not zero
            continue
        rows = 0
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.endswith("\n"):
                    rows += 1
        ledgers[ledger] = {"mtime": iso, "rows": rows}
        age = (now - _dt.datetime.fromtimestamp(path.stat().st_mtime, tz=_dt.timezone.utc)).total_seconds()
        if age < 30:
            running.append(f"{ledger}: last write {int(age)}s ago")
    return {"ledgers": ledgers, "running": running, "pid_note": "inference from mtime, not liveness"}
