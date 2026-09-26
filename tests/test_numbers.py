"""An as-written form into a value and a scale. Pure, and it refuses rather than guessing."""

import pytest

from claimstone import numbers


def test_a_percentage_becomes_a_fraction_and_says_so():
    assert numbers.parse("2.4%") == numbers.Value(0.024, "fraction", "2.4%")


def test_basis_points_become_a_fraction():
    assert numbers.parse("13.3 bps").value == pytest.approx(0.00133)
    assert numbers.parse("5.2 basis points").value == pytest.approx(0.00052)


def test_a_bare_number_keeps_its_own_scale_because_nothing_says_otherwise():
    """`0.024` may be a fraction, a coefficient or a t-statistic, and the engine does not know which.
    Calling it a fraction would be the guess this module exists to refuse."""
    assert numbers.parse("0.024") == numbers.Value(0.024, "as_reported", "0.024")


def test_a_parenthesised_value_is_unwrapped_and_flagged_as_bracketed():
    """A paper's convention. Whether the bracket holds a standard error or a t-statistic is an
    estimand question and this module does not reach it — it records that it was bracketed."""
    parsed = numbers.parse("(0.008)")
    assert parsed.value == pytest.approx(0.008)
    assert parsed.scale == "as_reported"
    assert parsed.bracketed is True


def test_a_unicode_minus_is_a_sign():
    assert numbers.parse("−1.7%").value == pytest.approx(-0.017)


def test_thousands_separators_are_removed():
    assert numbers.parse("1,250").value == pytest.approx(1250.0)


def test_scientific_notation_is_read():
    assert numbers.parse("1.4e-3").value == pytest.approx(0.0014)


def test_a_percentage_point_is_not_a_percentage():
    """`2.4 pp` is a difference of two percentages and converting it as one would halve nothing and
    mislabel everything. It is a fraction, and the distinction is recorded in the scale."""
    parsed = numbers.parse("2.4 pp")
    assert parsed.value == pytest.approx(0.024)
    assert parsed.scale == "fraction_difference"


def test_a_notation_it_does_not_understand_is_refused_rather_than_nulled():
    """`UNPARSEABLE_VALUE` is a recorded rejection. A null would read as "no estimate reported",
    which is a claim about the paper that a parser failure has not earned."""
    with pytest.raises(numbers.Unparseable, match="two-thirds"):
        numbers.parse("two-thirds")


def test_an_empty_form_is_refused_too():
    with pytest.raises(numbers.Unparseable):
        numbers.parse("")


def test_a_range_is_refused_because_it_is_two_values():
    with pytest.raises(numbers.Unparseable, match="range"):
        numbers.parse("2.4% to 3.1%")


def test_a_form_with_no_digits_at_all_is_refused():
    with pytest.raises(numbers.Unparseable):
        numbers.parse("significant")


def test_the_as_written_form_is_carried_so_the_gate_can_still_check_it():
    assert numbers.parse("2.4%").as_written == "2.4%"


def test_convert_adds_the_engine_fields_and_never_touches_the_model_fields():
    record = {"question_id": "H02", "estimate_as_written": "2.4%",
              "uncertainty_as_written": "(0.008)", "claim": "c", "evidence_quote": "q"}
    out, problems = numbers.convert(record)
    assert problems == []
    assert out["estimate"] == pytest.approx(0.024)
    assert out["estimate_scale"] == "fraction"
    assert out["uncertainty"] == pytest.approx(0.008)
    assert out["uncertainty_bracketed"] is True
    # The as-written forms are untouched: the gate checks them against the quote.
    assert out["estimate_as_written"] == "2.4%"


def test_convert_reports_what_it_could_not_read_rather_than_raising():
    record = {"question_id": "H02", "estimate_as_written": "two-thirds"}
    out, problems = numbers.convert(record)
    assert "estimate_as_written" in problems[0]
    assert "estimate" not in out


def test_convert_ignores_a_field_that_is_not_an_as_written_form():
    record = {"question_id": "H02", "horizon_as_written": "one week", "claim": "c"}
    out, problems = numbers.convert(record)
    # A horizon is not a number and is not converted; it is also not a failure.
    assert problems == []
    assert "horizon" not in out
