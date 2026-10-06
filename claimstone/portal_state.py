"""Pure state for the read-only research portal: ledgers in, plain dicts and dataclasses out.

No HTTP and no HTML live here, so every view is testable without a socket (spec §4.1). The
functions read the live project and the live ledgers on every call — there is deliberately no
cache — and every figure shown "for a selector" goes through `claimstone.scope` and the same
imported rules the CLI uses, so the portal can never be a second opinion the project never
asked for.

Ordering rule (review F13): inbox cards sort by `(CATEGORY_ORDER.index(category), subject)` and
by nothing else. The builders of the ACQUISITION, CLASSIFICATION and NORMALIZE cards take no
store and nothing derived from claims, reviews, stances or profiles, so intake can never be
ranked by expected result direction — the bias the acquisition floor cannot see. Test I-T3 pins
the signature.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import math
import os
import pathlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from claimstone import admissibility, claim_records, chunk_sets, flows, net, review, round_state, scope, synthesize
from claimstone.config import (ConfigError, Project, RegistryDrift, check_registry_drift,
                               discover_projects, load_project)
from claimstone.store import LedgerCorrupt, Store

# The F19 sentence, exact: HTTP 403 is a refusal, and the stored code's name asserts an
# inference the UI must never repeat as a fact.
PAYWALL_TEXT = ("HTTP 403 — access refused (stored as PAYWALL_403; not proof of a paywall "
                "or of a purchasable copy)")

ADVISORY_NOTE = "AI_PROVISIONAL: advisory only; changes no admission, denominator or reference (D79–D81)"
NEW_FLOW_NOTE = ("a protocol change is a new flow: `claimstone flow create ... "
                 "--derived-from <id> --relation supersedes`")
INTEGRITY_NOTE = "inspect by hand; never repair interior damage"
SIGN_NOTE = "a person reads the profile and signs; an agent does not"


def failure_display(failure_class: Any) -> str:
    """F19, one implementation for every view: the stored code beside a display text that
    asserts no inference the UI or the reader must not repeat as a fact."""
    text = str(failure_class or "")
    if text == "PAYWALL_403":
        return "HTTP 403 (access refused) [PAYWALL_403]"
    return text


def _attempt_display(attempt: Mapping[str, Any]) -> dict[str, Any]:
    """One attempt row for the API, with the failure class rendered display-ready (F19):
    the stored code's name asserts an inference the UI must never repeat as a fact, so the
    server says it once and the frontend renders `failure_display` verbatim (§4.2 rule 5)."""
    out = dict(attempt)
    out["failure_display"] = failure_display(attempt.get("failure_class"))
    return out

CATEGORY_ORDER = ("INTEGRITY", "PROTOCOL", "ACQUISITION", "CLASSIFICATION", "NORMALIZE",
                  "EXTRACT", "REVIEW", "ADJUDICATION", "ADVISORY")

SCREENING_LEDGER = "source_screening.jsonl"
IDENTITY_LEDGER = "source_identity.jsonl"


class NotFound(LookupError):
    """A path parameter that named nothing in the current ledgers. The transport answers 404."""


@dataclass(frozen=True)
class Card:
    category: str        # one of CATEGORY_ORDER
    scope: str           # "flow <id12>" or "legacy <round>" or "project"
    subject: str         # candidate_key, question id, ledger name, ...
    cause: str           # one sentence naming the rows
    command: str | None  # exact CLI text, or None
    note: str            # constraint the operator must know


def sort_cards(cards: Iterable[Card]) -> list[Card]:
    """The only ordering rule (F13): category order, then subject. Never urgency."""
    return sorted(cards, key=lambda card: (CATEGORY_ORDER.index(card.category), card.subject))


def _selector_of(flow_row: dict[str, Any] | None, selector: scope.Selector) -> scope.Selector:
    if flow_row is None:
        return selector
    held = (flow_row.get("binding") or {}).get("selector") or {}
    return scope.Selector(held.get("round"), bool(held.get("manifest_only")))


# A selector in a URL. `-` is the whole store (round None) and `~manifest` marks manifest_only;
# the slug is only ever *looked up* among the selectors that exist (`unbound_selectors`), never
# used to build a path.
WHOLE_STORE_SLUG = "-"
MANIFEST_SUFFIX = "~manifest"


def selector_slug(selector: scope.Selector) -> str:
    return (selector.round or WHOLE_STORE_SLUG) + (MANIFEST_SUFFIX if selector.manifest_only else "")


def selector_label(selector: scope.Selector) -> str:
    name = f"round {selector.round}" if selector.round else "whole store"
    return name + (" · manifest only" if selector.manifest_only else "")


def unbound_selectors(store: Store, flow_rows: Iterable[dict[str, Any]]) -> list[scope.Selector]:
    """Every selector with data that no flow binds: legacy, protocol not verified.

    `flows.legacy_selectors` lists candidate rounds only. A profile or a verdict can also be
    recorded under the whole-store selector or under `manifest_only` — `pmc-screen-time`'s eight
    current profiles, including Q04 awaiting a person, all carry `round: null` — and a portal
    that listed rounds alone would hide the one decision the project is waiting on.
    """
    rows = list(flow_rows)
    bound = {(((row.get("binding") or {}).get("selector") or {}).get("round"),
              bool(((row.get("binding") or {}).get("selector") or {}).get("manifest_only")))
             for row in rows}
    found: set[tuple[str | None, bool]] = {(sel.round, False)
                                           for sel in flows.legacy_selectors(store, rows)}
    if any(True for _ in store.read("candidates.jsonl")):
        found.add((None, False))
    for ledger in (synthesize.PROFILES, synthesize.ADJUDICATIONS):
        for row in store.read(ledger):
            found.add((row.get("round"), bool(row.get("manifest_only"))))
    return [scope.Selector(name, manifest)
            for name, manifest in sorted(found - bound,
                                         key=lambda item: (item[0] is not None, item[0] or "",
                                                           item[1]))]


def selector_from_slug(store: Store, flow_rows: Iterable[dict[str, Any]],
                       slug: str) -> scope.Selector:
    """The unbound selector a URL slug names, or NotFound. Never an invented round."""
    for selector in unbound_selectors(store, flow_rows):
        if selector_slug(selector) == slug:
            return selector
    raise NotFound(f"no unbound selector {slug!r}")


@dataclass
class Computed:
    """The expensive readings of one selector, computed once per request and shared.

    Measured on `pmc-screen-time` before this existed: one flow page ran `synthesize.verdicts`
    five times, `round_state.state` three times and `claim_records.current` sixteen times, 52 s
    under the profiler and 15 s plain. Every consumer below reads the same ledgers at the same
    moment, so computing once is the same answer, not a cache: nothing outlives the request.
    """

    rs: round_state.RoundState
    verdicts: dict[str, Any] | None
    verdict_error: BaseException | None
    admitted: dict[str, Any] | None
    collapsed: dict[str, dict[str, Any]] | None


def compute(project: Project, store: Store, selector: scope.Selector) -> Computed:
    verdict_result: dict[str, Any] | None = None
    verdict_error: BaseException | None = None
    try:
        verdict_result = synthesize.verdicts(store, project=project, round_name=selector.round,
                                             manifest_only=selector.manifest_only)
    except (synthesize.NotAdmissible, RegistryDrift, LedgerCorrupt) as exc:
        verdict_error = exc
    rs = round_state.state(project, store, round_name=selector.round,
                           manifest_only=selector.manifest_only,
                           precomputed_verdicts=verdict_result if verdict_error is None
                           else verdict_error)
    try:
        admitted = admissibility.admit(project, store, round_name=selector.round,
                                       manifest_only=selector.manifest_only)
        collapsed = admissibility.collapse(store)
    except LedgerCorrupt:
        admitted, collapsed = None, None
    return Computed(rs, verdict_result, verdict_error, admitted, collapsed)


def work_cards(project: Project, admitted: dict[str, Any] | None,
               scoped_candidates: dict[str, dict[str, Any]],
               collapsed_acquisitions: dict[str, dict[str, Any]],
               selector: scope.Selector) -> list[Card]:
    """ACQUISITION, CLASSIFICATION and NORMALIZE cards.

    Takes only these five arguments — no store, no claims, no reviews, no profiles (review F13):
    what is worth obtaining next must be a function of acquisition metadata alone. The scope
    label is filled in by the caller, which knows whether this selector belongs to a flow.
    """
    cards: list[Card] = []
    path = str(project.root)
    round_flag = f" --round {selector.round}" if selector.round else ""
    manifest_flag = " --manifest" if selector.manifest_only else ""

    for key, candidate in sorted(scoped_candidates.items()):
        row = collapsed_acquisitions.get(key)
        if row is not None and row.get("acquired"):
            continue
        subject = str(candidate.get("source_id") or key)
        failure = "NOT_ATTEMPTED" if row is None else str(row.get("failure_class") or "NOT_ATTEMPTED")
        if failure == "UNCLASSIFIED":
            # Not a fetch failure: acquire refused before any request. The CLASSIFICATION card
            # below is the remedy; offering `--retry-class UNCLASSIFIED` would be a wrong one.
            continue
        cause = PAYWALL_TEXT if failure == "PAYWALL_403" else f"acquisition failed: {failure}"
        if row is None or not net.is_terminal(failure):
            command = f"claimstone acquire {path}{round_flag}{manifest_flag} --dry-run"
            note = ("network requests: preview with --dry-run, then run without it only with the "
                    "operator's authorization for the sweep (AGENTS.md)")
        else:
            command = (f"claimstone acquire {path}{round_flag}{manifest_flag}"
                       f" --retry-class {failure} --campaign <campaign-name>")
            note = "terminal: retry only in a named campaign the operator authorizes (AGENTS.md)"
        cards.append(Card("ACQUISITION", "", subject, cause, command, note))

    for key, candidate in sorted(scoped_candidates.items()):
        if candidate.get("source_class"):
            continue
        subject = str(candidate.get("source_id") or key)
        cards.append(Card(
            "CLASSIFICATION", "", subject,
            "no source class recorded, and acquire refuses an unclassified candidate (invariant 6)",
            f"claimstone discover {path} --reclassify",
            "declare an assign_when rule in sources.yaml rather than loosening one"))

    awaiting = int((admitted or {}).get("awaiting_normalize") or 0)
    if awaiting:
        cards.append(Card(
            "NORMALIZE", "", "awaiting_normalize",
            f"{awaiting} obtained source(s) not yet examined by stage 3",
            f"./claimstone.sh normalize {path}",
            "runs in the container; the image is rebuilt first (D42)"))
    for identifier in sorted((admitted or {}).get("not_a_document") or []):
        cards.append(Card(
            "NORMALIZE", "", str(identifier),
            "obtained, and stage 3 read it as not a document",
            f"claimstone gate-audit {path} --show-rejected",
            "read the boundary cases by hand before touching a threshold"))
    return cards


def inbox_cards(project: Project, store: Store, selector: scope.Selector,
                flow_row: dict[str, Any] | None = None,
                computed: Computed | None = None) -> list[Card]:
    """Every open item for one selector, one card per actionable subject (spec §4.5)."""
    scope_label = (f"flow {str(flow_row['flow_id'])[:12]}" if flow_row is not None
                   else f"legacy {selector_label(selector)}")
    cards: list[Card] = []

    computed = computed or compute(project, store, selector)
    rs = computed.rs
    for error in rs.errors:
        cards.append(Card("INTEGRITY", scope_label, error.split(":", 1)[0], error, None,
                          INTEGRITY_NOTE))
    for ledger in sorted(store.torn_tail):
        cards.append(Card("INTEGRITY", scope_label, ledger,
                          f"{ledger} ends in a half-written row the reader skipped", None,
                          INTEGRITY_NOTE))
    repairs = list(store.read("ledger_repairs.jsonl"))
    if repairs:
        cards.append(Card(
            "INTEGRITY", scope_label, "ledger_repairs.jsonl",
            f"{len(repairs)} torn-tail repair(s) recorded in this project",
            None,
            "a repair makes every round non-final; admission reads this ledger project-wide (F1)"))

    if flow_row is not None:
        binding = flows.binding_state(project, store, flow_row)
        if binding["state"] != "CURRENT":
            cards.append(Card(
                "PROTOCOL", scope_label, str(flow_row["flow_id"])[:12],
                f"binding {binding['state']}: differs in {', '.join(binding['differences'])}",
                None, NEW_FLOW_NOTE))

    admitted = computed.admitted
    orphans = (admitted or {}).get("orphan_acquisitions") or []
    if orphans:
        cards.append(Card(
            "INTEGRITY", scope_label, "orphan_acquisitions",
            f"{len(orphans)} acquisition row(s) whose candidate is absent",
            f"claimstone report {project.root}",
            "the ledger is inconsistent; the count is reported, never folded into found"))

    scoped_candidates = scope.candidates(store, selector)
    collapsed = computed.collapsed
    if collapsed is not None and admitted is not None:
        for card in work_cards(project, admitted, scoped_candidates, collapsed, selector):
            cards.append(dataclasses.replace(card, scope=scope_label))

    verdict_rows: list[dict[str, Any]] = (computed.verdicts or {}).get("rows") or []
    if isinstance(computed.verdict_error, RegistryDrift):
        cards.append(Card("PROTOCOL", scope_label, "registry", str(computed.verdict_error),
                          None, NEW_FLOW_NOTE))

    from claimstone import evidence

    for row in verdict_rows:
        if row["unavailable"]:
            continue  # inadmissible: no profile is live, and none of these cards apply
        profile = row["profile"]
        question_id = str(profile.get("question_id"))
        completion = profile.get("extraction") or {}
        open_readings = {name: int(completion.get(name) or 0)
                         for name in ("unanswered", "unharvested", "unregated")
                         if int(completion.get(name) or 0) > 0}
        if open_readings:
            detail = ", ".join(f"{n} {name}" for name, n in sorted(open_readings.items()))
            cards.append(Card(
                "EXTRACT", scope_label, question_id,
                f"{profile.get('kind') or 'question'}: {detail} reading(s) open",
                None,
                "see docs/GUIDE.md, stage 4; extraction is not round-scoped and builds work "
                "for the whole project (review F7)"))
        awaiting_review = int(profile.get("awaiting_review") or 0)
        if awaiting_review:
            cards.append(Card(
                "REVIEW", scope_label, question_id,
                f"{awaiting_review} claim(s) awaiting review",
                None,
                "see docs/GUIDE.md, stage 5; review is not round-scoped and builds work for "
                "the whole project (review F7)"))
        card = adjudication_card(project, selector, row, scope_label)
        if card is not None:
            cards.append(card)

    scoped_keys = set(scoped_candidates)
    for ledger, label in ((SCREENING_LEDGER, "screening"), (IDENTITY_LEDGER, "identity")):
        rows = {key: row for key, row in store.latest_by(ledger, "candidate_key").items()
                if key in scoped_keys}
        if not rows:
            continue
        counts: dict[str, int] = {}
        for row in rows.values():
            role = str(row.get("role") or row.get("related_kind") or "-")
            status = str(row.get("assessment_status") or "-")
            counts[f"{role} {status}"] = counts.get(f"{role} {status}", 0) + 1
        cause = f"{len(rows)} {label} row(s) in scope: " + ", ".join(
            f"{name} {count}" for name, count in sorted(counts.items()))
        cards.append(Card("ADVISORY", scope_label, label, cause, None, ADVISORY_NOTE))

    return sort_cards(cards)



def adjudication_card(project: Project, selector: scope.Selector, row: dict[str, Any],
                      scope_label: str) -> Card | None:
    """The one place the next signing action is decided, for the inbox and the question page.

    None when nothing can be signed: an inadmissible round, a provisional or operational
    profile, or a verdict that is recorded and current. A stale *stored* profile gets
    `synthesize` first, because `adjudicate` refuses it (StaleProfile). A view that built this
    command itself would drift from these rules — the S5 question page did exactly that.
    """
    from claimstone import evidence

    if row.get("unavailable"):
        return None
    profile = row["profile"]
    question_id = str(profile.get("question_id"))
    if profile.get("provisional") or profile.get("state") == evidence.NOT_APPLICABLE:
        return None
    if row["verdict"] and not row["stale"]:
        return None
    reason = ("no verdict recorded" if not row["verdict"]
              else "verdict stale: the evidence moved under the signature")
    round_flag = f" --round {selector.round}" if selector.round else ""
    manifest_flag = " --manifest-only" if selector.manifest_only else ""
    if row.get("stored_profile_stale"):
        # `adjudicate` signs the *stored* profile and refuses when it differs from current
        # evidence (synthesize.adjudicate → StaleProfile). The next valid action is a rebuild
        # and a fresh reading, not a signature against a hash the engine will refuse.
        command = f"claimstone synthesize {project.root}{round_flag}{manifest_flag}"
        reason += "; the stored profile differs from current evidence"
        note = "rebuild the profile, read it again, then sign against the new hash"
    else:
        command = (f"claimstone adjudicate {project.root} {question_id}{round_flag}"
                   f"{manifest_flag} --profile-sha256 {profile.get('profile_sha256')}"
                   f" --verdict <ONE_OF_FIVE> --rationale-file <file> --by <name>")
        note = SIGN_NOTE
    return Card("ADJUDICATION", scope_label, question_id, reason, command, note)


def floor_panel(admitted: dict[str, Any] | None) -> dict[str, Any] | None:
    """The floor and the deficit arithmetic, from `admit()` only (spec §4.6).

    No simulator and no hypothetical rates: the sentence says how many more confirmations a
    class would need, and that this says nothing about which are obtainable — because
    "download until it clears" is the move the floor exists to refuse.
    """
    if not admitted:
        return None
    overall = {
        "basis": admitted.get("basis"),
        "basis_count": admitted.get(admitted.get("basis") or ""),
        "found": admitted.get("found"), "rate": admitted.get("rate"),
        "floor": admitted.get("floor"), "floor_version": admitted.get("floor_version"),
        "floor_set_at": admitted.get("floor_set_at"), "status": admitted.get("status"),
        "final": admitted.get("final"), "blocking": admitted.get("blocking"),
    }
    classes: dict[str, dict[str, Any]] = {}
    sentences: list[str] = []
    for name, bucket in (admitted.get("by_class") or {}).items():
        basis = str(bucket.get("basis") or "obtained")
        basis_count = int(bucket.get(basis) or 0)
        found = int(bucket.get("found") or 0)
        floor = bucket.get("floor")
        needed = max(0, math.ceil(floor * found - 1e-9) - basis_count) if floor and found else 0
        classes[name] = {"found": found, "basis": basis, "basis_count": basis_count,
                         "awaiting_normalize": bucket.get("awaiting_normalize"),
                         "floor": floor, "meets_floor": bucket.get("meets_floor"),
                         "needed": needed}
        if needed > 0:
            sentences.append(
                f"{name}: {needed} more of the {found - basis_count} not yet confirmed would be "
                f"needed to reach its floor. This says nothing about which are obtainable, and "
                f"selecting them by expected result is not allowed.")
    return {
        "overall": overall, "by_class": classes, "sentences": sentences,
        "disclosure": ("Admission currently reads document confirmations and ledger repairs "
                       "across the whole project (review F1). A round with no normalized "
                       "documents may show the confirmed basis because another round has "
                       "documents."),
    }


def integrity(project_path: pathlib.Path | str, store: Store, *,
              code_revision: str | None = None, code_dirty: bool | None = None) -> dict[str, Any]:
    """One place to see whether the numbers can be trusted right now (spec §4.7)."""
    from claimstone import grobid

    config: dict[str, Any] = {"state": "OK", "error": None}
    project: Project | None = None
    try:
        project = load_project(project_path)
    except ConfigError as exc:
        config = {"state": "ConfigError", "error": str(exc)}

    registry: dict[str, Any] = {"state": "OK", "error": None}
    if project is not None:
        try:
            check_registry_drift(project, store, record=False)
        except RegistryDrift as exc:
            registry = {"state": "RegistryDrift", "error": str(exc)}

    ledgers: dict[str, dict[str, Any]] = {}
    if store.root.is_dir():
        for path in sorted(store.root.glob("*.jsonl")):
            name = path.name
            rows, error, torn = 0, None, False
            try:
                for _row in store.read(name):
                    rows += 1
                torn = name in store.torn_tail
            except LedgerCorrupt as exc:
                error = str(exc)
            ledgers[name] = {"rows": rows, "torn_tail": torn, "error": error}

    orphans: int | None = None
    if project is not None:
        try:
            orphans = len(admissibility.admit(project, store)["orphan_acquisitions"] or [])
        except LedgerCorrupt:
            orphans = None

    if code_revision is None and code_dirty is None:
        code_revision, code_dirty = flows._code_identity(pathlib.Path(project_path))

    try:
        invalid = flows.invalid_flows(store)
    except LedgerCorrupt:
        invalid = []  # already named in `ledgers` above
    return {
        "config": config,
        "registry": registry,
        "ledgers": ledgers,
        "invalid_flows": invalid,
        "ledger_repairs": sum(1 for _ in store.read("ledger_repairs.jsonl")),
        "orphans": orphans,
        "instruments": instrument_check(),
        "code": {"revision": code_revision, "dirty": code_dirty, "grobid_image": grobid.IMAGE},
    }


_INSTRUMENT_CHECKER = None


def _checker_path() -> pathlib.Path | None:
    """Where `tools/check_instrument_versions.py` is. The repository checkout first, then
    `CLAIMSTONE_ROOT` and the working directory: inside the image the package is installed into
    site-packages, so the path next to `__file__` does not exist there."""
    candidates = [pathlib.Path(__file__).resolve().parent.parent]
    if os.environ.get("CLAIMSTONE_ROOT"):
        candidates.append(pathlib.Path(os.environ["CLAIMSTONE_ROOT"]))
    candidates.append(pathlib.Path.cwd())
    for root in candidates:
        path = root / "tools" / "check_instrument_versions.py"
        if path.is_file() and (root / "docs" / "DESIGN_DECISIONS.md").is_file():
            return path
    return None


def _load_instrument_checker():
    global _INSTRUMENT_CHECKER
    if _INSTRUMENT_CHECKER is None:
        path = _checker_path()
        if path is None:
            return None
        spec = importlib.util.spec_from_file_location("claimstone._instrument_check", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        _INSTRUMENT_CHECKER = module
    return _INSTRUMENT_CHECKER


def instrument_check() -> list[str]:
    """The design-record acknowledgement check, as a list of problems. Empty means OK.

    A checker that cannot be found is a named problem, never an empty (passing) list."""
    module = _load_instrument_checker()
    if module is None:
        return ["UNAVAILABLE: tools/check_instrument_versions.py and docs/DESIGN_DECISIONS.md "
                "not found (set CLAIMSTONE_ROOT); the instruments are unchecked, not OK"]
    return list(module.check())


def instrument_versions() -> dict[str, Any]:
    """The instrument constants the admin page lists, read with the checker's own helpers."""
    from claimstone import export

    module = _load_instrument_checker()
    out: dict[str, Any] = {}
    if module is not None:
        root = pathlib.Path(module.__file__).resolve().parent.parent
        for relative, constant, phrase in module.INSTRUMENTS:
            value = module.declared(root / relative, constant)
            if value is not None:
                out[phrase] = value
        for relative, constant in module.PARSERS:
            value = module.declared_string(root / relative, constant)
            if value is not None:
                out[constant.lower()] = value
    out["scope_version"] = scope.SCOPE_VERSION
    out["flow_version"] = flows.FLOW_VERSION
    out["export_version"] = export.EXPORT_VERSION
    return out


def admin_state(root: pathlib.Path | str) -> dict[str, Any]:
    """Presence of credentials, configured backends, instrument versions (spec §4.8).

    A name is `set` if the environment holds a non-empty value or `.env` in the repository root
    declares one. The value itself is never stored, returned or rendered — presence only.
    """
    from claimstone import cli
    from claimstone import runners

    names = ("CLAIMSTONE_CONTACT_EMAIL", "OLLAMA_API_KEY", "OPENALEX_API_KEY")
    dotenv: dict[str, str] = {}
    env_file = pathlib.Path(root) / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, _, value = stripped.partition("=")
            dotenv[name.strip()] = value.strip()
    credentials = {name: bool(os.environ.get(name)) or bool(dotenv.get(name))
                   for name in names}
    return {
        "credentials": credentials,
        "backends": {"configured": list(cli.BACKENDS),
                     "available": sorted(runners.available())},
        "backends_note": ("configured names; not health-checked. A health probe would be a "
                          "request and is never a side effect of GET."),
        "instruments": instrument_versions(),
        "key_rotation_note": ("Key rotation is done by editing `.env` outside the portal. "
                              "Containers read `.env` when `./claimstone.sh` starts them."),
    }


def question_matrix(project: Project, store: Store, selector: scope.Selector,
                    computed: Computed | None = None) -> dict[str, Any]:
    """One row per registry question, in registry order (spec §4.9)."""
    computed = computed or compute(project, store, selector)
    rs = computed.rs
    verdict_rows = (computed.verdicts or {}).get("rows") or []
    by_id = {str(row["profile"].get("question_id")): row for row in verdict_rows}

    from claimstone import evidence

    rows: list[dict[str, Any]] = []
    for question in rs.questions:  # registry order, always
        row = by_id.get(question.id)
        profile = (row or {}).get("profile") or {}
        gate_rejected = profile.get("gate_rejected") or {}
        rows.append({
            "id": question.id, "kind": question.kind, "text": question.text,
            # Per class before the aggregate (invariant 6): a pooled count that hides one class
            # sitting at zero is a different fact from a uniform one.
            "claims_by_class": dict(question.claims_by_class),
            "claims": question.claims,
            "coverage": {"sources": question.coverage_sources,
                         "examined": question.coverage_examined},
            "direction_count": dict(profile.get("direction_count") or {}),
            "direction_count_note": "a count, not a strength",
            "gate_rejected_total": sum(gate_rejected.values()) if gate_rejected else 0,
            "gate_rejected": dict(gate_rejected),
            "awaiting_review": profile.get("awaiting_review") or 0,
            "state": question.state,
            "provisional": question.provisional,
            "blocking": list(question.blocking),
            "verdict": question.verdict,
            "verdict_stale": question.verdict_stale,
            "profile_sha256": question.profile_sha256,
            "extraction": question.extraction,
            "unavailable": (row or {}).get("unavailable", ""),
            "stored_profile_stale": bool((row or {}).get("stored_profile_stale")),
            "operational_not_applicable": question.kind == "operational",
            "note": (None if question.state != evidence.NOT_APPLICABLE else
                     "kind operational: no verdict, never a sixth state"),
        })
    return {"rows": rows, "round": selector.round, "project": project.name}


# §8.3: the seven displayed question states of the React overview's DonutChart. Counted with
# the matrix's own precedence — the verdict cell first (the operational branch, then the
# recorded verdict with its staleness, then the engine's own NO_VERIFIED_CLAIM), then the two
# annotations that can carry an unsigned row (historical before provisional, as
# `synthesize.verdicts`'s awaiting count excludes an unavailable round before it inspects
# provisional), and the residual is the fresh profile that waits for a person.
QUESTION_STATES = ("signed", "stale", "awaiting_a_person", "provisional", "no_verified_claim",
                   "not_applicable", "historical")


def question_state_counts(matrix: dict[str, Any]) -> dict[str, int]:
    """§8.3: one count per displayed state, over the matrix rows the same page already built —
    no ledger read of its own, so the donut can never disagree with the table it sits beside
    (and the client counts nothing, F11)."""
    from claimstone import evidence

    counts = dict.fromkeys(QUESTION_STATES, 0)
    for row in matrix["rows"]:
        if row.get("operational_not_applicable"):
            state = "not_applicable"
        elif row.get("verdict") and row.get("verdict_stale"):
            state = "stale"
        elif row.get("verdict"):
            state = "signed"
        elif row.get("state") == evidence.NO_VERIFIED_CLAIM:
            state = "no_verified_claim"
        elif row.get("unavailable"):
            state = "historical"
        elif row.get("provisional"):
            state = "provisional"
        else:
            state = "awaiting_a_person"
        counts[state] += 1
    return counts


# §8.3: one tracker state per scoped candidate — `admissibility.rate`'s own branches, the same
# words its five-state accounting uses, so the Tracker can never split a population the floor
# panel judges.
TRACKER_STATES = ("confirmed", "awaiting_normalize", "not_a_document", "refused",
                  "not_attempted", "unclassified")


def _tracker_tooltip(state: str, row: Mapping[str, Any] | None) -> str:
    """The Tracker tooltip, decided server-side and rendered verbatim (§4.2 rule 5). A refusal
    follows F19 — the stored class asserts an inference the reader must not repeat as a fact,
    and an HTTP 403 in particular is not proof of a paywall."""
    if state == "confirmed":
        return "obtained and confirmed as a document by normalize"
    if state == "awaiting_normalize":
        return "obtained; normalize has not confirmed a document yet"
    if state == "not_a_document":
        return "obtained, but normalize rejected it: not a document"
    if state == "not_attempted":
        return "no acquisition attempt recorded"
    if state == "unclassified":
        return "acquire refused it: the candidate carries no source class"
    if (row or {}).get("failure_class") == "PAYWALL_403":
        return PAYWALL_TEXT
    return failure_display((row or {}).get("failure_class"))


def source_tracker(project: Project, store: Store, selector: scope.Selector,
                   computed: Computed | None = None) -> list[dict[str, Any]]:
    """§8.3: one Tracker entry per scoped candidate, in scoped candidate order, each with its
    state and a display-ready tooltip — the client derives nothing (F11).

    The states are read off the one `compute()` the page already ran: `collapse`'s per-key rows
    arrive in `computed`, so the acquisitions ledger is not walked twice, and the branches are
    `admissibility.rate`'s own (acquired → confirmed / awaiting / not-a-document by
    `documents.jsonl`; else the recorded failure class, UNCLASSIFIED named as itself). A
    damaged acquisitions ledger raises — the API's LEDGER_CORRUPT envelope is the single error
    channel (the S2-era decision); a tracker built without the collapse rows would call every
    refused source "not attempted", which is worse than no tracker.
    """
    from claimstone import admissibility

    if computed is None:
        computed = compute(project, store, selector)
    if computed.collapsed is None:
        # `compute` swallowed the damage it found there; name it again rather than guess states.
        raise LedgerCorrupt("acquisitions ledger unreadable: the tracker cannot be built")
    candidates = scope.candidates(store, selector)
    confirmed_rows = admissibility.confirmations(store)
    entries: list[dict[str, Any]] = []
    for key, candidate in candidates.items():
        row = computed.collapsed.get(key)
        if row is not None and row.get("acquired"):
            held = confirmed_rows.get(str(row.get("source_id") or key))
            if held is None:
                state = "awaiting_normalize"
            elif held.get("fulltext_confirmed"):
                state = "confirmed"
            else:
                state = "not_a_document"
        else:
            # `rate`'s own word for an unclassed failed row is NOT_ATTEMPTED (its failures
            # histogram), so the tracker never invents a refusal the ledger did not name.
            failure = str((row or {}).get("failure_class") or "")
            if failure == "UNCLASSIFIED":
                state = "unclassified"
            elif failure:
                state = "refused"
            else:
                state = "not_attempted"
        entries.append({
            "candidate_key": str(key),
            "source_id": candidate.get("source_id"),
            "source_class": str(candidate.get("source_class") or "UNCLASSIFIED"),
            "state": state,
            "tooltip": _tracker_tooltip(state, row),
        })
    return entries


def flow_overview(project: Project, store: Store, selector: scope.Selector,
                  flow_row: dict[str, Any] | None = None) -> dict[str, Any]:
    """Everything the flow page shows: binding banner, scoped stage strip, floor panel,
    question matrix, this scope's inbox, scoped activity."""
    computed = compute(project, store, selector)
    rs = computed.rs
    binding = flows.binding_state(project, store, flow_row) if flow_row is not None else None
    matrix = question_matrix(project, store, selector, computed)
    return {
        "project": project.name,
        "selector": selector.as_dict(),
        "selector_label": selector_label(selector),
        "flow": flow_row,
        "legacy": flow_row is None,
        "binding_state": binding,
        "state": rs.as_dict(),
        "floor_panel": floor_panel(computed.admitted),
        "questions": matrix,
        "question_state_counts": question_state_counts(matrix),
        "source_tracker": source_tracker(project, store, selector, computed),
        "inbox": [dataclasses.asdict(card)
                  for card in inbox_cards(project, store, selector, flow_row, computed)],
        "activity": round_state.activity(store, 50, selector),
        "unavailable": rs.unavailable,
        "errors": list(rs.errors),
    }


def question_detail(project: Project, store: Store, selector: scope.Selector,
                    question_id: str) -> dict[str, Any]:
    """One question's profile, its results with claim links, and any recorded verdict (§4.4)."""
    from claimstone import evidence

    if question_id not in project.question_ids:
        raise NotFound(f"unknown question id: {question_id}")
    try:
        rows = synthesize.verdicts(store, project=project, round_name=selector.round,
                                   manifest_only=selector.manifest_only)["rows"]
    except (synthesize.NotAdmissible, RegistryDrift, LedgerCorrupt):
        rows = []
    row = next((r for r in rows if str(r["profile"].get("question_id")) == question_id), None)
    card = (adjudication_card(project, selector, row, selector_label(selector))
            if row is not None else None)
    profile = (row or {}).get("profile") or {}
    question = next(q for q in project.questions if q.id == question_id)
    return {
        "project": project.name, "selector": selector.as_dict(), "id": question_id,
        "kind": question.kind, "text": question.text,
        "profile": profile,
        "profile_fields": {
            "state": profile.get("state"),
            "provisional": profile.get("provisional"),
            "blocking": profile.get("blocking") or [],
            "coverage": profile.get("coverage") or {},
            "direction_count": profile.get("direction_count") or {},
            "direction_count_note": "a count, not a strength",
            "gate_rejected": profile.get("gate_rejected") or {},
            "reviewed_not_usable": profile.get("reviewed_not_usable") or {},
            "awaiting_review": profile.get("awaiting_review") or 0,
            "linkage": profile.get("linkage"),
            "extraction": profile.get("extraction") or {},
            "profile_sha256": profile.get("profile_sha256"),
            "stored_profile_stale": bool((row or {}).get("stored_profile_stale")),
            "unavailable": (row or {}).get("unavailable", ""),
        },
        "results": profile.get("results") or [],
        "verdict": (row or {}).get("verdict"),
        "verdict_stale": bool((row or {}).get("stale")),
        # The same card the inbox shows, decided on the server: the page renders it verbatim.
        "adjudication_card": None if card is None else dataclasses.asdict(card),
        "operational_not_applicable": question.kind == "operational",
        "not_applicable_state": evidence.NOT_APPLICABLE if question.kind == "operational" else None,
    }


def lineage(project: Project, store: Store, selector: scope.Selector,
            claim_id: str) -> dict[str, Any]:
    """Invariant 1, end to end: claim → review → chunk → document → acquisition → candidate.

    A missing step is None and the remaining steps still render. The quote is rechecked against
    the current chunk text here (`quote_found`), because the check is the point of the page.
    """
    from claimstone import grobid

    claims, _ = claim_records.current(store)
    claim = claims.get(str(claim_id))
    sources = scope.source_ids(store, selector)
    if claim is None or str(claim.get("source_id")) not in sources:
        raise NotFound(f"claim {claim_id} is not in this scope")
    source_id = str(claim.get("source_id"))

    review_row = review.current(store).get(str(claim_id))

    chunk_id = claim.get("chunk_id")
    chunk = chunk_sets.current(store).get(str(chunk_id)) if chunk_id else None
    quote = str(claim.get("evidence_quote") or "")
    chunk_step = None
    if chunk is not None:
        chunk_step = {
            "chunk_id": str(chunk_id),
            "generation_sha256": chunk.get("generation_sha256"),
            "text_sha256": chunk.get("text_sha256"),
            "text": chunk.get("text"),
            "evidence_quote": quote,
            # Recheck in the view: the gate checked it at harvest time, on the text it had then.
            "quote_found": quote in str(chunk.get("text") or ""),
        }

    document = store.latest_by("documents.jsonl", "source_id").get(source_id)

    scoped = scope.candidates(store, selector)
    key = next((k for k, row in scoped.items()
                if str(row.get("source_id") or k) == source_id), None)
    acquisition = admissibility.collapse(store).get(key) if key is not None else None
    if acquisition is not None:
        # F19: each attempt carries its display-ready failure class; the UI renders it verbatim.
        acquisition = {**acquisition,
                       "attempts": [_attempt_display(a) for a in acquisition.get("attempts") or []]}

    return {
        "project": project.name, "selector": selector.as_dict(),
        "claim_id": str(claim_id), "source_id": source_id,
        "steps": {
            "claim": {name: claim.get(name) for name in (
                "claim", "stance", "question_id", "evidence_quote", "claim_gate_version",
                "gate_revision", "backend", "model", "harness_version", "call_id",
                "source_class")},
            "review": review_row,
            "chunk": chunk_step,
            "document": document,
            "document_pdf_instrument": (grobid.IMAGE
                                        if document is not None and document.get("format") == "pdf"
                                        else None),
            "acquisition": acquisition,
            "acquisition_candidate_key": key,
            "candidate": scoped.get(key) if key is not None else None,
        },
    }


def source_dossier(project: Project, store: Store, selector: scope.Selector,
                   candidate_key: str) -> dict[str, Any]:
    """One candidate's whole trail: every acquisition row (not just the counted one), the
    document, the active chunks, advisory rows and the claim count per question (§4.11)."""
    scoped = scope.candidates(store, selector)
    candidate = scoped.get(str(candidate_key))
    if candidate is None:
        raise NotFound(f"candidate {candidate_key} is not in this scope")
    source_id = str(candidate.get("source_id") or candidate_key)

    every_row = [row for row in store.read("acquisitions.jsonl")
                 if str(row.get("candidate_key")) == str(candidate_key)]
    # F19: display-ready failure classes on every attempt of every row, and on the counted one.
    every_row = [{**row, "attempts": [_attempt_display(a) for a in row.get("attempts") or []]}
                 for row in every_row]
    counted = admissibility.collapse(store).get(str(candidate_key))
    if counted is not None:
        counted = {**counted,
                   "attempts": [_attempt_display(a) for a in counted.get("attempts") or []]}

    document = store.latest_by("documents.jsonl", "source_id").get(source_id)
    try:
        active_chunks = sum(1 for row in chunk_sets.current(store).values()
                            if str(row.get("source_id")) == source_id)
    except ValueError:
        active_chunks = None

    advisory = {}
    for ledger in (SCREENING_LEDGER, IDENTITY_LEDGER):
        rows = {key: row for key, row in store.latest_by(ledger, "candidate_key").items()
                if key == str(candidate_key)}
        advisory[ledger] = list(rows.values())

    claims, _ = claim_records.current(store)
    by_question: dict[str, int] = {}
    for row in claims.values():
        if str(row.get("source_id")) == source_id:
            qid = str(row.get("question_id"))
            by_question[qid] = by_question.get(qid, 0) + 1

    return {
        "project": project.name, "selector": selector.as_dict(),
        "candidate_key": str(candidate_key), "source_id": source_id,
        "candidate": candidate,
        "acquisitions": every_row,
        "counted_acquisition": counted,   # the collapsed one: labelled "counted"
        "document": document,
        "active_chunks": active_chunks,
        "advisory": advisory,
        "advisory_note": ADVISORY_NOTE,
        "claims_by_question": dict(sorted(by_question.items())),
    }


def index(projects_dir: pathlib.Path | str, store_dir: pathlib.Path | str) -> dict[str, Any]:
    """One card per project: config, registry, flows with their binding states, legacies, and
    the open inbox count by category (spec §4.4)."""
    projects: list[dict[str, Any]] = []
    for root in discover_projects(projects_dir):
        card: dict[str, Any] = {"name": root.name, "config": "OK", "config_error": None}
        try:
            project = load_project(root)
        except ConfigError as exc:
            card.update(config="ConfigError", config_error=str(exc))
            projects.append(card)
            continue
        store = Store(root.name, base=store_dir)

        registry_state = None
        try:
            check_registry_drift(project, store, record=False)
        except RegistryDrift as exc:
            registry_state = str(exc)
        card["registry_version"] = project.registry_version
        card["registry_sha256"] = project.registry_sha256[:12]
        card["registry_drift"] = registry_state

        try:
            flow_rows = flows.flows(store)
            unbound = unbound_selectors(store, flow_rows.values())
        except LedgerCorrupt as exc:
            card.update(flows=[], legacy=[], legacy_note="legacy: protocol not verified",
                        inbox_counts={"INTEGRITY": 1}, integrity_error=f"LEDGER_CORRUPT: {exc}")
            projects.append(card)
            continue

        def summary(selector: scope.Selector, computed: Computed) -> dict[str, Any]:
            result = computed.verdicts
            return {
                "floor_status": (computed.admitted or {}).get("status"),
                "verdicts": None if result is None else {
                    "adjudicated": result["adjudicated"], "stale": result["stale"],
                    "awaiting_adjudication": result["awaiting_adjudication"]},
            }

        counts: dict[str, int] = {}
        flow_entries: list[dict[str, Any]] = []
        legacy_entries: list[dict[str, Any]] = []
        try:
            for flow_id, row in sorted(flow_rows.items()):
                selector = _selector_of(row, scope.Selector(None))
                computed = compute(project, store, selector)
                binding = flows.binding_state(project, store, row)
                flow_entries.append({
                    "flow_id": flow_id, "title": row.get("title"),
                    "selector": selector.as_dict(), "selector_label": selector_label(selector),
                    "binding_state": binding["state"],
                    "binding_differences": binding["differences"],
                    "bound_after_data": bool(row.get("bound_after_data")),
                    **summary(selector, computed),
                })
                for item in inbox_cards(project, store, selector, row, computed):
                    counts[item.category] = counts.get(item.category, 0) + 1
            for selector in unbound:
                computed = compute(project, store, selector)
                legacy_entries.append({
                    "slug": selector_slug(selector), "label": selector_label(selector),
                    "selector": selector.as_dict(), **summary(selector, computed)})
                for item in inbox_cards(project, store, selector, None, computed):
                    counts[item.category] = counts.get(item.category, 0) + 1
        except LedgerCorrupt as exc:
            counts["INTEGRITY"] = counts.get("INTEGRITY", 0) + 1
            card["integrity_error"] = f"LEDGER_CORRUPT: {exc}"
        card["flows"] = flow_entries
        # Kept for the round-name readers; `legacy_selectors` carries every unbound selector.
        card["legacy"] = [entry["selector"]["round"] for entry in legacy_entries
                          if entry["selector"]["round"] and not entry["selector"]["manifest_only"]]
        card["legacy_selectors"] = legacy_entries
        card["legacy_note"] = "legacy: protocol not verified"
        card["inbox_counts"] = {
            name: counts.get(name, 0) for name in CATEGORY_ORDER if counts.get(name)}
        projects.append(card)
    return {"projects": projects}
