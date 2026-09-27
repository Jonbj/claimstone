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
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Digits with optional thousands separators, decimal point, scientific exponent, and a leading ASCII
# hyphen or Unicode minus — typeset papers use the latter.
_NUMBER = re.compile(r"^[-−+]?\d[\d,]*(?:\.\d+)?(?:[eE][-−+]?\d+)?$")

# Ordered: the longest suffix first, so `basis points` is not read as `points`.
_UNITS: tuple[tuple[tuple[str, ...], float, str], ...] = (
    (("percentage points", "percentage point", "pp", "ppt"), 0.01, "fraction_difference"),
    (("basis points", "basis point", "bps", "bp"), 0.0001, "fraction"),
    (("percent", "per cent", "%"), 0.01, "fraction"),
)

# A range is found by counting numbers rather than by looking for a separator: `2.4% to 3.1%` has
# a per-cent sign between the digit and the word, which a separator pattern misses, and `1.4e-3`
# has a hyphen inside a single number, which one over-matches.
_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?(?:[eE][-\u2212+]?\d+)?")


class Unparseable(ValueError):
    """The notation is not one this module reads. A recorded rejection, never a null."""


@dataclass(frozen=True)
class Value:
    value: float
    scale: str
    as_written: str
    bracketed: bool = False


def parse(as_written: str) -> Value:
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

    scale = "as_reported"
    factor = 1.0
    low = text.lower()
    for suffixes, unit_factor, unit_scale in _UNITS:
        hit = next((s for s in suffixes if low.endswith(s)), None)
        if hit is not None:
            text = text[: len(text) - len(hit)].strip()
            factor, scale = unit_factor, unit_scale
            break

    text = text.replace("−", "-").replace(",", "").strip()
    if not _NUMBER.match(text.replace(",", "")):
        raise Unparseable(f"{raw!r} is not a notation this module reads")

    return Value(float(text) * factor, scale, raw, bracketed)


# Which as-written fields hold a number. `horizon_as_written` ("one week") and `sample` do not, and
# converting prose would be the guessing this module refuses.
# Aligned with the shapes stage 4 actually asks for. An earlier list named `high_side_as_written` and
# `low_side_as_written`, which do not exist: `high_side` and `low_side` are subgroup *labels* — "small
# firms" — and converting a label would be the guessing this module refuses.
NUMERIC_FIELDS = ("estimate_as_written", "uncertainty_as_written", "contrast_as_written",
                  "contrast_uncertainty_as_written", "threshold_as_written")


def convert(record: dict) -> tuple[dict, list[str]]:
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
            parsed = parse(str(raw))
        except Unparseable as exc:
            problems.append(f"{field}: {exc}")
            continue
        out[name] = parsed.value
        out[f"{name}_scale"] = parsed.scale
        if parsed.bracketed:
            out[f"{name}_bracketed"] = True
    return out, problems
