"""D158: one work found twice is counted once, and nothing is rewritten."""
from claimstone import evidence, works
from claimstone.config import Question

Q = Question(id="Q01", text="Does exercise reduce depressive symptoms?", kind="effect")
TITLE = "Reduced serum adiponectin and exercise predict depression in chronic heart failure patients"


def candidate(key, title):
    return {"candidate_key": key, "title": title}


def claim(claim_id, source_id, stance="SUPPORTS"):
    return {"claim_id": claim_id, "question_id": "Q01", "stance": stance, "claim": "x",
            "evidence_quote": "x", "source_id": source_id, "source_class": "ACA"}


def reviewed(*ids):
    return {i: {"claim_id": i, "verdict": "SUPPORTED"} for i in ids}


def test_a_doi_and_a_title_candidate_with_the_same_folded_title_are_one_work():
    rows = [candidate("doi:10.3389/x", TITLE), candidate("title:" + TITLE.lower(), TITLE.upper() + ".")]
    found = works.groups(rows, ["doi:10.3389/x", "title:" + TITLE.lower()])
    assert [g["work"] for g in found] == ["doi:10.3389/x"]
    assert found[0]["basis"] == works.BASIS_TITLE_EQUAL
    assert works.work_of(rows, ["doi:10.3389/x", "title:" + TITLE.lower()]) == {
        "title:" + TITLE.lower(): "doi:10.3389/x"}


def test_a_short_or_merely_similar_title_is_never_a_group():
    rows = [candidate("doi:a", "Introduction"), candidate("title:introduction", "Introduction"),
            candidate("doi:b", TITLE), candidate("title:other", TITLE + " a secondary analysis")]
    assert works.groups(rows, ["doi:a", "title:introduction", "doi:b", "title:other"]) == []


def test_a_group_only_counts_sources_that_are_in_the_question():
    rows = [candidate("doi:b", TITLE), candidate("title:b", TITLE)]
    assert works.groups(rows, ["doi:b"]) == []


def test_the_second_copy_is_listed_marked_and_not_counted():
    claims = [claim("c1", "doi:b"), claim("c2", "title:b"), claim("c3", "doi:z", "CONTRADICTS")]
    built = evidence.profile(Q, claims=claims, reviews=reviewed("c1", "c2", "c3"),
                             work_of={"title:b": "doi:b"},
                             work_groups=[{"work": "doi:b", "members": ["doi:b", "title:b"],
                                           "basis": "title_equal"}])
    assert built["direction_count"] == {"CONTRADICTS": 1, "SUPPORTS": 1}
    assert built["sources"] == ["doi:b", "doi:z"] and built["coverage"]["sources"] == 2
    listed = {r["claim_id"]: r.get("same_work_as") for r in built["results"]}
    assert listed == {"c1": None, "c2": "doi:b", "c3": None}
    assert built["work_groups"][0]["members"] == ["doi:b", "title:b"]


def test_a_profile_without_a_group_gains_no_key():
    built = evidence.profile(Q, claims=[claim("c1", "doi:b")], reviews=reviewed("c1"))
    assert "work_groups" not in built and "same_work_as" not in built["results"][0]
