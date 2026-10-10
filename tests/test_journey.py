"""journey: the guided page's eight steps, decided on the server (portal journey spec, J1).

Each status rule is exercised on the workspace `test_portal_state` builds, plus small appended
rows; the stage-only rules (annotate, review, profiles, sign) are exercised on hand-built
`StageState`s, because the real rows that would produce them need a model backend.
"""

from __future__ import annotations

import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from claimstone import flows, journey, operations, portal_state, round_state, scope
from claimstone.round_state import Progress, StageState
from claimstone.store import Store
from tests.test_api import _get_json, _served
from tests.test_operations import _fixture
from tests.test_portal_state import build_workspace

STEP_KEYS = ["protocol", "search", "copies", "documents", "annotate", "review", "profiles", "sign"]


def _overview(project, store, round_name="r1"):
    selector = scope.Selector(round_name)
    flow_row = next((row for row in flows.flows(store).values()
                     if (row["binding"]["selector"] or {}).get("round") == round_name), None)
    return portal_state.flow_overview(project, store, selector, flow_row)


def _by_key(overview):
    return {step["key"]: step for step in overview["journey"]["steps"]}


def _statuses(overview):
    return [step["status"] for step in overview["journey"]["steps"]]


def _candidate(store, key, source_id=None, round_name="r1"):
    row = {"candidate_key": key, "round": round_name, "channel": "keyword",
           "source_class": "ACA", "title": key, "url": f"https://example.org/{key}.pdf",
           "discovered_at": "2026-10-03T10:00:00+00:00"}
    if source_id:
        row["source_id"] = source_id
    store.append("candidates.jsonl", row)


def _stage(name, **kwargs):
    base = dict(name=name, implemented=True, inputs=None, outputs=None, rejected=None,
                progress=None, last_write=None)
    base.update(kwargs)
    return StageState(**base)


def _rs(stages, questions=(), unavailable=""):
    return SimpleNamespace(stages=tuple(stages), questions=tuple(questions),
                           unavailable=unavailable)


def _q(kind="effect", provisional=False, profile="sha", verdict=None, stale=False):
    return SimpleNamespace(kind=kind, provisional=provisional, profile_sha256=profile,
                           verdict=verdict, verdict_stale=stale)


ALL = ("discover", "acquire", "normalize", "extract", "review", "synthesize")


def _stages(**by_name):
    return [by_name.get(name, _stage(name)) for name in ALL]


# --- the built workspace ----------------------------------------------------------------------


def test_bound_flow_gives_eight_steps_in_order(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    block = _overview(project, store)["journey"]
    assert block["journey_version"] == journey.JOURNEY_VERSION == 2
    assert [s["key"] for s in block["steps"]] == STEP_KEYS
    assert [s["n"] for s in block["steps"]] == list(range(1, 9))
    assert [s["actor"] for s in block["steps"]] == ["you"] + ["claimstone"] * 6 + ["you"]
    steps = _by_key(_overview(project, store))
    assert [steps[k]["status"] for k in STEP_KEYS[:5]] == ["done"] * 5
    assert steps["review"]["status"] == "not_started"
    assert steps["profiles"]["status"] in {"partial", "done"}
    assert steps["sign"]["status"] == "waits_for_you"
    assert steps["protocol"]["figures"]["bound_at"] == next(
        iter(flows.flows(store).values()))["created_at"]
    assert block["questions"] == {"total": 20, "literature": 20, "operational": 0}
    assert block["topics"] and set(block["topics"][0]) == {"id", "label", "terms"}
    assert block["needs_you"]["ready_to_sign"] == steps["sign"]["figures"]["ready_to_sign"] > 0
    assert block["needs_you"]["required"] == 0 and block["needs_you"]["note"] is None
    assert block["running"] == [] and block["running_note"] is None


def test_summaries_are_templates_over_figures(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    steps = _by_key(_overview(project, store))
    copies = steps["copies"]
    assert copies["summary"] == (
        "2 of 2 found sources are confirmed documents (rate 1.00, floor 0.80): the floor is met.")
    assert steps["search"]["figures"]["candidates"] == 2
    assert steps["search"]["figures"]["per_class"] == {"ACA": 2}
    assert journey.sentence("{a} of {b}, rate {c}", {"a": None, "b": 3, "c": 0.5}) == \
        "— of 3, rate 0.50"
    assert journey.sentence("{a}", {}) == "—"


def test_search_is_partial_when_a_query_failed(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    store.append("queries.jsonl", {"query_id": "q1", "round": "r1", "ok": False})
    assert _by_key(_overview(project, store))["search"]["status"] == "partial"


def test_copies_partial_then_blocked_below_the_floor(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    _candidate(store, "r1-c", "S04")           # found, never attempted: not final
    steps = _by_key(_overview(project, store))
    assert steps["copies"]["status"] == "partial"
    assert steps["copies"]["figures"]["not_obtained"] == 1
    store.append("acquisitions.jsonl", {
        "candidate_key": "r1-c", "acquired": False, "http_status": 403,
        "failure_class": "PAYWALL_403", "url": "https://example.org/r1-c.pdf",
        "campaign": "routine", "fetched_at": "2026-10-03T11:00:00+00:00",
        "attempts": [{"url": "https://example.org/r1-c.pdf", "http_status": 403,
                      "failure_class": "PAYWALL_403", "fetch_version": 3}]})
    overview = _overview(project, store)
    steps = _by_key(overview)
    assert steps["copies"]["status"] == "blocked"
    assert "Below the acquisition floor" in steps["copies"]["summary"]
    assert steps["copies"]["figures"]["status"] == "INSUFFICIENT_ACQUISITION"
    # The floor gates verdicts: step 7 is blocked with the engine's own text, verbatim.
    assert steps["profiles"]["status"] == "blocked"
    assert steps["profiles"]["summary"]
    assert steps["sign"]["status"] != "waits_for_you"


def test_documents_partial_while_an_obtained_copy_awaits_normalize(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    _candidate(store, "r1-d", "S05")
    store.append("acquisitions.jsonl", {
        "candidate_key": "r1-d", "source_id": "S05", "acquired": True, "sha256": "e" * 64,
        "stored_path": f"raw/{'e' * 64}.pdf", "url": "https://example.org/r1-d.pdf",
        "provenance": "unpaywall", "licence": "cc-by", "oa_status": "gold",
        "campaign": "routine", "fetched_at": "2026-10-03T11:00:00+00:00",
        "attempts": [{"url": "https://example.org/r1-d.pdf", "http_status": 200,
                      "failure_class": None, "fetch_version": 3}]})
    steps = _by_key(_overview(project, store))
    assert steps["documents"]["status"] == "partial"
    assert steps["copies"]["status"] == "partial"


def test_protocol_blocked_names_the_drifted_parts(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    flow_row = copy.deepcopy(next(iter(flows.flows(store).values())))
    flow_row["binding"]["protocol_sha256"] = "0" * 64
    overview = portal_state.flow_overview(project, store, scope.Selector("r1"), flow_row)
    step = _by_key(overview)["protocol"]
    assert step["status"] == "blocked"
    assert "protocol_sha256" in step["summary"]
    assert step["figures"]["drifted_parts"] == ["protocol_sha256"]


# --- stage-only rules ---------------------------------------------------------------------------


def test_annotate_rules():
    def status(stage, running=frozenset()):
        return journey._annotate(_rs(_stages(extract=stage)), running)["status"]

    assert status(_stage("extract")) == "not_started"
    assert status(_stage("extract", progress=Progress(5, 10, "x"), outputs=2)) == "partial"
    assert status(_stage("extract", progress=Progress(10, 10, "x"), outputs=2)) == "done"
    assert status(_stage("extract"), frozenset({"extract"})) == "running"
    step = journey._annotate(_rs(_stages(extract=_stage("extract"))), frozenset())
    assert step["figures"]["readings_answered"] is None and "—" not in step["summary"]
    unknown = journey._annotate(
        _rs(_stages(extract=_stage("extract", progress=Progress(3, 6, "x")))), frozenset())
    assert unknown["figures"]["annotations_kept"] is None and "—" in unknown["summary"]


def test_review_rules():
    def status(progress, running=frozenset()):
        return journey._review(_rs(_stages(review=_stage("review", progress=progress))),
                               running)["status"]

    assert status(None) == "not_started"
    assert status(Progress(0, 4, "x")) == "not_started"
    assert status(Progress(2, 4, "x")) == "partial"
    assert status(Progress(4, 4, "x")) == "done"
    assert status(None, frozenset({"review"})) == "running"


def test_profiles_rules():
    def step(outputs, questions, unavailable="", running=frozenset()):
        return journey._profiles(
            _rs(_stages(synthesize=_stage("synthesize", outputs=outputs)), questions,
                unavailable), running)

    assert step(None, [_q()])["status"] == "not_started"
    assert step(None, [_q()])["figures"]["profiles"] is None
    assert step(2, [_q(), _q(provisional=True)])["status"] == "partial"
    assert step(2, [_q(), _q(profile=None)])["status"] == "partial"
    done = step(2, [_q(), _q(), _q(kind="operational", profile="x")])
    assert done["status"] == "done" and done["figures"]["final"] == 2
    assert step(2, [_q()], running=frozenset({"synthesize"}))["status"] == "running"
    blocked = step(None, [_q()], unavailable="below the acquisition floor")
    assert blocked["status"] == "blocked" and blocked["summary"] == "below the acquisition floor"


def test_sign_rules():
    def step(questions, ready=0):
        return journey._sign(_rs(_stages(), questions), ready)

    assert step([_q(kind="operational")])["status"] == "not_applicable"
    assert step([_q(), _q()], ready=1)["status"] == "waits_for_you"
    assert step([_q(verdict="SUPPORTED"), _q(verdict="CONTRADICTED")])["status"] == "done"
    assert step([_q(verdict="SUPPORTED"), _q()])["status"] == "partial"
    assert step([_q(), _q()])["status"] == "not_started"
    stale = step([_q(verdict="SUPPORTED", stale=True)])
    assert stale["status"] == "not_started" and stale["figures"]["signed"] == 0


# --- unknown stays null ---------------------------------------------------------------------------


def test_unknown_values_stay_null(tmp_path):
    project, store, _flow = _fixture(tmp_path)
    store.path("candidates.jsonl").write_text("", encoding="utf-8")  # a bound flow, nothing found
    for name in ("documents.jsonl", "chunks.jsonl"):
        store.path(name).write_text("", encoding="utf-8")
    steps = _by_key(_overview(project, store, "new"))
    assert steps["search"]["status"] == "not_started"
    assert steps["documents"]["figures"]["documents"] is None
    assert steps["annotate"]["figures"]["readings_expected"] is None
    assert steps["review"]["figures"]["reviewed"] is None
    assert steps["profiles"]["figures"]["profiles"] is None
    assert steps["profiles"]["figures"]["provisional"] is None
    assert steps["copies"]["figures"]["rate"] is None


# --- legacy selector ------------------------------------------------------------------------------


def test_legacy_selector_is_not_verified_and_has_no_decisions(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    block = _overview(project, store, "r2")["journey"]
    assert block["steps"][0]["status"] == "not_applicable"
    assert block["steps"][0]["summary"].startswith("Protocol not verified")
    assert block["needs_you"]["required"] is None and block["needs_you"]["optional"] is None
    assert block["needs_you"]["note"] == "decisions belong to a bound flow"
    assert block["running"] == []


# --- running operations ---------------------------------------------------------------------------


def test_an_authorized_operation_is_listed_but_its_step_is_not_running(tmp_path):
    """Authorized is not started: the operation is listed with its state, and the step does not
    claim work in flight until a worker holds it."""
    project, store, flow = _fixture(tmp_path)
    plan = operations.plan(project, store, flow["flow_id"], "extract-build", batch="e1")
    operations.authorize(store, operations._digest(plan))
    overview = _overview(project, store, "new")
    (item,) = overview["journey"]["running"]
    assert item["stage"] == "extract-build" and item["state"] == "AUTHORIZED"
    assert set(item) == {"operation_id", "stage", "state", "state_note"}
    assert all(s["status"] != "running" for s in overview["journey"]["steps"])


def test_an_in_flight_operation_with_the_lock_held_marks_its_step_running(tmp_path):
    project, store, flow = _fixture(tmp_path)
    plan = operations.plan(project, store, flow["flow_id"], "extract-build", batch="e1")
    operation_id = operations._digest(plan)
    operations.authorize(store, operation_id)
    operations._append(store, operation_id, flow["flow_id"], "started", "worker")
    interrupted = _overview(project, store, "new")
    assert _by_key(interrupted)["annotate"]["status"] != "running"  # no writer: interrupted
    # A writer holding the project lock is what the scheduler reads as "running" (operations.status).
    from claimstone.store import Store as _Store
    original = _Store.writer_busy
    _Store.writer_busy = lambda self: True
    try:
        held = _overview(project, store, "new")
    finally:
        _Store.writer_busy = original
    assert _by_key(held)["annotate"]["status"] == "running"
    assert held["journey"]["running"][0]["state"] == "RUNNING_OR_LOCK_HELD"


def test_planned_operation_is_not_running(tmp_path):
    project, store, flow = _fixture(tmp_path)
    operations.plan(project, store, flow["flow_id"], "extract-build", batch="e1")
    overview = _overview(project, store, "new")
    assert overview["journey"]["running"] == []
    assert _by_key(overview)["annotate"]["status"] != "running"


def test_stage_mapping_covers_the_spec():
    assert journey._running_stages([{"stage": s, "state": "RUNNING_OR_LOCK_HELD"} for s in
                                    ("extract-build", "extract-drain", "review-drain",
                                     "discover", "acquire", "normalize", "synthesize")]) == \
        {"extract", "review", "discover", "acquire", "normalize", "synthesize"}


def test_damaged_operations_ledger_is_named_not_a_crash(tmp_path):
    project, store, _flow = _fixture(tmp_path)
    store.append(operations.LEDGER, {"event": "authorized", "operation_id": "no-plan"})
    block = _overview(project, store, "new")["journey"]
    assert block["running"] is None
    assert block["running_note"] == journey.OPERATIONS_NOTE


# --- the read API ---------------------------------------------------------------------------------


def test_route_serves_the_block_and_stays_get_only(tmp_path):
    workspace = build_workspace(tmp_path)
    flow_id = next(iter(flows.flows(workspace[3])))
    with _served(workspace) as (_httpd, base, _store):
        status, _h, body = _get_json(f"{base}/api/v1/projects/example-news-and-returns/flows/"
                                     f"{flow_id}/overview")
        assert status == 200 and len(body["journey"]["steps"]) == 8
        status, _h, legacy = _get_json(f"{base}/api/v1/projects/example-news-and-returns/"
                                       f"unbound/r2/overview")
        assert legacy["journey"]["steps"][0]["status"] == "not_applicable"


def test_read_path_does_not_import_the_control_server():
    import ast
    import pathlib

    for module in (journey, portal_state):
        tree = ast.parse(pathlib.Path(module.__file__).read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
        assert not any("control" in name.split(".") for name in names), module.__name__


# --- F13: no step reads a stance ------------------------------------------------------------------


def test_flipping_stances_changes_no_step_before_the_profiles(tmp_path):
    base = tmp_path / "a"
    flip = tmp_path / "b"
    base.mkdir(), flip.mkdir()
    _pd, _sd, project, store = build_workspace(base)
    _pd2, _sd2, project2, store2 = build_workspace(flip, flip_stances=True)
    one = _by_key(_overview(project, store))
    two = _by_key(_overview(project2, store2))
    for key in STEP_KEYS[:6]:
        assert one[key]["status"] == two[key]["status"], key
        assert one[key]["summary"] == two[key]["summary"], key


# --- the six blocks ---------------------------------------------------------------------------

PIPELINE_KEYS = ["search", "copies", "documents", "annotate", "review", "profiles"]
BLOCK_KEYS = ["protocol", "pipeline", "selection", "intake", "execution", "reading"]


def _pipeline_steps(statuses):
    return [{"key": key, "status": status} for key, status in zip(PIPELINE_KEYS, statuses)]


def test_the_overview_carries_six_blocks_in_order(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    block = _overview(project, store)["journey"]
    assert [b["key"] for b in block["blocks"]] == BLOCK_KEYS
    for tile in block["blocks"]:
        assert tile["status"] in journey.BLOCK_STATUSES
        assert isinstance(tile["title"], str) and isinstance(tile["figure"], str)
    assert block["selection"]["state"] == "NO_SCOPE_DECLARED"


@pytest.mark.parametrize("statuses,expected", [
    (["done"] * 6, "done"),
    (["done", "done", "blocked", "done", "done", "done"], "blocked"),
    (["done", "partial", "running", "not_started", "not_started", "not_started"], "running"),
    (["not_started"] * 6, "not_started"),
    (["done"] + ["not_started"] * 5, "partial"),
    (["partial"] + ["not_started"] * 5, "partial"),
    (["blocked", "running"] + ["not_started"] * 4, "blocked"),
    (["done", "running", "blocked", "done", "not_started", "partial"], "blocked"),
])
def test_pipeline_tile_status_rule(statuses, expected):
    assert journey._pipeline_block(_pipeline_steps(statuses))["status"] == expected


def test_pipeline_tile_figure_counts_steps_not_percent():
    tile = journey._pipeline_block(_pipeline_steps(["done"] * 2 + ["partial"] + ["not_started"] * 3))
    assert tile["figure"] == "2 of 6 steps done"


def test_selection_tile_is_never_done_and_names_every_state():
    def sel(state, scopes=()):
        return {"state": state, "scopes": list(scopes)}

    def ok(screened=48, unobserved=782):
        return {"scope_id": "s", "question_id": "Q", "state": "OK",
                "figures": {"screened_count": screened, "unobserved_count": unobserved}}

    bad = {"scope_id": "s", "question_id": "Q", "state": "INVENTORY_DRIFTED", "figures": None}
    assert journey._selection_block(sel("NO_SCOPE_DECLARED"))["status"] == "not_declared"
    assert journey._selection_block(sel("SCOPES_FILE_INVALID"))["status"] == "unavailable"
    assert journey._selection_block(sel("DECLARED", [bad]))["status"] == "unavailable"
    tile = journey._selection_block(sel("DECLARED", [ok()]))
    assert tile["status"] == "advisory" and tile["figure"] == "48 seen · 782 unseen"
    # Even with nothing left unobserved the block stays advisory: this surface closes no cohort.
    assert journey._selection_block(sel("DECLARED", [ok(830, 0)]))["status"] == "advisory"
    assert journey._selection_block(sel("DECLARED", [ok(), ok()]))["figure"] == "2 scopes"


def test_intake_tile_rules():
    waiting = journey._intake_block({"x": 1}, {"required": 2, "optional": 1})
    assert waiting["status"] == "waits_for_you" and waiting["figure"] == "2 required · 1 optional"
    assert journey._intake_block({"x": 1}, {"required": 0, "optional": 3})["status"] == "idle"
    unreadable = journey._intake_block({"x": 1}, {"required": None, "optional": None})
    assert unreadable["status"] == "unavailable" and unreadable["figure"] == "— required · — optional"
    assert journey._intake_block(None, {"required": None, "optional": None})["status"] == "not_applicable"


def test_execution_tile_rules():
    assert journey._execution_block(None)["status"] == "unavailable"
    idle = journey._execution_block([])
    assert idle["status"] == "idle" and idle["figure"] == "0 running · 0 listed"
    authorized = [{"stage": "extract-drain", "state": "AUTHORIZED"}]
    assert journey._execution_block(authorized)["status"] == "idle"
    live = [{"stage": "extract-drain", "state": "RUNNING_OR_LOCK_HELD"}, authorized[0]]
    tile = journey._execution_block(live)
    assert tile["status"] == "running" and tile["figure"] == "1 running · 2 listed"


def test_a_legacy_selector_has_a_protocol_tile_that_says_it_is_not_verified(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    tiles = {b["key"]: b for b in _overview(project, store, "r2")["journey"]["blocks"]}
    assert tiles["protocol"]["status"] == "not_applicable"
    assert tiles["protocol"]["figure"] == "protocol not verified"
    assert tiles["intake"]["status"] == "not_applicable"


def test_selection_is_carried_in_the_overview_and_the_read_writes_nothing(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    base = store.path("audits/source-selection")
    (base / "inv").mkdir(parents=True)
    data = json.dumps([{"candidate_key": key} for key in ("x", "y", "z")]).encode()
    (base / "inv" / "inventory.json").write_bytes(data)
    (base / "scopes.json").write_text(json.dumps({"scopes": [{
        "scope_id": "s1", "question_id": "Q1", "round": "r1",
        "inventory_path": "inv/inventory.json",
        "inventory_sha256": hashlib.sha256(data).hexdigest()}]}))
    audits = store.path("audits")
    before = {p: p.read_bytes() for p in audits.rglob("*") if p.is_file()}
    block = _overview(project, store)["journey"]
    assert block["selection"]["state"] == "DECLARED"
    assert block["selection"]["scopes"][0]["figures"]["unobserved_count"] == 3
    tile = {b["key"]: b for b in block["blocks"]}["selection"]
    assert tile["status"] == "advisory" and tile["figure"] == "0 seen · 3 unseen"
    assert {p: p.read_bytes() for p in audits.rglob("*") if p.is_file()} == before
    assert not store.path("source_screening.jsonl").exists()


def test_reading_tile_rules():
    def sign(status, **figures):
        return [{"key": "sign", "status": status, "figures": figures}]

    none = journey._reading_block(sign("not_applicable"))
    assert none["status"] == "not_applicable" and none["figure"] == "no literature question"
    waiting = journey._reading_block(sign("waits_for_you", ready_to_sign=3, signed=1,
                                          literature_total=5))
    assert waiting["status"] == "waits_for_you" and waiting["figure"] == "3 to sign · 1 of 5 signed"


def test_protocol_tile_of_a_bound_flow_mirrors_the_overview_steps(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    block = _overview(project, store)["journey"]
    steps = {step["key"]: step for step in block["steps"]}
    tile = {b["key"]: b for b in block["blocks"]}["protocol"]
    floor = steps["copies"]["figures"]["floor"]
    floor_text = "—" if floor is None else f"{floor:.2f}"
    assert tile["status"] == steps["protocol"]["status"]
    assert tile["figure"] == f"{steps['protocol']['figures']['questions_total']} questions · floor {floor_text}"


def test_protocol_tile_with_an_unknown_floor_shows_a_dash():
    steps = [{"key": "protocol", "status": "done", "figures": {"questions_total": 4}},
             {"key": "copies", "status": "not_started", "figures": {"floor": None}}]
    assert journey._protocol_block(steps)["figure"] == "4 questions · floor —"


def test_selection_tile_with_one_unreadable_scope_is_unavailable():
    ok = {"scope_id": "a", "question_id": "Q", "state": "OK",
          "figures": {"screened_count": 1, "unobserved_count": 2}}
    bad = {"scope_id": "b", "question_id": "Q", "state": "INVENTORY_DRIFTED", "figures": None}
    tile = journey._selection_block({"state": "DECLARED", "scopes": [ok, bad]})
    assert tile["status"] == "unavailable" and tile["figure"] == "1 scope(s) unreadable"


def test_execution_tile_lists_an_unknown_stage_but_does_not_count_it_running():
    assert "bogus" not in journey.OPERATION_STAGE
    tile = journey._execution_block([{"stage": "bogus", "state": "RUNNING_OR_LOCK_HELD"}])
    assert tile["status"] == "idle" and tile["figure"] == "0 running · 1 listed"


# --- the pipeline tile says when the project holds candidates in other rounds ----------------------


def _other_candidates(store, selector):
    rows = [row for row in store.latest_by("candidates.jsonl", "candidate_key").values()
            if not scope.candidate_in_scope(row, selector)]
    return len(rows), len({row.get("round") for row in rows})


def test_pipeline_tile_notes_other_rounds_only_when_not_started():
    idle = _pipeline_steps(["not_started"] * 6)
    tile = journey._pipeline_block(idle, others=(34, 2))
    assert tile["figure"] == "0 of 6 steps done · 34 candidates in 2 other round(s)"
    assert tile["status"] == "not_started"
    started = _pipeline_steps(["done"] + ["not_started"] * 5)
    assert journey._pipeline_block(started, others=(34, 2))["figure"] == "1 of 6 steps done"
    assert journey._pipeline_block(idle, others=None)["figure"] == "0 of 6 steps done"


def test_an_empty_round_says_what_the_other_rounds_hold(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    selector = scope.Selector("r-empty")
    count, rounds = _other_candidates(store, selector)
    assert count > 0
    block = portal_state.flow_overview(project, store, selector, None)["journey"]
    tile = {b["key"]: b for b in block["blocks"]}["pipeline"]
    assert tile["status"] == "not_started"
    assert tile["figure"] == f"0 of 6 steps done · {count} candidates in {rounds} other round(s)"


def test_a_damaged_candidates_ledger_gives_no_other_rounds_count(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    with store.path("candidates.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"torn": \n{"candidate_key": "z", "round": "r9"}\n')
    selector = scope.Selector("r-empty")
    # The overview itself refuses to build on a damaged candidates ledger (a named error, not a
    # figure), so the helper's answer is the whole contract here: unknown, never a guessed count.
    assert journey._other_rounds(store, selector) is None
