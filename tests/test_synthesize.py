"""Stage 6: profiles, the two refusals, and the fact that no verdict comes from here.

The first version of this stage applied a verdict rule automatically. A review established the rule was
vote counting with a threshold, so the work split in two and this module implements layer 1 only.
"""

import pytest

from claimstone import admissibility, claimgate, evidence, extract, model_call, synthesize
from claimstone.config import Project, Question, SourceClass
from claimstone.store import Store
from claimstone.review import REVIEW_VERSION
from tests.test_admissibility import _ledger, row

QUESTIONS = (
    Question(id="H02", text="News carries information about future returns.", kind="effect"),
    Question(id="H06", text="The effect is stronger for small firms.", kind="heterogeneity"),
    Question(id="H11", text="Two lanes stay parallel.", kind="operational"),
)


def _project(tmp_path, floor=0.5):
    return Project(
        name="t", root=tmp_path, acquisition_floor=floor, excluded_hosts=(),
        classes=(SourceClass(id="ACA", name="refereed", weight_hint="high", role="empirical"),
                 SourceClass(id="MET", name="methods", weight_hint="high",
                             role="methodological")),
        topics=(), questions=QUESTIONS, registry_version=3, frozen_at="2026-09-25",
        registry_sha256="deadbeef",
    )


def claim(**overrides):
    base = {"claim_gate_version": claimgate.CLAIM_GATE_VERSION, "registry_version": 3, "claim_id": "c1", "question_id": "H02", "stance": "SUPPORTS",
            "claim": "News tone affects returns.", "evidence_quote": "news tone has an effect",
            "chunk_id": "ACA001#c1", "source_id": "ACA001", "source_class": "ACA",
            "estimate": 0.024, "estimate_as_written": "2.4%", "sample": "US equities"}
    return {**base, **overrides}


def _store(tmp_path, *, obtained=2, found=2, claims=(), reviews=(), final=True):
    store = Store("t", base=tmp_path)
    source_ids = ["ACA001", "MET001"] + [f"s{i}" for i in range(2, found)]
    rows = [row(source_ids[i], acquired=i < obtained) for i in range(found)]
    for r in rows:
        if not r["acquired"]:
            r["failure_class"] = "PAYWALL_403"
    _ledger(store, rows)
    if final:
        # A round is final only when nothing is outstanding, and an obtained source with no stage 3
        # verdict is outstanding. Without these every profile is provisional and nothing is adjudicable,
        # which is correct behaviour and makes for a useless fixture.
        for r in rows:
            if r["acquired"]:
                store.append("documents.jsonl", {"source_id": r["candidate_key"],
                                                 "fulltext_confirmed": True})
    store.append("chunks.jsonl", {"chunk_id": "ACA001#c1", "source_id": "ACA001",
                                  "text": "news tone has an effect", "kind": "prose"})
    for r in rows:
        if r["acquired"] and r["candidate_key"] != "ACA001":
            store.append("chunks.jsonl", {"source_id": r["candidate_key"],
                         "chunk_id": r["candidate_key"] + "#c1", "kind": "prose",
                         "text": "news tone has an effect"})
    if final:
        extract.build(_project(tmp_path), store, batch="production")
        queue = model_call.Queue(store, lane="extract", batch="production")
        for unit in queue.requests():
            store.append(queue.results_name, {"call_id": unit["call_id"],
                         "backend": "b", "model": "m", "ok": True, "output": []})
    for c in claims:
        store.append("claims.jsonl", c)
    for r in reviews:
        store.append("reviews.jsonl", r)
    return store


def review(claim_id="c1", verdict="SUPPORTED"):
    return {"claim_id": claim_id, "question_id": "H02", "verdict": verdict, "review_version": REVIEW_VERSION,
            "reviewed_by": {"backend": "b", "model": "m"}}


# --- the first refusal: invariant 3 ---------------------------------------------------------------

def test_an_inadmissible_round_produces_no_profiles_at_all(tmp_path):
    """Not a partial run and not a warning. A corpus read below its floor that certifies itself
    complete is worse than no corpus, and that is the state that motivated the project."""
    store = _store(tmp_path, obtained=1, found=4, claims=[claim()], reviews=[review()])
    with pytest.raises(synthesize.NotAdmissible):
        synthesize.build(_project(tmp_path, floor=0.8), store)
    assert list(store.read(synthesize.PROFILES)) == []


def test_the_refusal_names_the_rate_and_the_floor_it_missed(tmp_path):
    store = _store(tmp_path, obtained=1, found=4, claims=[claim()], reviews=[review()])
    with pytest.raises(synthesize.NotAdmissible) as raised:
        synthesize.build(_project(tmp_path, floor=0.8), store)
    assert admissibility.INSUFFICIENT in str(raised.value)
    assert "0.8" in str(raised.value)


def test_there_is_no_flag_that_overrides_the_floor():
    """Invariant 3 in the signature: nothing accepted here can waive it."""
    import inspect

    parameters = inspect.signature(synthesize.build).parameters
    assert set(parameters) == {"project", "store", "round_name", "manifest_only"}


# --- profiles -------------------------------------------------------------------------------------

def test_a_profile_is_written_per_question_including_the_operational_one(tmp_path):
    store = _store(tmp_path, claims=[claim()], reviews=[review()])
    result = synthesize.build(_project(tmp_path), store)
    assert result["questions"] == 3
    assert result["profiles"] == 2
    assert result["not_applicable"] == 1
    written = {r["question_id"] for r in store.read(synthesize.PROFILES)}
    assert written == {"H02", "H06", "H11"}


def test_the_operational_question_says_not_applicable_rather_than_a_sixth_state(tmp_path):
    store = _store(tmp_path, claims=[claim()], reviews=[review()])
    synthesize.build(_project(tmp_path), store)
    rows = {r["question_id"]: r for r in store.read(synthesize.PROFILES)}
    assert rows["H11"]["state"] == evidence.NOT_APPLICABLE
    assert rows["H11"]["state"] not in synthesize.VERDICTS


def test_a_question_nothing_survived_for_is_no_verified_claim(tmp_path):
    store = _store(tmp_path, claims=[claim()], reviews=[review()])
    synthesize.build(_project(tmp_path), store)
    rows = {r["question_id"]: r for r in store.read(synthesize.PROFILES)}
    assert rows["H06"]["state"] == evidence.NO_VERIFIED_CLAIM
    assert rows["H02"]["state"] is None


def test_an_unreviewed_claim_makes_its_profile_provisional(tmp_path):
    store = _store(tmp_path, claims=[claim(), claim(claim_id="c2")], reviews=[review()])
    result = synthesize.build(_project(tmp_path), store)
    rows = {r["question_id"]: r for r in store.read(synthesize.PROFILES)}
    assert rows["H02"]["provisional"] is True
    assert result["provisional"] >= 1


def test_a_non_final_round_marks_every_profile_provisional(tmp_path):
    """`admit` reports final: False while anything is outstanding, and a profile from an incomplete
    corpus is a profile that can still change."""
    store = _store(tmp_path, claims=[claim()], reviews=[review()])
    # An acquisition with no candidate behind it: the round is not settled.
    store.append("acquisitions.jsonl", {"candidate_key": "orphan", "acquired": True,
                                        "source_class": "ACA", "url": "https://x.example/o"})
    store.append("documents.jsonl", {"source_id": "orphan", "fulltext_confirmed": True})
    result = synthesize.build(_project(tmp_path), store)
    assert result["final"] is False
    assert all(r["provisional"] for r in store.read(synthesize.PROFILES)
               if r.get("kind") in evidence.FIELDS_BY_KIND)


def test_all_three_identities_are_on_every_profile(tmp_path):
    store = _store(tmp_path, claims=[claim()], reviews=[review()])
    synthesize.build(_project(tmp_path), store)
    for built in store.read(synthesize.PROFILES):
        if built.get("kind") not in evidence.FIELDS_BY_KIND:
            continue
        assert built["registry_version"] == 3
        assert built["registry_sha256"] == "deadbeef"
        assert built["decision_contract_version"] == 1


def test_the_declared_role_reaches_a_result_from_the_project_and_not_from_the_class_id(tmp_path):
    method = claim(claim_id="c9", question_id="H06", source_class="MET", source_id="MET001")
    store = _store(tmp_path, claims=[method],
                   reviews=[review(claim_id="c9") | {"question_id": "H06"}])
    synthesize.build(_project(tmp_path), store)
    rows = {r["question_id"]: r for r in store.read(synthesize.PROFILES)}
    assert rows["H06"]["results"][0]["role"] == "methodological"


def test_the_disclosure_is_reported_and_is_not_a_correction(tmp_path):
    """These rules test no significance, so there is no family-wise error rate to control. Disclosure
    is mandatory; a Benjamini-Hochberg adjustment over count-based rules would adjust nothing."""
    store = _store(tmp_path, claims=[claim()], reviews=[review()])
    result = synthesize.build(_project(tmp_path), store)
    assert result["no_controlled_error_rate_across"] == 2
    assert not any("correct" in key for key in result)


def _identifiers(module):
    """Every name the module's code uses, with prose excluded.

    Grepping the source text instead matches the docstrings, which *discuss* thresholds at length — and
    a test that fails because a comment explains why there is no threshold is a test that will be
    deleted rather than fixed.
    """
    import ast
    import inspect

    names: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value)
    return names


def test_the_module_holds_no_threshold_that_decides_a_verdict():
    """Reintroducing an automatic SUPPORTED should mean arguing with the verdict contract, not quietly
    shipping a constant."""
    names = _identifiers(synthesize) | _identifiers(evidence)
    for forbidden in ("min_studies", "min_distinct_data_sources", "min_sources",
                      "distinct_data_sources", "verdict_threshold"):
        assert forbidden not in names, forbidden


def test_no_verdict_is_ever_assigned_by_these_modules():
    """The four states beyond SUPPORTED appear only in the declared vocabulary, never as an outcome."""
    import ast
    import inspect

    assigned: set[str] = set()
    for module in (synthesize, evidence):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            # A string constant anywhere except the VERDICTS tuple itself.
            if not isinstance(node, ast.Assign):
                continue
            targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if "VERDICTS" in targets:
                continue
            for inner in ast.walk(node.value):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    assigned.add(inner.value)
    for verdict in ("CONTRADICTED", "CONTESTED_IN_LITERATURE", "UNANSWERED_IN_LITERATURE",
                    "NEVER_ASKED"):
        assert verdict not in assigned, verdict


def test_the_cli_verdict_list_matches_the_real_vocabulary():
    """The parser names them itself so building help imports no stage module; this pins the copy."""
    from claimstone import cli

    assert cli.VERDICT_NAMES == synthesize.VERDICTS


def test_no_model_and_no_network_in_stage_six():
    import inspect

    names = _identifiers(synthesize) | _identifiers(evidence)
    for forbidden in ("requests", "urllib", "model_call", "runners", "subprocess", "socket"):
        assert forbidden not in names, forbidden
