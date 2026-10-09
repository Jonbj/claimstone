"""selection_view: the source-selection block of the journey. Advisory, read-only, and it names
its failures instead of showing zeros."""

from __future__ import annotations

import hashlib
import json

from claimstone import scope, selection_view
from claimstone import source_selection as selection
from claimstone.store import Store

H = "a" * 64
ROUND = "r1"


def _assessment(key, decision="UNCERTAIN", role="UNRESOLVED", supersedes=None):
    return selection.identified({
        "selection_version": selection.SOURCE_SELECTION_VERSION,
        "scope_id": "s1", "question_id": "Q1", "registry_sha256": H,
        "candidate_key": key, "source_class": "UNCLASSIFIED",
        "assessment_status": "AI_PROVISIONAL", "decision": decision, "role": role,
        "screening_level": "ABSTRACT", "criterion_ids": ["C1"], "reason": "fixture",
        "assessed_by": "test agent", "input_sha256": H,
        "evidence": [{"quote": "text", "locator": "fixture:1", "text_sha256": H}],
        "supersedes": supersedes,
    }, "assessment_id")


def _declare(store, keys, *, round_name=ROUND, path="inv/inventory.json", sha=None):
    base = store.path(selection_view.BASE_DIR)
    (base / "inv").mkdir(parents=True, exist_ok=True)
    data = json.dumps([{"candidate_key": key} for key in keys]).encode()
    (base / "inv" / "inventory.json").write_bytes(data)
    (base / "scopes.json").write_text(json.dumps({"scopes": [{
        "scope_id": "s1", "question_id": "Q1", "round": round_name,
        "inventory_path": path, "inventory_sha256": sha or hashlib.sha256(data).hexdigest()}]}))


def _screen(store, rows, inventory):
    selection.append_observations(store, rows, [], scope_id="s1", question_id="Q1",
                                  inventory_keys=set(inventory))


def _read(store):
    return selection_view.read(store, scope.Selector(ROUND))


def _tree(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


def _assert_advisory(result):
    assert result["advisory"] is True
    assert result["assessment_status"] == "AI_PROVISIONAL"
    assert result["cohort_closed"] is False
    assert result["admitted_candidates"] == 0
    assert result["selection_version"] == selection_view.SELECTION_VIEW_VERSION


def test_no_declaration_is_named_not_zero(tmp_path):
    result = _read(Store("fixture", base=tmp_path))
    assert result["state"] == "NO_SCOPE_DECLARED" and result["scopes"] == []
    _assert_advisory(result)


def test_a_scope_for_another_round_is_not_this_rounds(tmp_path):
    store = Store("fixture", base=tmp_path)
    _declare(store, ["a"], round_name="other")
    assert _read(store)["state"] == "NO_SCOPE_DECLARED"


def test_an_unreadable_declaration_is_named(tmp_path):
    store = Store("fixture", base=tmp_path)
    path = store.path(selection_view.SCOPES_FILE)
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    result = _read(store)
    assert result["state"] == "SCOPES_FILE_INVALID" and result["scopes"] == []
    _assert_advisory(result)


def test_counts_use_the_latest_row_per_key(tmp_path):
    store = Store("fixture", base=tmp_path)
    keys = ["a", "b", "c", "d"]
    first = _assessment("a")
    rows = [first,
            _assessment("a", "EXCLUDE", "CONTEXT", supersedes=first["assessment_id"]),
            _assessment("b", "INCLUDE", "DIRECT_CANDIDATE"),
            _assessment("c", "EXCLUDE", "NOT_DIRECT")]
    _declare(store, keys)
    _screen(store, rows, keys)
    result = _read(store)
    assert result["state"] == "DECLARED"
    (only,) = result["scopes"]
    assert only["state"] == "OK"
    assert only["scope_id"] == "s1" and only["question_id"] == "Q1"
    assert only["figures"] == {
        "inventory_count": 4, "screened_count": 3, "unobserved_count": 1,
        "direct": 1, "context": 1, "not_direct": 1, "uncertain": 0,
        "identity_observations": 0}
    _assert_advisory(result)


def test_a_drifted_inventory_shows_no_figures(tmp_path):
    store = Store("fixture", base=tmp_path)
    _declare(store, ["a", "b"], sha="0" * 64)
    (only,) = _read(store)["scopes"]
    assert only["state"] == "INVENTORY_DRIFTED" and only["figures"] is None


def test_a_missing_inventory_shows_no_figures(tmp_path):
    store = Store("fixture", base=tmp_path)
    _declare(store, ["a"], path="inv/nowhere.json")
    (only,) = _read(store)["scopes"]
    assert only["state"] == "INVENTORY_UNREADABLE" and only["figures"] is None


def test_an_inventory_path_that_leaves_the_directory_is_refused(tmp_path):
    store = Store("fixture", base=tmp_path)
    outside = tmp_path / "fixture" / "outside.json"
    data = json.dumps([{"candidate_key": "a"}]).encode()
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(data)
    _declare(store, ["a"], path="../../outside.json", sha=hashlib.sha256(data).hexdigest())
    (only,) = _read(store)["scopes"]
    assert only["state"] == "INVENTORY_UNREADABLE" and only["figures"] is None


def test_screening_outside_the_inventory_is_named(tmp_path):
    store = Store("fixture", base=tmp_path)
    _screen(store, [_assessment("a"), _assessment("b")], ["a", "b"])
    _declare(store, ["a"])
    (only,) = _read(store)["scopes"]
    assert only["state"] == "SCREENING_OUTSIDE_INVENTORY" and only["figures"] is None


def test_an_invalid_screening_ledger_is_named(tmp_path):
    store = Store("fixture", base=tmp_path)
    store.append(selection.SCREENING_LEDGER, {"x": 1})
    _declare(store, ["a"])
    (only,) = _read(store)["scopes"]
    assert only["state"] == "SELECTION_LEDGER_INVALID" and only["figures"] is None


def test_the_read_writes_nothing(tmp_path):
    store = Store("fixture", base=tmp_path)
    keys = ["a", "b"]
    _declare(store, keys)
    _screen(store, [_assessment("a")], keys)
    before = _tree(store.root)
    _read(store)
    _read(store)
    assert _tree(store.root) == before


def _declare_raw(store, content: bytes, *, sha=None):
    base = store.path(selection_view.BASE_DIR)
    (base / "inv").mkdir(parents=True, exist_ok=True)
    (base / "inv" / "inventory.json").write_bytes(content)
    (base / "scopes.json").write_text(json.dumps({"scopes": [{
        "scope_id": "s1", "question_id": "Q1", "round": ROUND,
        "inventory_path": "inv/inventory.json",
        "inventory_sha256": sha or hashlib.sha256(content).hexdigest()}]}))


def test_an_inventory_of_the_wrong_shape_is_unreadable(tmp_path):
    for content in (b"{}", b"[]", b"{not json", b'[1, 2]', b'[{"other": "a"}]'):
        store = Store("fixture", base=tmp_path / content.hex())
        _declare_raw(store, content)
        result = _read(store)
        (only,) = result["scopes"]
        assert only["state"] == "INVENTORY_UNREADABLE" and only["figures"] is None, content
        _assert_advisory(result)


def test_a_nul_byte_in_the_inventory_path_is_unreadable(tmp_path):
    store = Store("fixture", base=tmp_path)
    _declare(store, ["a"], path="inv/\x00.json")
    result = _read(store)
    (only,) = result["scopes"]
    assert only["state"] == "INVENTORY_UNREADABLE" and only["figures"] is None
    _assert_advisory(result)


def test_a_declaration_entry_missing_a_field_invalidates_the_file(tmp_path):
    store = Store("fixture", base=tmp_path)
    path = store.path(selection_view.SCOPES_FILE)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"scopes": [{
        "scope_id": "s1", "question_id": "Q1", "round": ROUND,
        "inventory_path": "inv/inventory.json"}]}))
    result = _read(store)
    assert result["state"] == "SCOPES_FILE_INVALID" and result["scopes"] == []
    _assert_advisory(result)


def test_two_scopes_in_a_round_are_each_reported(tmp_path):
    store = Store("fixture", base=tmp_path)
    _declare(store, ["a", "b"])
    base = store.path(selection_view.BASE_DIR)
    (base / "inv" / "second.json").write_bytes(b'[{"candidate_key": "z"}]')
    declared = json.loads((base / "scopes.json").read_text())
    declared["scopes"].append({
        "scope_id": "s2", "question_id": "Q2", "round": ROUND,
        "inventory_path": "inv/second.json", "inventory_sha256": "0" * 64})
    (base / "scopes.json").write_text(json.dumps(declared))
    result = _read(store)
    first, second = result["scopes"]
    assert (first["scope_id"], first["state"]) == ("s1", "OK")
    assert first["figures"]["inventory_count"] == 2
    assert (second["scope_id"], second["state"]) == ("s2", "INVENTORY_DRIFTED")
    assert second["figures"] is None
    _assert_advisory(result)


def test_an_identity_observation_is_counted(tmp_path):
    store = Store("fixture", base=tmp_path)
    keys = ["a", "b"]
    row = selection.identified({
        "selection_version": selection.IDENTITY_RELATION_VERSION,
        "scope_id": "s1", "candidate_key": "a", "source_class": "UNCLASSIFIED",
        "status": "POSSIBLE_VERSION", "reason": "fixture", "assessed_by": "test agent",
        "metadata_sha256": H, "copy_sha256": H,
        "related_kind": "CANDIDATE", "related_key": "b",
        "observations": ["metadata:title A", "copy:title B"], "supersedes": None,
    }, "observation_id")
    _declare(store, keys)
    selection.append_observations(store, [], [row], scope_id="s1", question_id="Q1",
                                  inventory_keys=set(keys))
    result = _read(store)
    (only,) = result["scopes"]
    assert only["state"] == "OK" and only["figures"]["identity_observations"] == 1
    _assert_advisory(result)


def test_a_ledger_line_that_is_not_an_object_is_named(tmp_path):
    for ledger in (selection.SCREENING_LEDGER, selection.IDENTITY_LEDGER):
        for line in ("[]", '"x"', "1"):
            store = Store("fixture", base=tmp_path / ledger / line.encode().hex())
            _declare(store, ["a"])
            with open(store.path(ledger), "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            result = _read(store)
            (only,) = result["scopes"]
            assert only["state"] == "SELECTION_LEDGER_INVALID" and only["figures"] is None
            _assert_advisory(result)


def test_an_identity_row_outside_the_inventory_is_a_ledger_fault(tmp_path):
    store = Store("fixture", base=tmp_path)
    row = selection.identified({
        "selection_version": selection.IDENTITY_RELATION_VERSION,
        "scope_id": "s1", "candidate_key": "z", "source_class": "UNCLASSIFIED",
        "status": "POSSIBLE_VERSION", "reason": "fixture", "assessed_by": "test agent",
        "metadata_sha256": H, "copy_sha256": H,
        "related_kind": "HELD_COPY", "related_key": H,
        "observations": ["metadata:title A", "copy:title B"], "supersedes": None,
    }, "observation_id")
    selection.append_observations(store, [], [row], scope_id="s1", question_id="Q1",
                                  inventory_keys={"a", "z"})
    _declare(store, ["a"])
    (only,) = _read(store)["scopes"]
    assert only["state"] == "SELECTION_LEDGER_INVALID" and only["figures"] is None
