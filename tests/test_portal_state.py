"""portal_state: the portal's pure core — spec §4.13, the pure-function table.

One builder assembles a tmp projects dir with a copied example project and a store that has one
complete, extractable round (r1, bound to a flow) beside a legacy round (r2) with a failed
acquisition and a stray claim. No socket opens anywhere in this file.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import shutil

import pytest

from claimstone import claimgate, cli, extract, flows, model_call, portal_state, scope, synthesize
from claimstone.config import load_project
from claimstone.store import Store

SOURCE_PROJECT = "projects/example-news-and-returns"


def build_workspace(tmp_path, *, flip_stances: bool = False):
    """(projects_dir, store_dir, project, store). r1 complete and bound; r2 legacy."""
    projects_dir = tmp_path / "projects"
    store_dir = tmp_path / "store"
    root = projects_dir / "example-news-and-returns"
    shutil.copytree(SOURCE_PROJECT, root)
    project = load_project(root)
    store = Store(project.name, base=store_dir)
    stance = "CONTRADICTS" if flip_stances else "SUPPORTS"

    for source_id, key, title in (("S01", "r1-a", "Study one"), ("S02", "r1-b", "Study two")):
        store.append("candidates.jsonl", {
            "candidate_key": key, "source_id": source_id, "round": "r1",
            "channel": "keyword", "source_class": "ACA", "title": title,
            "url": f"https://example.org/{source_id}.pdf",
            "discovered_at": "2026-10-01T10:00:00+00:00"})
        generation = f"gen-{source_id}"
        store.append("acquisitions.jsonl", {
            "candidate_key": key, "source_id": source_id, "acquired": True,
            "sha256": source_id.lower() * 64, "stored_path": f"raw/{source_id.lower()*64}.pdf",
            "url": f"https://example.org/{source_id}.pdf", "provenance": "unpaywall",
            "licence": "cc-by", "oa_status": "gold", "campaign": "routine",
            "fetched_at": "2026-10-01T11:00:00+00:00",
            "attempts": [{"url": f"https://example.org/{source_id}.pdf", "http_status": 200,
                          "failure_class": None, "fetch_version": 3}]})
        store.append("documents.jsonl", {
            "source_id": source_id, "fulltext_confirmed": True,
            "generation_sha256": generation, "chunks": 1,
            "chunk_ids": [f"{source_id}#c1"], "format": "html",
            "html_parser_version": 2, "jats_parser_version": None,
            "references": 12, "body_chars": 5000, "built_at": "2026-10-01T12:00:00+00:00"})
        store.append("chunks.jsonl", {
            "chunk_id": f"{source_id}#c1", "source_id": source_id,
            "generation_sha256": generation, "kind": "prose",
            "text": "news tone has an effect on returns", "built_at": "2026-10-01T12:00:01+00:00"})

    # The extraction every profile needs to be non-provisional: requests built by the real
    # instrument, answered with valid empty readings.
    extract.build(project, store, batch="production")
    queue = model_call.Queue(store, lane="extract", batch="production")
    for unit in queue.requests():
        store.append(queue.results_name, {
            "call_id": unit["call_id"], "backend": "b", "model": "m",
            "harness_version": "t/1", "ok": True, "output": [],
            "usage": {"input_tokens": 10, "output_tokens": 10}, "cost_usd": 0.00002})

    store.append("claims.jsonl", {
        "claim_id": "c1", "question_id": "Q02", "source_id": "S01", "source_class": "ACA",
        "chunk_id": "S01#c1", "stance": stance, "claim": "News tone has an effect.",
        "evidence_quote": "news tone has an effect", "registry_version": 2,
        "claim_gate_version": claimgate.CLAIM_GATE_VERSION, "gate_revision": 1,
        "backend": "b", "model": "m", "harness_version": "t/1",
        "harvested_at": "2026-10-05T10:00:00+00:00"})
    store.append("claims.jsonl", {
        "claim_id": "c2", "question_id": "Q02", "source_id": "S02", "source_class": "ACA",
        "chunk_id": "S02#c1", "stance": stance, "claim": "A claim whose quote is absent.",
        "evidence_quote": "this sentence is not in the chunk", "registry_version": 2,
        "claim_gate_version": claimgate.CLAIM_GATE_VERSION, "gate_revision": 1,
        "backend": "b", "model": "m", "harness_version": "t/1",
        "harvested_at": "2026-10-05T10:00:01+00:00"})

    # r2, the legacy round: an unattempted candidate, a PAYWALL_403, and a stray claim.
    store.append("candidates.jsonl", {
        "candidate_key": "r2-a", "source_id": "S03", "round": "r2", "channel": "citation",
        "source_class": "ACA", "title": "Study three", "url": "https://example.org/S03.pdf",
        "discovered_at": "2026-10-02T10:00:00+00:00"})
    store.append("candidates.jsonl", {
        "candidate_key": "r2-w", "round": "r2", "channel": "citation", "source_class": "ACA",
        "title": "Refused work", "url": "https://example.org/locked.pdf",
        "discovered_at": "2026-10-02T10:00:01+00:00"})
    store.append("acquisitions.jsonl", {
        "candidate_key": "r2-w", "acquired": False, "http_status": 403,
        "failure_class": "PAYWALL_403", "url": "https://example.org/locked.pdf",
        "campaign": "routine", "fetched_at": "2026-10-02T11:00:00+00:00",
        "attempts": [{"url": "https://example.org/locked.pdf", "http_status": 403,
                      "failure_class": "PAYWALL_403", "fetch_version": 3}]})
    store.append("claims.jsonl", {
        "claim_id": "c9", "question_id": "Q02", "source_id": "S03", "source_class": "ACA",
        "stance": stance, "claim": "A claim from the other round.",
        "evidence_quote": "belongs to r2", "registry_version": 2,
        "claim_gate_version": claimgate.CLAIM_GATE_VERSION, "gate_revision": 1,
        "harvested_at": "2026-10-02T12:00:00+00:00"})

    # Stored profiles for r1, built by the real stage 6: `verdicts` walks the stored rows and
    # overlays the live preview. A hand-written row with an invented hash would never match the
    # live profile, and `adjudicate` refuses exactly that — so a test built on one would prove a
    # signing command the engine cannot accept.
    synthesize.build(project, store, round_name="r1")

    flows.create(project, store, selector=scope.Selector("r1"), title="round one")
    return projects_dir, store_dir, project, store


@pytest.fixture()
def workspace(tmp_path):
    return build_workspace(tmp_path)


def test_index_lists_flows_and_legacy_selectors(workspace):
    """P-T1: the index names the flow and the legacy round, with the legacy label."""
    projects_dir, store_dir, _project, _store = workspace
    data = portal_state.index(projects_dir, store_dir)
    assert len(data["projects"]) == 1
    card = data["projects"][0]
    assert card["config"] == "OK"
    assert [entry["selector"]["round"] for entry in card["flows"]] == ["r1"]
    assert card["flows"][0]["binding_state"] == "CURRENT"
    assert card["legacy"] == ["r2"]
    assert card["legacy_note"] == "legacy: protocol not verified"
    assert card["inbox_counts"]  # the r1 flow has adjudication work open


def test_flow_overview_leaks_no_other_round(workspace):
    """P-T2: the r1 overview's JSON contains no r2 source id or candidate key anywhere."""
    _projects_dir, _store_dir, project, store = workspace
    flow_id = next(iter(flows.flows(store)))
    overview = portal_state.flow_overview(project, store, scope.Selector("r1"),
                                          flows.flows(store)[flow_id])
    dumped = json.dumps(overview, default=str)
    assert "S03" not in dumped
    assert "r2-a" not in dumped and "r2-w" not in dumped


def test_protocol_drift_banner_and_live_floor(workspace):
    """P-T3: a floor change in the project reads as PROTOCOL_DRIFTED, and the floor panel shows
    the live floor, never the bound one (F4: the binding is compared, not used)."""
    _projects_dir, _store_dir, project, store = workspace
    flow_id = next(iter(flows.flows(store)))
    flow_row = flows.flows(store)[flow_id]
    sources = project.root / "sources.yaml"
    sources.write_text(
        sources.read_text(encoding="utf-8").replace("acquisition_floor: 0.80",
                                                    "acquisition_floor: 0.75"),
        encoding="utf-8")
    live = load_project(project.root)
    overview = portal_state.flow_overview(live, store, scope.Selector("r1"), flow_row)
    assert overview["binding_state"]["state"] == "PROTOCOL_DRIFTED"
    assert overview["binding_state"]["differences"] == ["protocol_sha256"]
    assert overview["floor_panel"]["overall"]["floor"] == 0.75


def test_paywall_card_sentence_is_exact(workspace):
    """I-T1: the PAYWALL_403 cause is the F19 sentence; 'paywall' appears only inside it."""
    _projects_dir, _store_dir, project, store = workspace
    cards = portal_state.inbox_cards(project, store, scope.Selector("r2"))
    paywall = [card for card in cards
               if card.category == "ACQUISITION" and card.subject == "r2-w"]
    assert len(paywall) == 1
    assert paywall[0].cause == portal_state.PAYWALL_TEXT
    for card in cards:
        if "paywall" in card.cause.lower():
            assert "not proof of a paywall" in card.cause


def test_cards_sort_by_category_then_subject(workspace):
    """I-T2: CATEGORY_ORDER then subject is the only ordering rule."""
    cards = [
        portal_state.Card("ADJUDICATION", "flow x", "Q10", "c", None, ""),
        portal_state.Card("ACQUISITION", "flow x", "zz", "c", None, ""),
        portal_state.Card("INTEGRITY", "flow x", "b", "c", None, ""),
        portal_state.Card("ACQUISITION", "flow x", "aa", "c", None, ""),
        portal_state.Card("ADVISORY", "flow x", "Q01", "c", None, ""),
        portal_state.Card("INTEGRITY", "flow x", "a", "c", None, ""),
    ]
    ordered = portal_state.sort_cards(cards)
    assert [(card.category, card.subject) for card in ordered] == [
        ("INTEGRITY", "a"), ("INTEGRITY", "b"), ("ACQUISITION", "aa"),
        ("ACQUISITION", "zz"), ("ADJUDICATION", "Q10"), ("ADVISORY", "Q01")]


def test_work_cards_signature_and_stance_independence(tmp_path):
    """I-T3: the acquisition builder takes exactly §4.5's five arguments, and flipping every
    claim's stance changes nothing about the ACQUISITION cards (F13)."""
    build_workspace(tmp_path / "a")
    build_workspace(tmp_path / "b", flip_stances=True)

    signature = inspect.signature(portal_state.work_cards)
    assert list(signature.parameters) == ["project", "admitted", "scoped_candidates",
                                          "collapsed_acquisitions", "selector"]

    from claimstone import admissibility

    def acquisition_cards(base):
        project = load_project(base / "projects" / "example-news-and-returns")
        store = Store(project.name, base=base / "store")
        selector = scope.Selector("r2")
        admitted = admissibility.admit(project, store, round_name="r2")
        cards = portal_state.work_cards(project, admitted,
                                        scope.candidates(store, selector),
                                        admissibility.collapse(store), selector)
        # The command embeds the project path, which differs between the two bases; compare
        # everything else as-is and the command with the base path neutralized.
        return [dataclasses.replace(card, scope="", command=(
            None if card.command is None else card.command.replace(str(base), "<base>")))
            for card in cards]

    # The builder ran on two stores whose only difference is claim stances.
    assert acquisition_cards(tmp_path / "a") == acquisition_cards(tmp_path / "b")


def test_every_command_parses_with_the_real_parser(workspace):
    """I-T4: each non-None command string parses once placeholders are filled with dummies."""
    import re

    _projects_dir, _store_dir, project, store = workspace
    cards = list(portal_state.inbox_cards(project, store, scope.Selector("r1")))
    cards += portal_state.inbox_cards(project, store, scope.Selector("r2"))
    synthetic_admitted = {
        "awaiting_normalize": 1, "not_a_document": ["S07"],
        "by_class": {"ACA": {"found": 2, "obtained": 2, "confirmed": 1,
                             "awaiting_normalize": 1, "rate": 0.5, "basis": "confirmed",
                             "floor": 0.8, "meets_floor": False}},
    }
    unclassified = {"candidate_key": "r1-x", "source_id": "S08", "round": "r1",
                    "source_class": None}
    cards += portal_state.work_cards(
        project, synthetic_admitted,
        {"r1-x": unclassified}, {"r1-x": {"acquired": False, "failure_class": "ROBOTS_DISALLOWED"}},
        scope.Selector("r1"))

    commands = [card.command for card in cards if card.command]
    assert len(commands) >= 5  # acquire, retry-acquire, discover, normalize, adjudicate shapes
    parser = cli.build_parser()
    for command in commands:
        argv = command.split()
        if argv[0] == "./claimstone.sh":
            argv = argv[1:]  # the exception §4.5 names: the check is the subcommand `normalize`
        else:
            assert argv[0] == "claimstone", command
            argv = argv[1:]
        argv = [re.sub(r"<[^>]+>", "DUMMY", part) for part in argv]
        try:
            parser.parse_args(argv)
        except SystemExit as exc:
            raise AssertionError(f"unparseable command: {command}") from exc


def test_adjudication_card_carries_hash_and_placeholder(workspace):
    """I-T5: the full profile hash and the literal <ONE_OF_FIVE>; never a concrete verdict."""
    _projects_dir, _store_dir, project, store = workspace
    cards = portal_state.inbox_cards(project, store, scope.Selector("r1"))
    adjudications = [card for card in cards if card.category == "ADJUDICATION"]
    assert adjudications
    for card in adjudications:
        assert len(card.command.split("--profile-sha256 ")[1].split()[0]) == 64
        assert "--verdict <ONE_OF_FIVE>" in card.command
        for verdict in cli.VERDICT_NAMES:
            assert f"--verdict {verdict}" not in card.command
        # The hash on the card is the one `adjudicate` will accept: the stored profile's, equal
        # to the live one. A card carrying any other hash proposes a refused signature.
        stored = synthesize.latest_profiles(store, round_name="r1")[card.subject]
        assert stored["profile_sha256"] in card.command


def test_adjudication_card_on_a_stale_stored_profile_rebuilds_first(workspace):
    """When the stored profile differs from current evidence, `adjudicate` refuses
    (StaleProfile), so the next valid action is `synthesize`, not a signature."""
    _projects_dir, _store_dir, project, store = workspace
    question = next(q for q in project.questions if q.kind != "operational")
    stored = synthesize.latest_profiles(store, round_name="r1")[question.id]
    store.append("profiles.jsonl", {**stored, "profile_sha256": "0" * 64})
    cards = [card for card in portal_state.inbox_cards(project, store, scope.Selector("r1"))
             if card.category == "ADJUDICATION" and card.subject == question.id]
    assert len(cards) == 1
    assert cards[0].command.startswith("claimstone synthesize ")
    assert "adjudicate" not in cards[0].command
    assert "differs from current evidence" in cards[0].cause


def test_lineage_six_steps_and_quote_recheck(workspace):
    """L-T1: every step renders for a complete fixture, and the quote is rechecked against the
    current chunk text — a claim whose quote is absent says so, loudly."""
    _projects_dir, _store_dir, project, store = workspace
    page = portal_state.lineage(project, store, scope.Selector("r1"), "c1")
    steps = page["steps"]
    assert steps["claim"]["evidence_quote"] == "news tone has an effect"
    assert steps["chunk"]["quote_found"] is True
    assert steps["chunk"]["chunk_id"] == "S01#c1"
    assert steps["document"]["fulltext_confirmed"] is True
    assert steps["acquisition"]["licence"] == "cc-by"
    assert steps["candidate"]["round"] == "r1"
    assert steps["review"] is None  # awaiting review is a rendered state, not a missing step

    bad = portal_state.lineage(project, store, scope.Selector("r1"), "c2")
    assert bad["steps"]["chunk"]["quote_found"] is False


def test_lineage_of_another_round_is_not_found(workspace):
    """L-T2: a claim of r2 requested under the r1 selector raises the not-found path."""
    _projects_dir, _store_dir, project, store = workspace
    with pytest.raises(portal_state.NotFound):
        portal_state.lineage(project, store, scope.Selector("r1"), "c9")


def test_admin_state_never_leaks_values(tmp_path, monkeypatch):
    """A-T1: presence only — no value, no prefix, no length in the JSON."""
    monkeypatch.setenv("OLLAMA_API_KEY", "secret-value-123")
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    (tmp_path / ".env").write_text("CLAIMSTONE_CONTACT_EMAIL=me@example.org\n", encoding="utf-8")
    data = portal_state.admin_state(tmp_path)
    dumped = json.dumps(data)
    assert "secret-value-123" not in dumped
    assert "secret" not in dumped
    assert "me@example.org" not in dumped and "example.org" not in dumped
    # The secret is 16 characters long. Instrument versions elsewhere in the payload are small
    # integers, so the length check is made where a leak would appear: the credentials block
    # holds booleans and nothing else.
    assert len("secret-value-123") == 16
    assert all(value is True or value is False for value in data["credentials"].values())
    assert "16" not in json.dumps(data["credentials"])
    assert data["credentials"] == {"CLAIMSTONE_CONTACT_EMAIL": True,
                                   "OLLAMA_API_KEY": True,
                                   "OPENALEX_API_KEY": False}


def test_integrity_names_corruption_and_touches_nothing(workspace):
    """G-T1: a corrupt ledger is reported by name, and the file is not modified."""
    _projects_dir, _store_dir, project, store = workspace
    target = store.path("reviews.jsonl")
    target.write_bytes(b'{"claim_id": "c1"}\n{bad\n')
    before = target.read_bytes()
    data = portal_state.integrity(project.root, store)
    assert data["ledgers"]["reviews.jsonl"]["error"] is not None
    assert "not valid JSON" in data["ledgers"]["reviews.jsonl"]["error"]
    assert target.read_bytes() == before


def test_floor_panel_needed_arithmetic():
    """F-T9: needed = ceil(floor*found) - confirmed, floor-guarded, never negative."""
    panel = portal_state.floor_panel({
        "basis": "confirmed", "found": 12, "rate": 2 / 12, "floor": 0.8,
        "floor_version": 1, "floor_set_at": "2026-01-01", "status": "INSUFFICIENT_ACQUISITION",
        "final": False, "blocking": ["awaiting_normalize"],
        "by_class": {"ACA": {"found": 12, "confirmed": 2, "obtained": 12,
                             "awaiting_normalize": 10, "basis": "confirmed",
                             "rate": 2 / 12, "floor": 0.8, "meets_floor": False}}})
    assert panel["by_class"]["ACA"]["needed"] == 8
    assert panel["sentences"] == [
        "ACA: 8 more of the 10 not yet confirmed would be needed to reach its floor. "
        "This says nothing about which are obtainable, and selecting them by expected result "
        "is not allowed."]
    panel = portal_state.floor_panel({
        "basis": "confirmed", "found": 5, "rate": 0.8, "floor": 0.8, "floor_version": 1,
        "floor_set_at": "2026-01-01", "status": "OK", "final": True, "blocking": [],
        "by_class": {"ACA": {"found": 5, "confirmed": 4, "obtained": 5,
                             "awaiting_normalize": 1, "basis": "confirmed", "rate": 0.8,
                             "floor": 0.8, "meets_floor": True}}})
    assert panel["by_class"]["ACA"]["needed"] == 0
    assert panel["sentences"] == []


# --- review of the implementation (2026-10-06): regressions for the fixed findings --------------


def test_whole_store_profiles_are_reachable(workspace):
    """R1: profiles recorded under `round: null` (pmc-screen-time's real Q04 case) appear as an
    unbound selector, with a slug the legacy route resolves; an invented slug is NotFound."""
    _projects_dir, _store_dir, project, store = workspace
    # The whole store is below its floor here, so `build` would refuse it; a recorded profile
    # under another selector is copied in, as a store from before round selectors would hold it.
    recorded = next(iter(synthesize.latest_profiles(store, round_name="r1").values()))
    store.append("profiles.jsonl", {**recorded, "round": None, "manifest_only": True})
    unbound = portal_state.unbound_selectors(store, flows.flows(store).values())
    assert scope.Selector(None, False) in unbound               # candidates exist
    assert scope.Selector(None, True) in unbound                # a profile was recorded there
    assert portal_state.selector_from_slug(
        store, flows.flows(store).values(), "-~manifest") == scope.Selector(None, True)
    assert scope.Selector("r2", False) in unbound
    assert scope.Selector("r1", False) not in unbound          # bound by the fixture's flow
    whole = portal_state.selector_from_slug(store, flows.flows(store).values(), "-")
    assert whole == scope.Selector(None, False)
    with pytest.raises(portal_state.NotFound):
        portal_state.selector_from_slug(store, flows.flows(store).values(), "no-such-round")
    page = portal_state.flow_overview(project, store, scope.Selector(None, True))
    assert page["selector_label"] == "whole store · manifest only"


def test_flow_overview_computes_each_reading_once(workspace, monkeypatch):
    """R2: one flow page runs `synthesize.verdicts` once and `round_state.state` once — it ran
    them five and three times, 15 s per page on the real PMC store."""
    _projects_dir, _store_dir, project, store = workspace
    from claimstone import round_state
    calls = {"verdicts": 0, "state": 0}
    real_verdicts, real_state = synthesize.verdicts, round_state.state

    def counting_verdicts(*args, **kwargs):
        calls["verdicts"] += 1
        return real_verdicts(*args, **kwargs)

    def counting_state(*args, **kwargs):
        calls["state"] += 1
        return real_state(*args, **kwargs)

    monkeypatch.setattr(synthesize, "verdicts", counting_verdicts)
    monkeypatch.setattr(round_state, "state", counting_state)
    flow_row = next(iter(flows.flows(store).values()))
    portal_state.flow_overview(project, store, scope.Selector("r1"), flow_row)
    assert calls == {"verdicts": 1, "state": 1}


def test_acquisition_cards_preview_first_and_skip_unclassified(tmp_path):
    """R3: a routine retry is offered as `--dry-run` with the sweep-authorization note, and an
    UNCLASSIFIED refusal gets the CLASSIFICATION card only — never `--retry-class UNCLASSIFIED`."""
    _projects_dir, _store_dir, project, store = build_workspace(tmp_path)
    store.append("candidates.jsonl", {"candidate_key": "r2-u", "round": "r2", "channel": "keyword",
                                      "title": "No class", "url": "https://example.org/u.pdf"})
    store.append("acquisitions.jsonl", {"candidate_key": "r2-u", "acquired": False,
                                        "failure_class": "UNCLASSIFIED", "attempts": [],
                                        "fetched_at": "2026-10-02T11:00:00+00:00"})
    cards = portal_state.inbox_cards(project, store, scope.Selector("r2"))
    acquisition = [card for card in cards if card.category == "ACQUISITION"]
    assert all("UNCLASSIFIED" not in (card.command or "") for card in acquisition)
    routine = [card for card in acquisition if card.subject == "S03"]
    assert routine and routine[0].command.endswith("--dry-run")
    assert "authorization" in routine[0].note
    assert any(card.category == "CLASSIFICATION" and card.subject == "r2-u" for card in cards)


def test_a_forged_flow_row_is_not_a_flow(workspace):
    """R4: a `created` row whose id is not the hash of its binding is excluded and named."""
    _projects_dir, _store_dir, project, store = workspace
    genuine = next(iter(flows.flows(store).values()))
    forged = {**genuine, "binding": {**genuine["binding"], "registry_version": 99}}
    store.append("flows.jsonl", forged)
    assert list(flows.flows(store)) == [genuine["flow_id"]]
    assert flows.invalid_flows(store) == [genuine["flow_id"]]
    assert portal_state.integrity(project.root, store)["invalid_flows"] == [genuine["flow_id"]]


def test_missing_instrument_checker_is_a_named_problem(monkeypatch):
    """R5: inside an image the tools/ directory may be absent; that is UNAVAILABLE, not OK."""
    monkeypatch.setattr(portal_state, "_INSTRUMENT_CHECKER", None)
    monkeypatch.setattr(portal_state, "_checker_path", lambda: None)
    problems = portal_state.instrument_check()
    assert len(problems) == 1 and problems[0].startswith("UNAVAILABLE")
