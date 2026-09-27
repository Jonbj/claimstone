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


# The forms below are all taken from the first full extraction round on `alembic-s4`, where they were
# 183 refusals. Each one is a notation the literature uses, not a bad claim.

def test_a_label_is_stripped_to_reach_the_figure_and_never_read_as_the_quantity():
    value = numbers.parse("t-statistic of 2.7")
    assert value.value == 2.7
    # `as_reported`, not `t_statistic`: what the quantity is remains an estimand question, and the
    # label stays in the as-written form for a reader.
    assert value.scale == "as_reported"
    assert value.as_written == "t-statistic of 2.7"


def test_a_bracketed_standard_error_notation_is_read_and_still_only_flagged_as_bracketed():
    value = numbers.parse("(se = 1.20)")
    assert (value.value, value.bracketed, value.scale) == (1.20, True, "as_reported")


def test_a_hedge_is_recorded_as_the_bound_it_states_rather_than_dropped():
    assert numbers.parse("over 300%").bound == "lower"
    assert numbers.parse("all below 65%").bound == "upper"
    assert numbers.parse("nearly 6%").bound == "approximate"
    assert numbers.parse("∼100%").bound == "approximate"
    # The figure is still the figure.
    assert numbers.parse("over 300%").value == 3.0


def test_a_bare_figure_is_exact_and_the_bound_is_never_guessed_from_the_magnitude():
    assert numbers.parse("2.4%").bound == "exact"


def test_approaching_is_approximate_because_the_word_does_not_settle_a_direction():
    assert numbers.parse("approaching 1 percent").bound == "approximate"


def test_a_period_belongs_to_the_horizon_and_does_not_stop_the_figure_being_read():
    assert numbers.parse("0.55% per month").value == pytest.approx(0.0055)
    assert numbers.parse("3.75% per annum").value == pytest.approx(0.0375)


def test_a_gloss_inside_a_period_is_still_reached():
    # `5.2 basis points (bps) per day` puts the bracketed gloss inside the period, so one pass in
    # either order leaves the other in place.
    assert numbers.parse("5.2 basis points (bps) per day").value == pytest.approx(0.00052)


def test_a_significance_level_is_still_refused_because_it_is_not_a_magnitude():
    with pytest.raises(numbers.Unparseable):
        numbers.parse("significant at the 1% level")


def test_a_contrast_is_two_sides_in_the_order_written_and_no_difference_is_taken():
    first, second = numbers.parse_contrast("2.00% versus 0.14%")
    assert (first.value, second.value) == pytest.approx((0.02, 0.0014))


def test_a_contrast_whose_sides_are_on_different_scales_is_refused():
    with pytest.raises(numbers.Unparseable) as raised:
        numbers.parse_contrast("2.00% versus 0.14")
    assert "not on one scale" in str(raised.value)


def test_a_contrast_is_not_put_through_the_one_value_path():
    # It holds two numbers by construction, which is what stage 4 asks for.
    assert "contrast_as_written" not in numbers.NUMERIC_FIELDS
    assert "contrast_as_written" in numbers.COMPOSITE_FIELDS


def test_convert_reads_a_contrast_into_two_sides_and_a_shared_scale():
    out, problems = numbers.convert({"contrast_as_written": "22.42 versus 0.16"})
    assert problems == []
    assert out["contrast_sides"] == [22.42, 0.16]
    assert out["contrast_scale"] == "as_reported"


def test_convert_records_a_bound_only_when_there_is_one():
    out, _ = numbers.convert({"estimate_as_written": "over 300%"})
    assert out["estimate_bound"] == "lower"
    plain, _ = numbers.convert({"estimate_as_written": "2.4%"})
    assert "estimate_bound" not in plain


def test_only_the_estimate_is_required_to_convert():
    # The claim's own figure. Everything else is auxiliary, and losing the claim over a notation the
    # engine does not read would also lose it from the coverage denominator.
    assert numbers.FIELDS_REQUIRED_TO_CONVERT == ("estimate_as_written",)


# --- the vocabulary is project data ---------------------------------------------------------------
# This list shipped with `sharpe` and without `OR`, so the finance corpus parsed and the epidemiology
# corpus refused 63 estimates over `AOR=1.66` and `ß = -.22`. A list of a discipline's notations inside
# `claimstone/` is the domain knowledge invariant 4 forbids.

EPIDEMIOLOGY = numbers.DEFAULT_VALUE_LABELS + ("AOR", "OR", "RR", "HR", "ß", "beta")


def test_the_engine_knows_no_discipline_s_labels():
    folded = {label.lower() for label in numbers.DEFAULT_VALUE_LABELS}
    for owned in ("sharpe", "sharpe ratio", "aor", "or", "hazard ratio", "cohen's d"):
        assert owned not in folded, owned
    # What stays is what any quantitative field writes.
    for generic in ("t", "se", "sd", "p", "mean", "median", "n"):
        assert generic in folded, generic


def test_a_declared_label_is_read_and_an_undeclared_one_is_not():
    with pytest.raises(numbers.Unparseable):
        numbers.parse("AOR=1.66")
    assert numbers.parse("AOR=1.66", labels=EPIDEMIOLOGY).value == 1.66


def test_a_bare_leading_decimal_is_a_number():
    """`ß = -.22` and `p < .01` are how psychology and epidemiology write a coefficient and a level."""
    assert numbers.parse(".22").value == 0.22
    assert numbers.parse("-.18").value == -0.18
    assert numbers.parse("−.22").value == -0.22


def test_an_inequality_symbol_is_a_bound():
    assert numbers.parse("< .05").bound == "upper"
    assert numbers.parse("≥ 3").bound == "lower"


def test_a_label_and_a_bound_are_read_in_either_order():
    """`p < .01` is a label then a bound; `< .05` is a bound alone. A fixed order reads one and refuses
    the other."""
    value = numbers.parse("p < .01")
    assert (value.value, value.bound) == (0.01, "upper")


def test_a_one_letter_label_does_not_eat_the_start_of_a_word():
    """`n` took the `n` of `nearly 6%` and left `early 6%`, which broke a hedge that had been parsing."""
    assert numbers.parse("nearly 6%").value == pytest.approx(0.06)
    assert numbers.parse("n = 1297").value == 1297
