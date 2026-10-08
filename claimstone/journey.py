"""The research journey, decided on the server (portal journey spec, J1).

Eight steps, each with a status and one plain sentence, computed from what the flow overview
has already read: the `Computed` object (round state, admission, verdict rows) and the inbox
cards. Nothing here opens a ledger of its own except the two small reads the spec names, the
scheduler's operations and the decisions' open items, and nothing imports the control server.

Rules that hold for every step:
- A summary is a fixed template filled from `figures`. Which template is chosen depends on the
  status, never on the result's content, so no wording varies with what was found.
- Unknown is `None` in `figures` and "—" in the sentence. Never 0 for unknown.
- No step reads a claim's stance or a profile's direction count: only counts and states. Flipping
  every stance changes steps 7 and 8 at most, through the verdict rows' own states (F13).
- Where the spec's table is ambiguous the reading chosen is the one that never claims more
  progress than the ledgers show; the cases are listed in `docs/contracts/journey.md`.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from claimstone import admissibility, decisions, operations_view
from claimstone.config import Project
from claimstone.operations import OperationError
from claimstone.store import LedgerCorrupt, Store

JOURNEY_VERSION = 1

STATUSES = ("done", "partial", "running", "waits_for_you", "blocked", "not_started",
            "not_applicable")

# The scheduler stage a running operation belongs to, as the journey names it. `extract-build`
# and `extract-drain` are the spec's; the build/harvest variants of the same lanes map to the
# same step because an operation of that lane is the work the step describes.
OPERATION_STAGE = {
    "discover": "discover", "acquire": "acquire", "normalize": "normalize",
    "extract-build": "extract", "extract-drain": "extract", "extract-harvest": "extract",
    "review-build": "review", "review-drain": "review", "review-harvest": "review",
    "synthesize": "synthesize",
}

DECISIONS_NOTE = "decisions belong to a bound flow"
OPERATIONS_NOTE = "operations ledger unreadable: nothing is shown as running"
DECISIONS_UNREADABLE_NOTE = "decisions ledger unreadable: the counts are unknown"

DASH = "—"


class _Fill(dict):
    """`str.format_map` source: None renders as "—", floats as two decimals."""

    def __missing__(self, key: str) -> str:  # a template naming an absent figure shows unknown
        return DASH

    def __getitem__(self, key: str) -> str:
        value = dict.get(self, key)
        if value is None:
            return DASH
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, float):
            return f"{value:.2f}"
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value) or DASH
        return str(value)


def sentence(template: str, figures: Mapping[str, Any]) -> str:
    return template.format_map(_Fill(figures))


def _step(n: int, key: str, title: str, actor: str, status: str, template: str,
          figures: dict[str, Any]) -> dict[str, Any]:
    assert status in STATUSES, status
    return {"n": n, "key": key, "title": title, "actor": actor, "status": status,
            "summary": sentence(template, figures), "figures": figures}


def _is_literature(row: Any) -> bool:
    return row.kind != "operational"


def _running_stages(running: list[dict[str, Any]] | None) -> set[str]:
    return {OPERATION_STAGE[item["stage"]] for item in running or []
            if item.get("stage") in OPERATION_STAGE}


def _stage(rs: Any, name: str) -> Any:
    return next(stage for stage in rs.stages if stage.name == name)


def _positive(value: int | None) -> bool:
    return bool(value)  # None and 0 are both "nothing recorded"


def questions_block(project: Project) -> dict[str, int]:
    operational = sum(1 for q in project.questions if q.kind == "operational")
    return {"total": len(project.questions),
            "literature": len(project.questions) - operational, "operational": operational}


def topics_block(project: Project) -> list[dict[str, Any]]:
    return [{"id": t.id, "label": t.label, "terms": list(t.terms)} for t in project.topics]


# --- the eight steps -----------------------------------------------------------------------


def _protocol(project: Project, flow_row: dict[str, Any] | None,
              binding: dict[str, Any] | None) -> dict[str, Any]:
    counts = questions_block(project)
    figures: dict[str, Any] = {
        "registry_version": project.registry_version,
        "questions_total": counts["total"], "questions_literature": counts["literature"],
        "questions_operational": counts["operational"],
        # The flow row's own field: `flows.create` stamps `created_at`.
        "bound_at": (flow_row or {}).get("created_at"),
        "drifted_parts": None,
    }
    if flow_row is None or binding is None:
        return _step(1, "protocol", "Protocol frozen", "you", "not_applicable",
                     "Protocol not verified: this is a historical round, not a bound flow.",
                     figures)
    if binding["state"] == "CURRENT":
        return _step(1, "protocol", "Protocol frozen", "you", "done",
                     "Protocol frozen at registry v{registry_version}: {questions_total} "
                     "questions ({questions_literature} literature, {questions_operational} "
                     "operational), bound {bound_at}.", figures)
    figures["drifted_parts"] = list(binding["differences"])
    return _step(1, "protocol", "Protocol frozen", "you", "blocked",
                 "The protocol has drifted from the one bound: {drifted_parts}.", figures)


def _search(rs: Any, admitted: dict[str, Any] | None, running: set[str]) -> dict[str, Any]:
    stage = _stage(rs, "discover")
    by_class = None if admitted is None else {
        name: bucket.get("found") for name, bucket in (admitted.get("by_class") or {}).items()}
    figures = {"candidates": stage.outputs, "per_class": by_class, "note": stage.detail}
    if "discover" in running:
        status, text = "running", "Searching: {candidates} candidates so far."
    elif not _positive(stage.outputs):
        status, text = "not_started", "No candidates found yet."
    elif admitted is None or "awaiting_discovery" in (admitted.get("blocking") or []):
        # An unreadable admission cannot show the queries all succeeded: never claim done.
        status, text = "partial", ("The search is incomplete: {candidates} candidates found, "
                                   "some queries failed or are unconfirmed.")
    else:
        status, text = "done", "{candidates} candidates found."
    return _step(2, "search", "Search the declared scope", "claimstone", status, text, figures)


def _copies(rs: Any, admitted: dict[str, Any] | None, running: set[str]) -> dict[str, Any]:
    a = admitted or {}
    found, obtained = a.get("found"), a.get("obtained")
    figures = {
        "confirmed": a.get("confirmed"), "found": found, "obtained": obtained,
        "rate": a.get("rate"), "floor": a.get("floor"), "status": a.get("status"),
        "not_obtained": (found - obtained) if found is not None and obtained is not None
        else None,
        "not_a_document": len(a["not_a_document"]) if "not_a_document" in a else None,
    }
    if "acquire" in running:
        status, text = "running", ("Obtaining copies: {confirmed} confirmed of {found} found "
                                   "so far.")
    elif not _positive(found):
        status, text = "not_started", "No copies sought yet: nothing was found."
    elif a.get("final") and a.get("status") == admissibility.OK:
        status, text = "done", ("{confirmed} of {found} found sources are confirmed documents "
                                "(rate {rate}, floor {floor}): the floor is met.")
    elif a.get("final") and a.get("status") == admissibility.INSUFFICIENT:
        status, text = "blocked", ("Below the acquisition floor: {confirmed} of {found} found "
                                   "sources are confirmed documents (rate {rate}, floor "
                                   "{floor}); no verdicts can be produced.")
    else:
        status, text = "partial", ("{confirmed} of {found} found sources are confirmed so far "
                                   "(rate {rate}, floor {floor}); {not_obtained} not obtained, "
                                   "and the round is not final.")
    return _step(3, "copies", "Obtain legal copies", "claimstone", status, text, figures)


def _documents(rs: Any, admitted: dict[str, Any] | None, running: set[str]) -> dict[str, Any]:
    stage = _stage(rs, "normalize")
    figures = {"documents": stage.outputs, "rejected": stage.rejected}
    blocking = (admitted or {}).get("blocking") or []
    if "normalize" in running:
        status, text = "running", "Preparing documents: {documents} ready so far."
    elif not _positive(stage.outputs):
        # Covers the table's "normalize and acquire outputs both nothing" and the case where
        # copies exist but none has been prepared: neither claims a prepared document.
        status, text = "not_started", "No documents prepared yet."
    elif admitted is None or "awaiting_normalize" in blocking:
        status, text = "partial", ("{documents} documents prepared, {rejected} rejected; "
                                   "obtained copies are still waiting to be prepared.")
    else:
        status, text = "done", "{documents} documents prepared, {rejected} rejected."
    return _step(4, "documents", "Prepare the documents", "claimstone", status, text, figures)


def _annotate(rs: Any, running: set[str]) -> dict[str, Any]:
    stage = _stage(rs, "extract")
    progress = stage.progress
    figures = {"readings_answered": progress.done if progress else None,
               "readings_expected": progress.total if progress else None,
               "annotations_kept": stage.outputs, "rejected": stage.rejected}
    if "extract" in running:
        status, text = "running", ("Annotating: {readings_answered} of {readings_expected} "
                                   "readings answered.")
    elif progress is None:
        status, text = "not_started", "No passage has been annotated yet."
    elif progress.total is not None and progress.done == progress.total:
        status, text = "done", ("All {readings_expected} readings answered; {annotations_kept} "
                                "annotations kept, {rejected} rejected.")
    else:
        status, text = "partial", ("{readings_answered} of {readings_expected} readings "
                                   "answered; {annotations_kept} annotations kept, "
                                   "{rejected} rejected.")
    return _step(5, "annotate", "Annotate every passage", "claimstone", status, text, figures)


def _review(rs: Any, running: set[str]) -> dict[str, Any]:
    stage = _stage(rs, "review")
    progress = stage.progress
    figures = {"reviewed": progress.done if progress else None,
               "accepted": progress.total if progress else None}
    if "review" in running:
        status, text = "running", "Reviewing: {reviewed} of {accepted} annotations reviewed."
    elif progress is None:
        status, text = "not_started", "No annotation has been reviewed yet."
    elif progress.total is not None and progress.done == progress.total:
        status, text = "done", "All {accepted} accepted annotations have an independent review."
    elif progress.done > 0:
        status, text = "partial", "{reviewed} of {accepted} accepted annotations reviewed."
    else:
        status, text = "not_started", "No annotation has been reviewed yet."
    return _step(6, "review", "Independent review", "claimstone", status, text, figures)


def _profiles(rs: Any, running: set[str]) -> dict[str, Any]:
    stage = _stage(rs, "synthesize")
    literature = [q for q in rs.questions if _is_literature(q)]
    # A literature question with no profile is not final either: calling the step done while a
    # question has no profile would claim more than the ledgers show.
    provisional = sum(1 for q in literature if q.provisional or not q.profile_sha256)
    final = sum(1 for q in literature if q.profile_sha256 and not q.provisional)
    figures: dict[str, Any] = {"profiles": stage.outputs, "provisional": None, "final": None}
    if rs.unavailable:
        figures["reason"] = rs.unavailable
        return _step(7, "profiles", "Evidence profiles", "claimstone", "blocked",
                     rs.unavailable, figures)
    if _positive(stage.outputs):
        figures["provisional"], figures["final"] = provisional, final
    if "synthesize" in running:
        status, text = "running", "Building evidence profiles: {profiles} so far."
    elif not _positive(stage.outputs):
        status, text = "not_started", "No evidence profile has been built yet."
    elif provisional:
        status, text = "partial", ("{profiles} profiles built: {final} final and {provisional} "
                                   "provisional literature questions.")
    else:
        status, text = "done", ("{profiles} profiles built: all {final} literature questions "
                                "are final.")
    return _step(7, "profiles", "Evidence profiles", "claimstone", status, text, figures)


def _sign(rs: Any, ready_to_sign: int) -> dict[str, Any]:
    literature = [q for q in rs.questions if _is_literature(q)]
    signed = sum(1 for q in literature if q.verdict and not q.verdict_stale)
    operational = len(rs.questions) - len(literature)
    figures = {"ready_to_sign": ready_to_sign, "signed": signed,
               "literature_total": len(literature), "operational": operational}
    if not literature:
        status, text = "not_applicable", ("This protocol has no literature question to sign; "
                                          "{operational} operational.")
    elif ready_to_sign > 0:
        status, text = "waits_for_you", ("{ready_to_sign} profiles are ready for you to read "
                                         "and sign; {signed} of {literature_total} literature "
                                         "questions signed.")
    elif signed == len(literature):
        status, text = "done", "All {literature_total} literature questions are signed."
    elif signed > 0:
        status, text = "partial", ("{signed} of {literature_total} literature questions "
                                   "signed; none is ready to sign right now.")
    else:
        status, text = "not_started", ("0 of {literature_total} literature questions signed; "
                                       "none is ready to sign right now.")
    return _step(8, "sign", "Read and sign", "you", status, text, figures)


# --- the two small reads ---------------------------------------------------------------------


def running_operations(store: Store, flow_row: dict[str, Any] | None
                       ) -> tuple[list[dict[str, Any]] | None, str | None]:
    """`operations_view.continuing()` restricted to this flow: authorized, running or
    interrupted operations. `[]` for a legacy selector; `None` and a named note when the
    operations ledger is damaged. `for_flow` is the same replay filtered by flow id (the
    summary row carries no flow id of its own), narrowed here to the continuing events."""
    if flow_row is None:
        return [], None
    try:
        rows = operations_view.for_flow(store, str(flow_row["flow_id"]))
    except (OperationError, LedgerCorrupt):
        return None, OPERATIONS_NOTE
    keep = [row for row in rows
            if row["last_event"] == "authorized" or row["last_event"] in operations_view.IN_FLIGHT]
    return [{"operation_id": row["operation_id"], "stage": row["stage"], "state": row["state"],
             "state_note": row["state_note"]} for row in keep], None


def needs_you(store: Store, selector: Any, flow_row: dict[str, Any] | None,
              ready_to_sign: int) -> dict[str, Any]:
    required: int | None = None
    optional: int | None = None
    note: str | None = DECISIONS_NOTE
    if flow_row is not None:
        note = None
        try:
            items = decisions.open_items(store, selector, str(flow_row["flow_id"]))
            required = sum(1 for item in items if item["required"])
            optional = len(items) - required
        except LedgerCorrupt:
            note = DECISIONS_UNREADABLE_NOTE
    return {"required": required, "optional": optional, "ready_to_sign": ready_to_sign,
            "note": note}


def build(project: Project, store: Store, selector: Any, flow_row: dict[str, Any] | None,
          computed: Any, cards: Iterable[Any], binding: dict[str, Any] | None
          ) -> dict[str, Any]:
    """The `journey` block. `computed` and `cards` are the ones the overview already built."""
    ready = sum(1 for card in cards if card.category == "ADJUDICATION")
    running, running_note = running_operations(store, flow_row)
    active = _running_stages(running)
    rs, admitted = computed.rs, computed.admitted
    return {
        "journey_version": JOURNEY_VERSION,
        "topics": topics_block(project),
        "questions": questions_block(project),
        "steps": [
            _protocol(project, flow_row, binding),
            _search(rs, admitted, active),
            _copies(rs, admitted, active),
            _documents(rs, admitted, active),
            _annotate(rs, active),
            _review(rs, active),
            _profiles(rs, active),
            _sign(rs, ready),
        ],
        "needs_you": needs_you(store, selector, flow_row, ready),
        "running": running,
        "running_note": running_note,
    }
