"""D138: a title keeps its letters in every script, and a Latin title does not move."""

import pytest

from claimstone import ids


def test_non_latin_titles_sharing_only_a_year_stay_distinct():
    a = ids.candidate_key(doi=None, title="抑郁症 2024", url="https://a.example/1")
    b = ids.candidate_key(doi=None, title="运动 2024", url="https://b.example/2")
    assert a != b
    assert a != "title:2024" and b != "title:2024"


@pytest.mark.parametrize("title", [
    "Депрессия и спорт", "قياس الاكتئاب 2021", "がん と ガン 2020", "우울증 연구 2022", "דיכאון ופעילות גופנית",
])
def test_every_script_survives_as_a_key(title):
    folded = ids.normalize_title(title)
    assert folded and any(not c.isascii() for c in folded)


def test_kana_voicing_and_arabic_hamza_are_not_stripped():
    assert ids.normalize_title("がん") == "がん"
    assert ids.normalize_title("الاكتئاب") == "الاكتئاب"


@pytest.mark.parametrize("title, expected", [
    ("Résumé études 2024", "resume etudes 2024"),
    ("COVID-19: a review", "covid 19 a review"),
    ("Ça va, ñandú", "ca va nandu"),
    ("Foo_bar (baz)!", "foo bar baz"),
    ("  Spaced   out  ", "spaced out"),
])
def test_latin_titles_fold_as_they_did_under_version_2(title, expected):
    assert ids.normalize_title(title) == expected


def test_the_version_names_this_rule():
    assert ids.CANDIDATE_KEY_VERSION == 3
