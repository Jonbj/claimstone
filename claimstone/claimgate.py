"""Invariant 1, executable: no claim without a verified quote.

A record and a chunk's text in, a verdict out. Pure — no store, no network, no model — because this is
where the project's first invariant stops being prose, and a check that needs a fixture to run is a
check nobody runs.

**Nothing is partially accepted.** A record failing any check goes to the rejection ledger whole, with
the check that failed and the record intact, because a rejection nobody can read is not a denominator.

**What no check here establishes.** That a quote is in the chunk, and that the claim's figures and
comparisons are in the quote. Not that the model read the right row of a table, not that `(0.008)` is a
standard error rather than a t-statistic, not that an uncertainty is on the estimate's scale. Those are
estimand questions and nothing mechanical reaches them; stage 5 is a model reading, not a verification.

Two checks come from measurement rather than from the spec. On 66 real claims for one question, 66 of
66 quotes were exact — and the single one that contradicted the question was `ACA002` reporting Roll
(1988), whose 48-character quote carried almost none of its 190-character claim, about a paper not in
the corpus. Exact is necessary and not sufficient (D23).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from . import numbers

# The rule set these checks are. It is stamped on every claim and every rejection, because a claim
# admitted under one rule set and a claim admitted under another are not the same kind of row, and a
# figure that mixes them silently is the failure `tools/check_instrument_versions.py` exists to stop.
# Rows written before this constant existed carry no `claim_gate_version` and are rule set 1.
#
#   1  the first full round: every `_as_written` field checked verbatim against the quote, and any
#      unreadable value a rejection whatever field it was in.
#   2  single-figure fields checked verbatim, prose and composite fields checked numeral by numeral,
#      and an unreadable auxiliary field recorded as `unconverted` instead of dropping the claim.
#   3  a per-cent sign the quote leaves implicit no longer makes the figure absent, unless the quote
#      attaches a different unit to those digits.
#   4  whole numeric tokens, including sign, leading decimal, grouping and exponent; single-figure
#      as-written fields retain their verbatim check and also verify whole tokens.
CLAIM_GATE_VERSION = 4

FAILURES = (
    "UNKNOWN_QUESTION_ID", "WRONG_KIND", "QUOTE_NOT_FOUND", "VALUE_NOT_IN_QUOTE",
    "NUMBER_NOT_IN_QUOTE", "COMPARATIVE_NOT_IN_QUOTE", "WRONG_STANCE",
    "SECONDHAND_CLAIM", "QUOTE_TOO_THIN",
    # Raised by `numbers.convert` rather than by a check here, because the gate compares strings while
    # conversion produces the values stage 6 consumes. It is a rejection all the same: a null would
    # read as "no estimate reported", which a parser failure has not earned.
    "UNPARSEABLE_VALUE",
)

# Digits, optional thousands separators and decimal point, optional exponent, optional percent, and a
# leading ASCII hyphen **or Unicode minus** — which typeset papers use, and which an earlier draft of
# this rule did not match. A written-out number is not checked: the rule exists to stop a fabricated
# figure, and a fabricated figure is written in digits.
#
# **A comma is a thousands separator only before exactly three digits.** An earlier `[\d,.]*` read the
# interval `[2,5]` as the single figure `2,5` — twenty-five — and then asked the quote for a number
# nobody wrote: 45 rejections on the first full round, all of them true claims stating an event window.
# It is the same error as reading `1964-1997` as minus 1997, one separator over.
# A detached `. 001` is a spaced leading decimal. A dot attached to a word, another dot or a
# closing delimiter is punctuation, so `vs. 2.89` and `... 1` keep their whole next figure.
NUMERAL = re.compile(
    r"(?:[-−+][ \t]*)?(?:\d+(?:,\d{3})*(?:\.\d+)?|(?<![\w.)\]])\.[ \t]*\d+)(?:[eE][-−+]?\d+)?%?")

# A digit inside a hyphenated word is a name, not a figure. `day-0` and `T+63` read as numerals
# rejected two true claims on the first real harvest, whose quotes had no reason to contain a zero.
IDENTIFIER_TAIL = re.compile(r"[A-Za-z][-\u2212+]$")

# The mirror image, found on the first full round: `3-factor` names a model the way `day-0`
# names a day, and the earlier rule caught a digit hanging off a word while missing one in
# front of it.
IDENTIFIER_HEAD = re.compile(r"^[-\u2212][A-Za-z]")

# Matched by class, not by phrase, and by **stem** rather than by whole word. Comparing phrases
# literally rejects a correct record whose claim says `exceeds` where the quote says `is greater than`
# — a false rejection for a synonym. Measured on the first real harvest, a list of exact forms held
# `exceeds` and not `exceeding` and rejected a true claim for exactly that.
DEFAULT_COMPARATIVES: dict[str, tuple[str, ...]] = {
    # `over` is deliberately absent. It compares in "over 90% of stocks" and does not in "over a
    # longer horizon", and adding it fixed one true claim on the real harvest while breaking another —
    # a stem that is sometimes a preposition manufactures a comparison the claim never made.
    ">": ("more than", "higher than", "greater than", "exceed", "outperform", "above",
          "larger", "bigger", "elevated", ">"),
    "<": ("less than", "lower than", "below", "underperform", "under-perform", "smaller",
          "fewer than", "<"),
    ">=": ("at least", "no less than", ">=", "≥"),
    "<=": ("at most", "no more than", "<=", "≤"),
}

# Note the absence of `operational`: those questions receive no verdict, which is what makes them
# unextractable rather than merely stanceless.
STANCES_BY_KIND: dict[str, tuple[str, ...]] = {
    "effect": ("SUPPORTS", "CONTRADICTS", "QUALIFIES"),
    "heterogeneity": ("SUPPORTS", "CONTRADICTS", "QUALIFIES"),
    "method": ("SUPPORTS", "CONTRADICTS"),
    "premise": ("SUPPORTS", "CONTRADICTS"),
}

# A citation in the claim's **subject position**: the claim is reporting what another work found rather
# than what this source establishes. Anchored at the start on purpose — "inconsistent with Roll (1988)"
# is this paper's finding contrasted with another's, and rejecting every claim that names a work would
# discard those. Measured: 4 of 66 claims named a work, and exactly one of them in subject position.
_CITE = r"[A-Z][A-Za-zÀ-ɏ'’-]+(?:\s*(?:,|and|&|et al\.?)\s*[A-Z][A-Za-zÀ-ɏ'’-]+)*"
SECONDHAND = re.compile(rf"^\s*(?:The passage reports that\s+)?(?:prior work by\s+)?{_CITE}\s*\(\d{{4}}[a-z]?\)")

# A citation's year is not a figure the claim asserts, and the numeral check must not read it as one.
# Measured: 4 of 66 real claims name another work, and every one of them would have been rejected as
# NUMBER_NOT_IN_QUOTE unless the quote happened to carry the same year — a false rejection on 6% of a
# real harvest, for a rule whose whole purpose is to catch a *fabricated* figure.
CITATION_YEAR = re.compile(rf"{_CITE}\s*\((\d{{4}}[a-z]?(?:\s*[,;]\s*\d{{4}}[a-z]?)*)\)")

# `operational` questions receive no verdict at all (invariant 2), so a claim for one is a call spent
# on an answer nothing will ever read. They are refused here rather than silently accepted and dropped
# later.
EXTRACTABLE_KINDS = tuple(STANCES_BY_KIND)

DEFAULT_THRESHOLDS: dict[str, int] = {
    # The quote must be at least this percentage of the claim's length. Zero disables the check, and
    # zero is the default, **because the measurement says length is the wrong instrument**.
    #
    # D23 asked for a check that a quote carries its claim: exact is necessary and not sufficient, and
    # the one claim that would have decided H02's verdict had a 48-character quote under a
    # 190-character claim. Swept on those 66 claims, this ratio does nothing from 0 to 34, and at 35 —
    # the value chosen at a desk — it rejects a *true* claim whose 57-character quote carries the
    # figure and the direction both. The case it was meant to catch is caught by SECONDHAND_CLAIM,
    # which is about attribution and not about length.
    #
    # So the check stays, declarable per project, and off. Shipping a threshold that earns nothing and
    # costs one true claim would be the desk-chosen constant this project keeps finding and removing.
    "min_quote_ratio": 0,
}


@dataclass(frozen=True)
class Verdict:
    ok: bool
    failure: str | None
    detail: str
    record: dict[str, Any] = field(default_factory=dict)


def _numeric_tokens(text: str) -> Iterable[tuple[int, int, str]]:
    """Whole figures, preserving signs except a range or a dash attached to a typeset label.

    `1964-1997` has two positive endpoints; `reversals-3.7` uses the paper's label separator
    (D25). A detached minus, including `- 2`, remains a sign. No magnitude is converted here.
    """
    for found in NUMERAL.finditer(text):
        figure = found.group(0).replace("−", "-").replace(" ", "").replace("\t", "")
        start = found.start()
        before = text[:start]
        if figure.startswith("-") and before[-1:] and before[-1:].isalnum():
            figure = figure[1:]
        if figure.startswith("+"):
            figure = figure[1:]
        yield start, found.end(), figure


def _asserted_numerals(claim: str) -> list[str]:
    """The whole figures asserted: citation years and identifiers removed."""
    text = CITATION_YEAR.sub(" ", claim)
    out: list[str] = []
    for start, end, figure in _numeric_tokens(text):
        before = text[:start]
        if before[-1:].isalpha() or IDENTIFIER_TAIL.search(before):
            continue
        after = text[end:end + 2]
        if after[:1].isalpha() or IDENTIFIER_HEAD.match(after):
            continue
        out.append(figure)
    return out


# Every unit notation this project knows, longest first. Taken from `numbers._UNITS` rather than
# restated, so the gate and the converter cannot drift apart about what a unit is.
_UNIT_WORDS: tuple[str, ...] = tuple(sorted(
    (suffix for suffixes, _factor, _scale in numbers._UNITS for suffix in suffixes),
    key=len, reverse=True))


def _unit_after(text: str, at: int) -> str:
    """The unit the text attaches to a figure ending at `at`, or "" if it attaches none."""
    tail = text[at:at + 20].lstrip().lower()
    return next((word for word in _UNIT_WORDS if tail.startswith(word)), "")


def _figure_present(figure: str, quote: str) -> bool:
    """Is this figure in the quote, as a figure?

    Compare whole numeric tokens without removing figures attached to typeset labels. Thus
    `return reversals-3.7 bps versus 16.7` still holds both (D25), but `2` cannot borrow digits
    from `-2`, `.2`, `2.7`, `2,000` or `2e3`. Sentence punctuation is outside the token.

    **A per-cent sign the quote leaves implicit does not make the figure absent.** A table cell reads
    `1.99` under a header declaring percent, and the claim writes `1.99%`. Measured on the first full
    round: three of five sampled `NUMBER_NOT_IN_QUOTE` rejections were this, and the figure was in the
    quote in every one of them. The invariant is about the *number*; the unit is checked verbatim on
    `estimate_as_written` and its siblings, which is why that rule stays strict.

    So the sign may be dropped — but only when the quote attaches no **different** unit to those
    digits. A claim of `2.4%` against a quote of `2.4 basis points` is a real disagreement about
    magnitude, and dropping the sign blindly would pass it.
    """
    for _start, end, quoted in _numeric_tokens(quote):
        if quoted == figure or (not figure.endswith("%") and quoted == figure + "%"):
            return True
        if figure.endswith("%") and quoted == figure[:-1] and not _unit_after(quote, end):
            return True
    return False


def _classes(text: str, comparatives: dict[str, Sequence[str]]) -> set[str]:
    low = text.lower()
    return {name for name, phrases in comparatives.items() if any(p in low for p in phrases)}


def check(
    record: dict[str, Any],
    *,
    chunk: str,
    questions: Iterable[Any],
    lane: str,
    comparatives: dict[str, Sequence[str]] | None = None,
    thresholds: dict[str, int] | None = None,
) -> Verdict:
    """The checks, in order. The first failure is the verdict and the record is kept whole."""
    phrases = comparatives or DEFAULT_COMPARATIVES
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    def no(failure: str, detail: str) -> Verdict:
        return Verdict(False, failure, detail, record)

    claim = str(record.get("claim") or "")
    quote = str(record.get("evidence_quote") or "")

    question = next((q for q in questions if q.id == record.get("question_id")), None)
    if question is None:
        return no("UNKNOWN_QUESTION_ID", f"{record.get('question_id')!r} is not in the registry")
    if question.kind not in EXTRACTABLE_KINDS:
        return no("WRONG_KIND",
                  f"{question.id} is kind {question.kind!r}, which receives no verdict — "
                  f"extracting claims for it spends a call on an answer nothing reads")
    if question.kind != lane:
        return no("WRONG_KIND", f"{question.id} is kind {question.kind!r}, asked in lane {lane!r}")

    # Against the chunk's stored text, which stage 3 guarantees is byte-for-byte what the model was
    # shown. Re-rendering either side here would turn a difference between two renderings into the
    # rejection of a true claim.
    if not quote or quote not in chunk:
        return no("QUOTE_NOT_FOUND", f"{quote[:80]!r} is not a substring of the chunk")

    # A field holding one figure is checked verbatim: the engine converts that string and nothing else,
    # so the string is what the quote has to bear.
    for name in numbers.NUMERIC_FIELDS:
        value = record.get(name)
        if value:
            if str(value) not in quote:
                return no("VALUE_NOT_IN_QUOTE", f"{name}={value!r} is not in the quote")
            for figure in _asserted_numerals(str(value)):
                if not _figure_present(figure, quote):
                    return no("VALUE_NOT_IN_QUOTE",
                              f"{name}={value!r} asserts {figure!r}, which is not in the quote")

    # Every other as-written field is prose or a composite — `weekly`, `0.31% versus 0.04%` — and stage 4
    # asks for exactly that. Demanding the whole string verbatim rejected 295 true claims on the first
    # full round because the quote wrote `each week`, or joined the two sides with `compared with`. The
    # invariant is about numbers and inequalities, so the numbers are what is checked.
    for name, value in record.items():
        if not name.endswith("_as_written") or name in numbers.NUMERIC_FIELDS or not value:
            continue
        for figure in _asserted_numerals(str(value)):
            if not _figure_present(figure, quote):
                return no("VALUE_NOT_IN_QUOTE",
                          f"{name}={value!r} asserts {figure!r}, which is not in the quote")

    for figure in _asserted_numerals(claim):
        if not _figure_present(figure, quote):
            return no("NUMBER_NOT_IN_QUOTE", f"{figure!r} appears in the claim and not in the quote")

    missing = _classes(claim, phrases) - _classes(quote, phrases)
    if missing:
        return no("COMPARATIVE_NOT_IN_QUOTE",
                  f"comparative class {sorted(missing)} is in the claim and not in the quote")

    allowed = STANCES_BY_KIND.get(question.kind, ())
    if record.get("stance") not in allowed:
        return no("WRONG_STANCE",
                  f"{record.get('stance')!r} is not one of {list(allowed)} for kind {question.kind!r}")

    if SECONDHAND.match(claim):
        return no("SECONDHAND_CLAIM",
                  "the claim reports what another work found, not what this source establishes")

    ratio = th["min_quote_ratio"]
    if ratio and claim and len(quote) * 100 < len(claim) * ratio:
        return no("QUOTE_TOO_THIN",
                  f"quote is {len(quote)} characters under a claim of {len(claim)}, "
                  f"below {ratio}%")

    return Verdict(True, None, "", record)
