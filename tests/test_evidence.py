"""Layer 1: everything known, nothing concluded. Pure — no store, no clock, no network."""

import pytest

from claimstone import evidence
from claimstone.config import Question

H02 = Question(id="H02", text="News carries information about future returns.", kind="effect")
H06 = Question(id="H06", text="The effect is stronger for small firms.", kind="heterogeneity")
H09 = Question(id="H09", text="The event is the unit of inference.", kind="method")
H11 = Question(id="H11", text="Two lanes stay parallel.", kind="operational")


def claim(**overrides):
    base = {"claim_id": "c1", "question_id": "H02", "stance": "SUPPORTS",
            "claim": "News tone affects returns.", "evidence_quote": "news tone has an effect",
            "source_id": "ACA001", "source_class": "ACA",
            "estimate": 0.024, "estimate_scale": "fraction", "estimate_as_written": "2.4%",
            "uncertainty_as_written": "(0.008)", "horizon_as_written": "one week",
            "sample": "US equities 1996-2008", "design": "panel regression",
            "dependence": "clustered by firm and week"}
    return {**base, **overrides}


def reviewed(*claim_ids, verdict="SUPPORTED"):
    return {cid: {"claim_id": cid, "verdict": verdict} for cid in claim_ids}


def test_a_verified_result_carries_the_fields_stage_four_extracted():
    """Not a subset of them: a reader deciding a verdict needs the estimand."""
    built = evidence.profile(H02, claims=[claim()], reviews=reviewed("c1"))
    result = built["results"][0]
    for field in ("estimate", "estimate_scale", "uncertainty_as_written", "horizon_as_written",
                  "sample", "design", "dependence", "evidence_quote"):
        assert field in result, field


def test_a_contrary_result_carries_the_same_fields_as_an_agreeing_one():
    """A profile showing only the agreeing side is a selection presented as a description, and what it
    hides is a verdict resting on vendor research that refereed work disagrees with."""
    against = claim(claim_id="c2", stance="CONTRADICTS", source_id="IND001", source_class="IND",
                    estimate=-0.003, estimate_as_written="-0.3%")
    built = evidence.profile(H02, claims=[claim(), against], reviews=reviewed("c1", "c2"))
    agreeing, contrary = (r for r in sorted(built["results"], key=lambda r: r["source_id"]))
    assert contrary["stance"] == "CONTRADICTS"
    assert set(agreeing) - {"role"} == set(contrary) - {"role"}


def test_the_direction_count_is_a_count_and_lives_under_that_name():
    claims = [claim(), claim(claim_id="c2", source_id="ACA002"),
              claim(claim_id="c3", stance="CONTRADICTS", source_id="ACA003")]
    built = evidence.profile(H02, claims=claims, reviews=reviewed("c1", "c2", "c3"))
    assert built["direction_count"] == {"CONTRADICTS": 1, "SUPPORTS": 2}


def test_qualifies_counts_on_neither_side_of_by_class():
    """It is a claim that the effect holds under conditions, and putting it on a side would be this
    module deciding what the adjudicator is there to decide."""
    claims = [claim(), claim(claim_id="c2", stance="QUALIFIES", source_id="WP001",
                             source_class="WP")]
    built = evidence.profile(H02, claims=claims, reviews=reviewed("c1", "c2"))
    assert built["by_class"]["against"] == {}
    # It is still a result, and still in the count.
    assert built["direction_count"]["QUALIFIES"] == 1
    assert len(built["results"]) == 2


def test_by_class_splits_for_and_against_separately():
    against = claim(claim_id="c2", stance="CONTRADICTS", source_id="IND001", source_class="IND")
    built = evidence.profile(H02, claims=[claim(), against], reviews=reviewed("c1", "c2"))
    assert built["by_class"] == {"for": {"ACA": 1}, "against": {"IND": 1}}


def test_linkage_is_always_unestablished_and_labels_are_verbatim():
    """No string comparison establishes a dataset. Two spellings of one dataset pass a distinct-count;
    one broad label hides two."""
    same = claim(claim_id="c2", source_id="ACA002", sample="US equities 1996-2008")
    other = claim(claim_id="c3", source_id="ACA003", sample="CRSP 1993-2010")
    built = evidence.profile(H02, claims=[claim(), same, other], reviews=reviewed("c1", "c2", "c3"))
    assert built["linkage"] == "unestablished"
    assert built["sample_labels"] == ["CRSP 1993-2010", "US equities 1996-2008"]
    assert "distinct_samples" not in built
    assert "distinct_data_sources" not in built


def test_coverage_counts_sources_not_claims():
    """Two claims from one source is one source. Counting claims would be vote counting with steps."""
    twice = claim(claim_id="c2", evidence_quote="another span")
    built = evidence.profile(H02, claims=[claim(), twice], reviews=reviewed("c1", "c2"),
                            examined=14)
    assert built["coverage"] == {"sources": 1, "examined": 14}


def test_only_a_claim_a_reader_passed_reaches_the_profile():
    overstated = claim(claim_id="c2", source_id="ACA002")
    reviews = {**reviewed("c1"), **reviewed("c2", verdict="OVERSTATED")}
    built = evidence.profile(H02, claims=[claim(), overstated], reviews=reviews)
    assert [r["claim_id"] for r in built["results"]] == ["c1"]
    # Counted and shown, never used and never hidden.
    assert built["reviewed_not_usable"] == {"OVERSTATED": 1}


def test_an_unreviewed_claim_is_awaiting_and_makes_the_profile_provisional():
    """Counting it as supported gives the rules an input nobody checked; counting it as unsupported makes
    a verdict fall because stage 5 had not finished."""
    built = evidence.profile(H02, claims=[claim(), claim(claim_id="c2")], reviews=reviewed("c1"))
    assert built["awaiting_review"] == 1
    assert built["provisional"] is True
    assert "awaiting_review" in built["blocking"]


def test_nothing_surviving_is_no_verified_claim_and_never_never_asked():
    """`NEVER_ASKED` asserts nobody asked, and an extraction miss, an all-rejected question and a
    genuinely unasked one look identical from here. Only screening tells them apart."""
    built = evidence.profile(H02, claims=[], reviews={})
    assert built["state"] == evidence.NO_VERIFIED_CLAIM
    assert built["state"] != "NEVER_ASKED"


def test_a_profile_with_results_has_no_state_at_all():
    assert evidence.profile(H02, claims=[claim()], reviews=reviewed("c1"))["state"] is None


def test_rejections_are_attributed_to_the_right_question_by_reason():
    rejections = [
        {"failure": "QUOTE_NOT_FOUND", "record": {"question_id": "H02"}},
        {"failure": "QUOTE_NOT_FOUND", "record": {"question_id": "H02"}},
        {"failure": "NUMBER_NOT_IN_QUOTE", "record": {"question_id": "H02"}},
        {"failure": "QUOTE_NOT_FOUND", "record": {"question_id": "H06"}},
    ]
    built = evidence.profile(H02, claims=[claim()], reviews=reviewed("c1"),
                            rejections=rejections)
    assert built["gate_rejected"] == {"QUOTE_NOT_FOUND": 2, "NUMBER_NOT_IN_QUOTE": 1}


def test_a_heterogeneity_profile_carries_the_contrast_and_whether_it_was_prespecified():
    """An absent case is neither necessary nor sufficient for moderation: an effect can differ
    materially between two subgroups that are both non-zero. A contrast is what establishes it."""
    row = {"claim_id": "c1", "question_id": "H06", "stance": "SUPPORTS", "claim": "Stronger small.",
           "evidence_quote": "0.31% versus 0.04%", "source_id": "ACA001", "source_class": "ACA",
           "moderator": "size", "high_side": "small firms", "low_side": "large firms",
           "contrast_as_written": "0.31% versus 0.04%", "contrast_sides": [0.0031, 0.0004],
           "contrast_uncertainty_as_written": "(t = 3.4)", "prespecified": False}
    built = evidence.profile(H06, claims=[row], reviews=reviewed("c1"))
    result = built["results"][0]
    assert result["contrast_sides"] == [0.0031, 0.0004]
    assert result["contrast_uncertainty_as_written"] == "(t = 3.4)"
    assert result["prespecified"] is False


def test_a_method_result_carries_its_sources_declared_role_and_never_infers_it():
    """Which classes are methodological is project data. Reading it off the class id `MET` would be
    domain knowledge in the engine, which invariant 4 forbids."""
    row = {"claim_id": "c1", "question_id": "H09", "stance": "SUPPORTS", "claim": "Event studies.",
           "evidence_quote": "the event is the unit", "source_id": "MET001", "source_class": "MET",
           "support_type": "ENDORSEMENT"}
    built = evidence.profile(H09, claims=[row], reviews=reviewed("c1"),
                            roles={"MET": "methodological"})
    assert built["results"][0]["role"] == "methodological"
    # No role declared, no role claimed.
    bare = evidence.profile(H09, claims=[row], reviews=reviewed("c1"))
    assert "role" not in bare["results"][0]


def test_an_unconverted_field_travels_so_stage_six_knows_not_to_pool_it():
    row = claim(unconverted=["uncertainty_as_written"])
    built = evidence.profile(H02, claims=[row], reviews=reviewed("c1"))
    assert built["results"][0]["unconverted"] == ["uncertainty_as_written"]


def test_claims_for_another_question_are_not_in_this_profile():
    other = claim(claim_id="c2", question_id="H06")
    built = evidence.profile(H02, claims=[claim(), other], reviews=reviewed("c1", "c2"))
    assert [r["claim_id"] for r in built["results"]] == ["c1"]


def test_an_operational_question_gets_a_row_rather_than_a_silence():
    """Omitting it would make the registry and the report disagree on how many questions exist, and
    "one verdict per question" is the contract."""
    row = evidence.not_applicable(H11, see=("H26",))
    assert row["state"] == evidence.NOT_APPLICABLE
    assert row["see"] == ["H26"]
    assert "results" not in row


def test_the_hash_covers_the_evidence_and_not_the_clock():
    """An adjudication records the hash it was shown, so a rebuild at a later minute must not make every
    recorded verdict stale overnight."""
    first = evidence.profile(H02, claims=[claim()], reviews=reviewed("c1"))
    again = evidence.profile(H02, claims=[claim()], reviews=reviewed("c1"))
    assert first["profile_sha256"] == again["profile_sha256"]
    changed = evidence.profile(H02, claims=[claim(estimate=0.031)], reviews=reviewed("c1"))
    assert changed["profile_sha256"] != first["profile_sha256"]


def test_the_result_order_does_not_change_the_hash():
    a, b = claim(), claim(claim_id="c2", source_id="ACA002")
    one = evidence.profile(H02, claims=[a, b], reviews=reviewed("c1", "c2"))
    two = evidence.profile(H02, claims=[b, a], reviews=reviewed("c1", "c2"))
    assert one["profile_sha256"] == two["profile_sha256"]


def test_the_three_identities_ride_on_every_profile():
    """A profile is a statement about a question at a registry version under a decision contract, and
    two are comparable only when all three agree."""
    built = evidence.profile(H02, claims=[claim()], reviews=reviewed("c1"),
                            registry_version=3, registry_sha256="abc",
                            decision_contract_version=1)
    assert built["registry_version"] == 3
    assert built["registry_sha256"] == "abc"
    assert built["decision_contract_version"] == 1


def test_no_verdict_word_appears_in_a_profile():
    """Layer 1 emits none, and the vocabulary belongs to layer 2."""
    built = evidence.profile(H02, claims=[claim()], reviews=reviewed("c1"))
    rendered = repr(built)
    for verdict in ("CONTRADICTED", "CONTESTED_IN_LITERATURE", "UNANSWERED_IN_LITERATURE",
                    "NEVER_ASKED"):
        assert verdict not in rendered
