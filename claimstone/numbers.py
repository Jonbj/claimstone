"""An as-written form into a value and a scale. Pure, and it refuses rather than guessing.

A paper writes `2.4%`; a numeric field wants `0.024`. As strings they do not match, so a gate checking
the value against the quote would reject a correct record — or be loosened until it verified nothing.
So the model reports **only** the as-written form and the engine converts here, in code. The gate checks
that the as-written string is in the quote, and the value never came from the model, so it cannot be
wrong in a way the quote cannot reveal.

**A notation this module does not understand is refused, never nulled.** `UNPARSEABLE_VALUE` is a
recorded rejection; a `null` would read as "no estimate reported", which is a claim about the paper that
a parser failure has not earned.

**A scale is recorded and never assumed.** `0.024` may be a fraction, a coefficient or a t-statistic and
nothing here knows which, so it is `as_reported` — the honest label. What this module cannot reach at all
is whether a bracketed figure is a standard error or a t-statistic, and whether an uncertainty is on the
estimate's scale. Those are estimand questions; stage 5 is a model reading them, not a verification.

**A hedge is part of the notation, and the bound it states is recorded.** Measured on the first full
round, 46 of 183 unreadable forms were a figure behind a word: `nearly 6%`, `over 300%`, `all below 65%`,
`∼100%`. Reading any of them as an exact value would drop an inequality the paper wrote, which is the
same error `COMPARATIVE_NOT_IN_QUOTE` exists to catch one field over. So the word is stripped to reach
the figure and recorded as `lower`, `upper` or `approximate`.

**A label is stripped, not interpreted.** `t = 5.73`, `(se = 1.20)` and `standard error of 1.90` were 32
more of those 183. The label names the quantity, and *what the quantity is* remains the estimand question
above — so the number is read, the label stays in the as-written form for a reader, and this module still
declines to say whether it is a standard error.

**A contrast holds two numbers by construction**, because that is what stage 4 asks for: "the two sides
as written: `0.31% versus 0.04%`". Putting it through the one-value path made 60 of those 183 refusals a
statement about this module and not about the paper. It has its own two-sided reading, and both sides
must share a scale — `2.00% versus 0.14` is a mismatch worth naming.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

# Digits with optional thousands separators, decimal point, scientific exponent, and a leading ASCII
# hyphen or Unicode minus — typeset papers use the latter.
# The leading zero is optional because a great deal of literature omits it: `ß = -.22` and `p < .01`
# are how psychology and epidemiology write a coefficient and a significance level, and 63 estimates in
# the PMC round were refused for that alone.
_NUMBER = re.compile(r"^[-−+]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)(?:[eE][-−+]?\d+)?$")

# Ordered: the longest suffix first, so `basis points` is not read as `points`.
_UNITS: tuple[tuple[tuple[str, ...], float, str], ...] = (
    (("percentage points", "percentage point", "pp", "ppt"), 0.01, "fraction_difference"),
    (("basis points", "basis point", "bps", "bp"), 0.0001, "fraction"),
    (("percent", "per cent", "%"), 0.01, "fraction"),
)

# A range is found by counting numbers rather than by looking for a separator: `2.4% to 3.1%` has
# a per-cent sign between the digit and the word, which a separator pattern misses, and `1.4e-3`
# has a hyphen inside a single number, which one over-matches.
_TOKEN = re.compile(r"(?:\d[\d,]*(?:\.\d+)?|(?<![\d.])\.\d+)(?:[eE][-−+]?\d+)?")

# What a hedge says about the figure behind it. `approaching` is deliberately `approximate` rather than
# a direction: "approaching 1%" reads as just under 1% to most people and as just over to some, and
# guessing between them would be this module answering a question the words do not settle.
_BOUNDS: tuple[tuple[str, str], ...] = tuple(sorted(
    [(word, kind) for words, kind in (
        (("at least", "no less than", "more than", "greater than", "in excess of", "over", "above",
          ">=", "≥", ">"), "lower"),
        (("at most", "no more than", "less than", "fewer than", "all below", "up to", "under",
          "below", "<=", "≤", "<"), "upper"),
        (("approximately", "approx.", "approx", "nearly", "almost", "around", "about", "roughly",
          "circa", "approaching", "~", "∼", "≈"), "approximate"),
    ) for word in words],
    key=lambda pair: -len(pair[0]),
))

# A label naming the quantity. Stripped to reach the figure; never read as saying what the quantity is.
#
# **A default, not the vocabulary.** Written against one corpus it becomes domain knowledge in the engine,
# which invariant 4 forbids, and which measurably happened: this list shipped with `sharpe` and without
# `OR`, so the finance corpus parsed and the epidemiology corpus did not — 63 estimates refused over
# `AOR=1.66` and `ß = -.22`. What stays here is what any quantitative field writes. Anything a discipline
# owns is declared in that project's `extraction.value_labels`, which is the shape `comparatives` already
# uses for the same reason.
DEFAULT_VALUE_LABELS: tuple[str, ...] = (
    "t-statistic", "t-statistics", "t-value", "t-values", "t-stat", "t-stats", "t",
    "z-score", "z-scores", "z",
    "standard error", "standard errors", "std err", "std errs", "std. err", "std. errs",
    "standard deviation", "standard deviations", "std dev", "std devs", "std. dev",
    "s.e.", "se", "s.d.", "sd",
    "p-value", "p-values", "p",
    "mean", "means", "median", "medians", "n", "m",
)


def label_pattern(labels: Sequence[str]) -> re.Pattern[str]:
    """Longest first, so `standard error` is not read as `s` and then nonsense.

    The connector is optional: `p < .01` puts an inequality where `=` would go, and requiring one refused
    every significance level in the PMC round. A wrong strip cannot pass anything — what remains still has
    to match a number.

    A letter may not follow the label, or the one-character labels eat the start of a word: `n` took the
    `n` of `nearly 6%` and left `early 6%`, which broke a hedge that had been parsing for hours.
    """
    alternatives = "|".join(
        re.escape(label) for label in sorted(set(labels), key=len, reverse=True) if label
    )
    return re.compile(rf"^(?:{alternatives})(?![A-Za-z])\s*(?:of|=|:|is|was)?\s*", re.I)


_DEFAULT_LABEL = label_pattern(DEFAULT_VALUE_LABELS)

# A period belongs to the horizon, not to the figure: `0.55% per month` is 0.0055, and
# `horizon_as_written` is where stage 4 records the month. Dropped here, and kept there.
_PERIODS: tuple[str, ...] = tuple(sorted(
    ("per day", "per week", "per month", "per quarter", "per year", "per annum", "per trading day",
     "a day", "a week", "a month", "a quarter", "a year", "daily", "weekly", "monthly", "quarterly",
     "yearly", "annually", "annualized", "annualised", "annual"),
    key=lambda word: -len(word),
))

# A trailing gloss repeating the unit in brackets: `5.2 basis points (bps) per day`. Removed only when
# it holds no digits of its own, so a bracketed figure is never silently dropped.
_GLOSS = re.compile(r"\s*\(([^()\d]*)\)\s*$")

# How the two sides of a contrast are joined. `versus` is what stage 4 asks for; the rest are what
# papers write when the model quotes them instead.
_SIDES = re.compile(r"\s+(?:versus|vs\.?|compared\s+(?:with|to)|relative\s+to|against)\s+", re.I)


class Unparseable(ValueError):
    """The notation is not one this module reads. A recorded rejection, never a null."""


@dataclass(frozen=True)
class Value:
    value: float
    scale: str
    as_written: str
    bracketed: bool = False
    # `exact` unless a hedge said otherwise. Never inferred from the magnitude.
    bound: str = "exact"


def parse(as_written: str, *, labels: Sequence[str] | None = None) -> Value:
    """One as-written form into one value. Two values, or none, is a refusal."""
    raw = str(as_written or "").strip()
    if not raw:
        raise Unparseable("an empty as-written form carries no value")
    if not any(ch.isdigit() for ch in raw):
        raise Unparseable(f"{raw!r} contains no digits")

    text = raw
    bracketed = False
    if text.startswith("(") and text.endswith(")"):
        # A paper's convention for an uncertainty. Whether the bracket holds a standard error or a
        # t-statistic is not knowable here, so the fact of the bracket is recorded and nothing more.
        bracketed = True
        text = text[1:-1].strip()

    if len(_TOKEN.findall(text)) > 1:
        raise Unparseable(f"{raw!r} holds more than one number: a range is two values, not one")

    # Both in a loop: `5.2 basis points (bps) per day` puts the gloss inside the period, so one pass
    # in either order leaves the other in place and the figure unreachable.
    while True:
        shorter = _GLOSS.sub("", text).strip()
        low = shorter.lower()
        for period in _PERIODS:
            if low.endswith(period):
                shorter = shorter[: len(shorter) - len(period)].strip()
                break
        if shorter == text:
            break
        text = shorter

    scale = "as_reported"
    factor = 1.0
    low = text.lower()
    for suffixes, unit_factor, unit_scale in _UNITS:
        hit = next((s for s in suffixes if low.endswith(s)), None)
        if hit is not None:
            text = text[: len(text) - len(hit)].strip()
            factor, scale = unit_factor, unit_scale
            break

    label = _DEFAULT_LABEL if labels is None else label_pattern(labels)
    bound = "exact"
    # Both, until neither bites. `p < .01` is a label then a bound and `< .05` is a bound alone, so a fixed
    # order reads one of them and refuses the other.
    while True:
        shorter = label.sub("", text, count=1).strip()
        low = shorter.lower()
        for word, kind in _BOUNDS:
            if low.startswith(word):
                shorter = shorter[len(word):].strip()
                bound = kind
                break
        if shorter == text:
            break
        text = shorter

    text = text.replace("−", "-").replace(",", "").strip()
    if not _NUMBER.match(text.replace(",", "")):
        raise Unparseable(f"{raw!r} is not a notation this module reads")

    return Value(float(text) * factor, scale, raw, bracketed, bound)


def parse_contrast(as_written: str, *, labels: Sequence[str] | None = None) -> tuple[Value, Value]:
    """The two sides of a contrast, in the order they were written.

    Both sides must share a scale. `2.00% versus 0.14` is a per-cent against a bare number, and a
    difference taken across that pair would be off by a hundred without anything looking wrong.
    """
    raw = str(as_written or "").strip()
    sides = _SIDES.split(raw)
    if len(sides) != 2:
        raise Unparseable(f"{raw!r} is not two sides joined by `versus`")
    first, second = (parse(side, labels=labels) for side in sides)
    if first.scale != second.scale:
        raise Unparseable(
            f"{raw!r} puts {first.scale} against {second.scale}: the two sides are not on one scale")
    return first, second


# Which as-written fields hold **one** number. `horizon_as_written` ("one week") and `sample` do not,
# and converting prose would be the guessing this module refuses.
# Aligned with the shapes stage 4 actually asks for. An earlier list named `high_side_as_written` and
# `low_side_as_written`, which do not exist: `high_side` and `low_side` are subgroup *labels* — "small
# firms" — and converting a label would be the guessing this module refuses. It also named
# `contrast_as_written`, which holds two numbers by construction and now has its own path below.
NUMERIC_FIELDS = ("estimate_as_written", "uncertainty_as_written",
                  "contrast_uncertainty_as_written", "threshold_as_written")

# Fields holding two numbers joined by `versus`.
COMPOSITE_FIELDS = ("contrast_as_written",)

# An unreadable form here means the claim's own figure could not be read, so there is nothing to weigh
# and the claim is a rejection. Every other field is recorded as unconverted and the claim stands: a
# t-statistic in a notation this module does not read is a limit of this module, and dropping the claim
# would also drop it from the coverage that makes `UNANSWERED_IN_LITERATURE` sayable.
FIELDS_REQUIRED_TO_CONVERT = ("estimate_as_written",)


def convert(record: dict, *, labels: Sequence[str] | None = None) -> tuple[dict, list[str]]:
    """The record with the engine's fields added, and what could not be read.

    The as-written forms are left untouched: the gate checks them against the quote, and rewriting them
    here would mean the gate checking a string the model never wrote.
    """
    out = dict(record)
    problems: list[str] = []
    for field in NUMERIC_FIELDS:
        raw = record.get(field)
        if not raw:
            continue
        name = field[: -len("_as_written")]
        try:
            parsed = parse(str(raw), labels=labels)
        except Unparseable as exc:
            problems.append(f"{field}: {exc}")
            continue
        out[name] = parsed.value
        out[f"{name}_scale"] = parsed.scale
        if parsed.bracketed:
            out[f"{name}_bracketed"] = True
        if parsed.bound != "exact":
            out[f"{name}_bound"] = parsed.bound

    for field in COMPOSITE_FIELDS:
        raw = record.get(field)
        if not raw:
            continue
        name = field[: -len("_as_written")]
        try:
            first, second = parse_contrast(str(raw), labels=labels)
        except Unparseable as exc:
            problems.append(f"{field}: {exc}")
            continue
        # In written order, and no difference is taken: which side is the treatment is not something
        # the string says, and subtracting the wrong way round flips a verdict.
        out[f"{name}_sides"] = [first.value, second.value]
        out[f"{name}_scale"] = first.scale
        bounds = [first.bound, second.bound]
        if bounds != ["exact", "exact"]:
            out[f"{name}_bounds"] = bounds
    return out, problems
