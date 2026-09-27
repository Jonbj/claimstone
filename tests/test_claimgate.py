"""Invariant 1, executable. A record and a chunk text in, a verdict out — no store, no network."""

import pytest

from claimstone import claimgate
from claimstone.config import Question

QUESTIONS = (
    Question(id="H02", text="News carries information about future returns.", kind="effect"),
    Question(id="H05", text="The event is the unit of inference.", kind="method"),
    Question(id="H11", text="Two lanes stay parallel.", kind="operational"),
)

CHUNK = (
    "We find that news tone does indeed have an effect on stock returns. "
    "Portfolios formed on this basis earn excess returns for up to 13 weeks, "
    "and the estimate is greater than the no-news benchmark by 4.2 basis points. "
    "Roll (1988) finds little discernible difference."
)


def record(**overrides):
    base = {"question_id": "H02", "stance": "SUPPORTS",
            "claim": "News tone has an effect on stock returns.",
            "evidence_quote": "news tone does indeed have an effect on stock returns"}
    return {**base, **overrides}


def verdict(rec=None, *, chunk=CHUNK, lane="effect", **kw):
    return claimgate.check(rec or record(), chunk=chunk, questions=QUESTIONS, lane=lane, **kw)


def test_a_clean_record_passes():
    assert verdict().ok is True
    assert verdict().failure is None


# --- 1. the question and its kind ----------------------------------------------------------------

def test_an_unknown_question_id_is_refused():
    assert verdict(record(question_id="H99")).failure == "UNKNOWN_QUESTION_ID"


def test_a_question_of_another_kind_is_refused():
    """A method question answered in the effect lane would be judged by the wrong rule later."""
    assert verdict(record(question_id="H05")).failure == "WRONG_KIND"


def test_a_question_that_gets_no_verdict_is_refused_here_too():
    """`operational` questions receive no verdict (invariant 2), so extracting claims for one spends
    calls on an answer nothing will ever read."""
    assert verdict(record(question_id="H11"), lane="operational").failure == "WRONG_KIND"


# --- 2. the quote is in the chunk ----------------------------------------------------------------

def test_a_quote_absent_from_the_chunk_is_refused():
    assert verdict(record(evidence_quote="news tone has a large effect")).failure == "QUOTE_NOT_FOUND"


def test_a_paraphrased_quote_is_refused_however_close():
    # One word changed in the middle. Truncating the end would not test anything: a prefix of the
    # chunk's text is still a substring of it.
    close = "news tone does indeed have an impact on stock returns"
    assert verdict(record(evidence_quote=close)).failure == "QUOTE_NOT_FOUND"


def test_normalised_whitespace_does_not_rescue_a_quote():
    """The chunk's text is byte-for-byte what the model was shown. Re-rendering either side here
    would turn any difference between two renderings into the rejection of a true claim."""
    spaced = "news tone  does indeed have an effect on stock returns"
    assert verdict(record(evidence_quote=spaced)).failure == "QUOTE_NOT_FOUND"


# --- 4. numerals ---------------------------------------------------------------------------------

def test_a_number_in_the_claim_must_be_in_the_quote():
    bad = record(claim="Excess returns persist for up to 17 weeks.",
                 evidence_quote="earn excess returns for up to 13 weeks")
    assert verdict(bad).failure == "NUMBER_NOT_IN_QUOTE"


def test_a_number_present_in_the_quote_passes():
    good = record(claim="Excess returns persist for up to 13 weeks.",
                  evidence_quote="earn excess returns for up to 13 weeks")
    assert verdict(good).ok is True


def test_a_unicode_minus_counts_as_a_numeral():
    chunk = "the coefficient is −1.7 per cent at all lags"
    rec = record(claim="The coefficient is −1.7 per cent.",
                 evidence_quote="the coefficient is −1.7 per cent")
    assert verdict(rec, chunk=chunk).ok is True


def test_a_written_out_number_is_not_checked():
    """The rule exists to stop a fabricated figure, and a fabricated figure is written in digits."""
    rec = record(claim="Returns persist for thirteen weeks.",
                 evidence_quote="earn excess returns for up to 13 weeks")
    assert verdict(rec).ok is True


# --- 5. comparatives by class --------------------------------------------------------------------

def test_a_comparative_class_absent_from_the_quote_is_refused():
    bad = record(claim="The estimate is less than the no-news benchmark.",
                 evidence_quote="the estimate is greater than the no-news benchmark")
    assert verdict(bad).failure == "COMPARATIVE_NOT_IN_QUOTE"


def test_a_synonym_for_a_class_the_quote_contains_is_accepted():
    """`exceeds` against `is greater than` is the same class. Comparing phrases literally would
    reject a correct record for a synonym."""
    good = record(claim="The estimate exceeds the no-news benchmark by 4.2 basis points.",
                  evidence_quote="the estimate is greater than the no-news benchmark by 4.2 basis")
    assert verdict(good).ok is True


def test_a_symbol_is_its_own_class():
    chunk = "the estimate is > the benchmark"
    rec = record(claim="The estimate is greater than the benchmark.",
                 evidence_quote="the estimate is > the benchmark")
    assert verdict(rec, chunk=chunk).ok is True


# --- 6. the stance belongs to the kind -----------------------------------------------------------

def test_a_stance_outside_the_kinds_vocabulary_is_refused():
    assert verdict(record(stance="MAYBE")).failure == "WRONG_STANCE"


def test_a_method_question_may_not_qualify():
    rec = record(question_id="H05", stance="QUALIFIES",
                 claim="The event is the unit of inference.",
                 evidence_quote="news tone does indeed have an effect on stock returns")
    assert verdict(rec, lane="method").failure == "WRONG_STANCE"


# --- the two checks D23 asked for ----------------------------------------------------------------

def test_a_claim_reporting_another_works_finding_is_refused():
    """Measured: the single CONTRADICTS in 66 real claims was `ACA002` citing Roll (1988), a source not
    in the corpus. Without this an unread paper votes, and invariant 7 calls that vote counting."""
    rec = record(
        stance="CONTRADICTS",
        claim="Roll (1988) found little discernible difference in return variation between days "
              "with and without news.",
        evidence_quote="Roll (1988) finds little discernible difference")
    assert verdict(rec).failure == "SECONDHAND_CLAIM"


def test_a_citation_year_is_not_a_figure_the_claim_asserts():
    """Measured: every one of the 4 real claims naming another work would have been rejected as
    NUMBER_NOT_IN_QUOTE for the year in its citation — a false rejection on 6% of a real harvest, by a
    rule whose purpose is to catch a fabricated figure."""
    rec = record(claim="News tone has an effect, as Tetlock (2007) and Loughran and McDonald "
                       "(2011) also report.",
                 evidence_quote="news tone does indeed have an effect on stock returns")
    assert verdict(rec).ok is True


def test_a_claim_merely_mentioning_another_work_is_not_secondhand():
    """`inconsistent with Pound and Zeckhauser (1990)` is this paper's finding, contrasted with
    another's. Rejecting every claim that names a work would discard those."""
    rec = record(
        claim="News tone has an effect on stock returns, inconsistent with Roll (1988).",
        evidence_quote="news tone does indeed have an effect on stock returns")
    assert verdict(rec).ok is True


def test_a_quote_too_short_to_carry_its_claim_is_refused_when_the_project_asks():
    """The check works. It is off by default because the measurement says length is the wrong
    instrument for adequacy — see the threshold's own comment and D25."""
    rec = record(
        claim="News tone has a large, robust and economically meaningful effect on stock returns "
              "across every specification the authors tried.",
        evidence_quote="an effect on stock returns")
    assert verdict(rec, thresholds={"min_quote_ratio": 35}).failure == "QUOTE_TOO_THIN"


def test_the_thinness_check_is_off_by_default():
    """Swept on 66 real claims it rejects nothing from 0 to 34 and one *true* claim at 35, and the case
    it was written for is caught by SECONDHAND_CLAIM instead."""
    rec = record(
        claim="News tone has a large, robust and economically meaningful effect on stock returns "
              "across every specification the authors tried.",
        evidence_quote="an effect on stock returns")
    assert verdict(rec).ok is True


# --- nothing is partially accepted ---------------------------------------------------------------

def test_the_first_failing_check_is_the_one_reported_and_the_record_is_kept_whole():
    rec = record(question_id="H99", evidence_quote="not in the chunk at all")
    result = verdict(rec)
    assert result.failure == "UNKNOWN_QUESTION_ID"
    assert result.record == rec
    assert result.ok is False


def test_every_failure_name_is_declared():
    """So a typo in a check cannot produce a rejection class nothing counts."""
    assert claimgate.FAILURES == (
        "UNKNOWN_QUESTION_ID", "WRONG_KIND", "QUOTE_NOT_FOUND", "VALUE_NOT_IN_QUOTE",
        "NUMBER_NOT_IN_QUOTE", "COMPARATIVE_NOT_IN_QUOTE", "WRONG_STANCE",
        "SECONDHAND_CLAIM", "QUOTE_TOO_THIN", "UNPARSEABLE_VALUE",
    )


def test_an_as_written_value_must_be_in_the_quote():
    rec = record(estimate_as_written="4.2",
                 claim="The estimate is 4.2 basis points.",
                 evidence_quote="the estimate is greater than the no-news benchmark by 4.2 basis")
    assert verdict(rec).ok is True
    bad = {**rec, "estimate_as_written": "5.1"}
    assert verdict(bad).failure == "VALUE_NOT_IN_QUOTE"


# --- What the 66 real claims showed --------------------------------------------------------------
#
# Eight of 66 were rejected and six of the eight were the gate's fault. These are those six.

def test_a_digit_inside_a_hyphenated_word_is_not_a_figure():
    """`day-0` is a name. Reading its 0 as a numeral rejected two true claims whose quotes say `day-0`
    nowhere and had no reason to."""
    chunk = "stocks with the lowest news-event returns outperform the highest by 5.2 basis points"
    rec = record(claim="The day-0 reaction predicts returns, with the lowest outperforming the "
                       "highest by 5.2 basis points.",
                 evidence_quote="lowest news-event returns outperform the highest by 5.2 basis points")
    assert verdict(rec, chunk=chunk).ok is True


def test_a_figure_the_quote_runs_into_a_word_still_counts():
    """The quote reads `reversals-3.7 bps versus 16.7`, which is the typesetting of the paper. Both
    figures are there; extracting the quote's numerals instead of searching it found neither."""
    chunk = ("greater publicity is associated with much smaller return reversals-3.7 bps versus "
             "16.7 bps per day")
    rec = record(claim="Publicity halves the reversal, 3.7 bps versus 16.7 bps per day.",
                 evidence_quote="reversals-3.7 bps versus 16.7 bps per day")
    assert verdict(rec, chunk=chunk).ok is True


def test_a_figure_is_not_matched_inside_a_longer_number():
    """The loosening that substring search invites. A claim of 1.5 against a quote of 11.5 is a
    different figure and must stay a rejection."""
    chunk = "the median variance ratio is 11.5 across the sample"
    rec = record(claim="The median variance ratio is 1.5.",
                 evidence_quote="the median variance ratio is 11.5")
    assert verdict(rec, chunk=chunk).failure == "NUMBER_NOT_IN_QUOTE"


def test_a_sign_flip_is_still_caught():
    chunk = "the coefficient is 1.7 per cent at all lags"
    rec = record(claim="The coefficient is −1.7 per cent.",
                 evidence_quote="the coefficient is 1.7 per cent")
    assert verdict(rec, chunk=chunk).failure == "NUMBER_NOT_IN_QUOTE"


def test_a_comparative_matches_on_a_stem_so_inflections_are_one_class():
    """`above` in the claim against `exceeding` in the quote is one class. A word list of exact forms
    rejected a true claim because it held `exceeds` and not `exceeding`."""
    chunk = ("The result appears quite robust with over 90% of stocks exhibiting variance ratios "
             "exceeding one on identified news days.")
    rec = record(claim="Over 90% of stocks show variance ratios above one.",
                 evidence_quote="over 90% of stocks exhibiting variance ratios exceeding one")
    assert verdict(rec, chunk=chunk).ok is True


def test_an_ambiguous_preposition_is_not_a_comparative():
    """`over 90%` compares and `over a longer horizon` does not. Adding `over` to the `>` class fixed
    one true claim and broke another, so it is not in the list: a stem that is sometimes a preposition
    manufactures a comparison the claim never made."""
    chunk = "For example, we find that weekly news predicts returns much longer than daily news."
    rec = record(claim="Weekly news predicts returns over a much longer horizon than daily news.",
                 evidence_quote="weekly news predicts returns much longer than daily news")
    assert verdict(rec, chunk=chunk).ok is True


# --- What 4,358 real claims showed ---------------------------------------------------------------
#
# The first full round rejected 614 of 4,358, and 470 of those were NUMBER_NOT_IN_QUOTE — 76% of all
# rejections, where 116 earlier claims had produced one. Reading them, two families of false rejection.

def test_a_year_range_is_two_years_and_not_a_negative_number():
    """The worst of them: the claim said "during 1964-1997" and the quote said *the same words*. `-1997` was
    extracted as a signed figure, then searched for in a quote where the hyphen follows a digit — so the
    digit boundary blocked the very text it came from. 1964-1997 is two years."""
    chunk = ("Across NYSE stocks during 1964-1997, the proposed illiquidity measure has a positive "
             "and highly significant effect on returns.")
    rec = record(claim="Across NYSE stocks during 1964-1997 the measure has a positive effect.",
                 evidence_quote="Across NYSE stocks during 1964-1997, the proposed illiquidity measure "
                                "has a positive")
    assert verdict(rec, chunk=chunk).ok is True


def test_a_digit_that_names_a_model_is_not_a_figure():
    """`3-factor` is a name, like `day-0`. The earlier fix caught a digit *after* a word and missed one
    before it."""
    chunk = "News losers exhibit the same pattern of persistent negative abnormal returns."
    rec = record(claim="The 3-factor model shows news losers have persistent negative abnormal returns.",
                 evidence_quote="news losers exhibit the same pattern of persistent negative abnormal "
                                "returns".capitalize())
    assert verdict(rec, chunk=chunk).ok is True


def test_a_genuine_negative_figure_is_still_a_figure():
    chunk = "the alpha is -0.08 per day in that window"
    rec = record(claim="The alpha is -0.08 per day.", evidence_quote="the alpha is -0.08 per day")
    assert verdict(rec, chunk=chunk).ok is True
    missing = record(claim="The alpha is -0.09 per day.", evidence_quote="the alpha is -0.08 per day")
    assert verdict(missing, chunk=chunk).failure == "NUMBER_NOT_IN_QUOTE"


def test_a_window_the_quote_does_not_show_is_still_a_rejection():
    """Not every flagged figure was a false positive. A claim citing days [-15,-6] against a quote that is a
    table of alphas asserts a window the quote does not carry, and that stays refused."""
    chunk = "Daily Alpha | 0.080 | 0.065 | 0.045 | for windows we tabulate elsewhere"
    rec = record(claim="For events with the latest story in days [-15,-6] the portfolio earns 0.080.",
                 evidence_quote="Daily Alpha | 0.080 | 0.065 | 0.045 |")
    assert verdict(rec, chunk=chunk).failure == "NUMBER_NOT_IN_QUOTE"


# --- prose and composite as-written fields --------------------------------------------------------
# On the first full round 295 of 326 `VALUE_NOT_IN_QUOTE` rejections were these two fields, and every
# one of them was a true claim: stage 4 asks for `weekly` and for `A versus B`, and a quote that says
# `up to 13 weeks` bears neither verbatim.

def test_a_prose_horizon_need_not_appear_verbatim():
    rec = record(horizon_as_written="weekly")
    assert verdict(rec).ok is True


def test_a_prose_horizon_still_has_its_numbers_checked():
    quote = "earn excess returns for up to 13 weeks"
    rec = record(horizon_as_written="up to 13 weeks", evidence_quote=quote)
    assert verdict(rec).ok is True
    bad = {**rec, "horizon_as_written": "up to 26 weeks"}
    result = verdict(bad)
    assert result.failure == "VALUE_NOT_IN_QUOTE"
    assert "'26'" in result.detail


# The two sides are in one sentence, joined by a connective that is not `versus`.
SIDES = "the treated group earned 4.2 basis points against 1.9 for the control"


def test_a_contrast_need_not_match_the_quotes_own_connective():
    # The quote joins the two sides with `against`, and stage 4 asks for `versus`.
    rec = record(contrast_as_written="4.2 versus 1.9", evidence_quote=SIDES)
    assert verdict(rec, chunk=SIDES).ok is True


def test_a_contrast_asserting_a_figure_the_quote_lacks_is_still_refused():
    rec = record(contrast_as_written="4.2 versus 3.3", evidence_quote=SIDES)
    result = verdict(rec, chunk=SIDES)
    assert result.failure == "VALUE_NOT_IN_QUOTE"
    assert "'3.3'" in result.detail


def test_a_single_figure_field_is_still_checked_verbatim():
    # Nothing above loosens the fields the engine actually converts.
    bad = record(estimate_as_written="4.20",
                 evidence_quote="the estimate is greater than the no-news benchmark by 4.2 basis")
    assert verdict(bad).failure == "VALUE_NOT_IN_QUOTE"


def test_a_comma_is_a_thousands_separator_only_before_three_digits():
    """`[2,5]` is an event window of two days, not the figure twenty-five.

    45 rejections on the first full round, every one a true claim stating a window — the same error as
    reading `1964-1997` as minus 1997, one separator over.
    """
    quote = "returns over days [2,5] after the story"
    rec = record(claim="Returns accumulate over days [2,5].", evidence_quote=quote)
    assert verdict(rec, chunk=quote).ok is True
    # A real thousands separator is still one figure.
    big = "a sample of 1,297 firms"
    assert verdict(record(claim="The sample has 1,297 firms.", evidence_quote=big),
                   chunk=big).ok is True
    mismatched = "a sample of 1,297 firms"
    assert verdict(record(claim="The sample has 2,400 firms.", evidence_quote=mismatched),
                   chunk=mismatched).failure == "NUMBER_NOT_IN_QUOTE"


# --- a per-cent sign the quote leaves implicit ----------------------------------------------------
# A table cell reads `1.99` under a header declaring percent and the claim writes `1.99%`. Measured on
# the first full round: three of five sampled NUMBER_NOT_IN_QUOTE rejections were this, and the figure
# was in the quote in every one.

PERCENT_CHUNK = "the initial reaction is 1.99 and the drift is 0.06 for small caps"


def test_a_percent_sign_the_quote_leaves_implicit_does_not_make_the_figure_absent():
    rec = record(claim="The initial reaction is 1.99%.", evidence_quote=PERCENT_CHUNK)
    assert verdict(rec, chunk=PERCENT_CHUNK).ok is True


def test_a_different_unit_on_those_digits_is_still_a_disagreement():
    """`2.4%` against `2.4 basis points` is two magnitudes apart, and dropping the sign blindly would
    pass it. The unit is what makes them differ, so the unit decides."""
    for unit in ("basis points", "percentage points", "bps"):
        quote = f"a drift of 2.4 {unit} over the week"
        rec = record(claim="The drift is 2.4%.", evidence_quote=quote)
        assert verdict(rec, chunk=quote).failure == "NUMBER_NOT_IN_QUOTE", unit


def test_the_digit_boundary_still_holds_with_the_sign_dropped():
    """A claim of 1.5% must not pass on a quote of 11.5, which is a different figure."""
    quote = "a drift of 11.5 over the week"
    rec = record(claim="The drift is 1.5%.", evidence_quote=quote)
    assert verdict(rec, chunk=quote).failure == "NUMBER_NOT_IN_QUOTE"


def test_the_unit_vocabulary_is_the_converters_and_not_a_second_copy():
    """Two lists of what a unit is would drift, and the drift would look like a rejection."""
    from claimstone import claimgate, numbers

    declared = {s for suffixes, _f, _s in numbers._UNITS for s in suffixes}
    assert set(claimgate._UNIT_WORDS) == declared
