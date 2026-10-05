"""Does this look like full text?

A publisher landing page answers HTTP 200 with a perfectly good content type. Counting it as
an acquisition inflates the rate that decides whether a round may produce verdicts at all,
which is the failure this project exists to prevent. So a transfer succeeding is not the
question; what came back is.

The HTML rule is strict because that is where the inflation happens, and it is strict about
the right thing. A first draft tested length alone; run over 25 artifacts a real round had
already stored, it accepted three vendor research summaries at 4190, 4820 and 5981 characters
and rejected two at 2473 and 2526 — the same kind of page either side of a line chosen at a
desk. No threshold fixes that: one of those summaries runs to 9243 characters. What separates
them is that none of them cites anything. A document that argues from evidence has a reference
list; a page summarising one does not.

The PDF rule is structural — no PDF parser exists before stage 3 — and catches the case that
actually occurs: an HTML error page wearing a PDF content type.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Sequence

PDF_FULLTEXT = "PDF_FULLTEXT"
HTML_FULLTEXT = "HTML_FULLTEXT"
JATS_FULLTEXT = "JATS_FULLTEXT"
LANDING_PAGE_ONLY = "LANDING_PAGE_ONLY"
ABSTRACT_ONLY = "ABSTRACT_ONLY"
# A 200 carrying an interstitial that asks the client to prove it is not a robot. It is **not**
# ABSTRACT_ONLY, and the distinction is the whole reason this class exists: `ABSTRACT_ONLY` is a
# statement about the source — only a summary of this paper is freely available — while this is a
# statement about us. Measured on the pilot: 9 attempts across 6 unobtained candidates were recorded as
# `ABSTRACT_ONLY` when the bytes said "Checking your browser before accessing pmc.ncbi.nlm.nih.gov",
# including one on PMC, the route carrying 25 of 39 successes. Recording infrastructure as an
# established negative is the same defect `ARTIFACT_UNREADABLE` was added for one stage over.
BOT_CHALLENGE = "BOT_CHALLENGE"
TOO_SHORT = "TOO_SHORT"
CORRUPT_PDF = "CORRUPT_PDF"
NOT_TEXT = "NOT_TEXT"

ACCEPTED = (PDF_FULLTEXT, HTML_FULLTEXT, JATS_FULLTEXT)

# Phrases a challenge page carries and an article does not. Matched against the visible text only, so
# a paper *discussing* CAPTCHAs is not caught by its own prose: the phrases are the interstitial's own
# words to the user, and they sit alone on a page of a few hundred characters.
CHALLENGE_PHRASES: tuple[str, ...] = (
    "checking your browser",
    "just a moment",
    "verify you are human",
    "are you a robot",
    "enable javascript and cookies to continue",
    "unusual traffic from your computer",
    "ddos protection by",
)

# Bumped whenever a rule below changes. Written onto every ledger row, because a rate computed
# under different thresholds is not comparable to one computed under these.
# Version 2: the HTML rule gained the structural signal after a length-only rule was measured
# against 25 real artifacts and accepted three abstract pages out of six.
# Version 3: a bot challenge is its own kind rather than ABSTRACT_ONLY, which was recording a fact
# about our crawler as a fact about the literature.
# Version 4: XML is checked as JATS, with explicit article structure, instead of being
# treated as HTML and potentially admitting an API error page as full text.
GATE_VERSION = 5

DEFAULT_THRESHOLDS: dict[str, int] = {
    # Low on purpose: a short conference note can be a legitimate 12 KB PDF, and a false
    # TOO_SHORT removes a real source from the numerator.
    "min_pdf_bytes": 10000,
    "min_text_chars": 3000,
    "paywall_doubt_chars": 12000,
    # Above this, accept without a structural signal: a document this long is a document.
    "fulltext_chars": 15000,
}

PAYWALL_PHRASES = (
    "get access", "purchase pdf", "buy article", "rent this article",
    "sign in to continue", "institutional access", "add to cart",
    "subscribe to continue", "you do not have access",
)

_SKIP_TAGS = frozenset({"script", "style", "nav", "header", "footer", "aside"})

# Everything below is knowledge about a language and a genre, not about the engine's job, so a
# project may replace it (invariant 4). These are the defaults for English scholarly prose, which
# is what the first corpus is; an Italian corpus, or one of regulatory filings, must be
# expressible without editing this package.
DEFAULT_POLICY: dict[str, Any] = {
    "paywall_phrases": PAYWALL_PHRASES,
    "reference_headings": ("references", "bibliography", "works cited"),
    # `reference_list` requires the marks of a citing document; `none` asks only for length, for
    # a genre that does not cite at all.
    "structural_signal": "reference_list",
}

STRUCTURAL_SIGNALS = ("reference_list", "none")
# "(Author, 2019)" / "(Author and Other, 2019)" — enough of these is a reference list even when
# the heading is missing or styled unrecognisably.
_CITATION = re.compile(
    r"\(\s*[A-Z][A-Za-z'\-]+(?:\s+(?:and|&|et al\.?)\s+[A-Z][A-Za-z'\-]+)?"
    r"(?:\s*,)?\s*(?:19|20)\d{2}[a-z]?\s*\)"
)
_MIN_CITATIONS = 10


@dataclass(frozen=True)
class FullText:
    kind: str
    chars: int | None
    reason: str
    gate_version: int = GATE_VERSION

    @property
    def accepted(self) -> bool:
        return self.kind in ACCEPTED

    def as_row(
        self, thresholds: dict[str, int], policy: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        applied = {**DEFAULT_POLICY, **(policy or {})}
        return {
            "kind": self.kind,
            "chars": self.chars,
            "reason": self.reason,
            "gate_version": self.gate_version,
            "thresholds": dict(thresholds),
            # A rate computed under a different policy is not comparable to one computed under
            # this. An earlier version stored the *count* of paywall phrases, so two different
            # lists of the same length were recorded identically and a ledger could not tell two
            # instruments apart. The hash covers the whole policy.
            "policy": {
                "structural_signal": applied["structural_signal"],
                "reference_headings": list(applied["reference_headings"]),
                "paywall_phrases": len(applied["paywall_phrases"]),
                "sha256": _policy_digest(applied),
            },
        }


def _policy_digest(policy: dict[str, Any]) -> str:
    """One hash over everything the policy decides, so two instruments are distinguishable."""
    import hashlib
    import json as _json

    payload = _json.dumps(
        {
            "structural_signal": policy["structural_signal"],
            "reference_headings": sorted(policy["reference_headings"]),
            "paywall_phrases": sorted(policy["paywall_phrases"]),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._muted = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in _SKIP_TAGS:
            self._muted += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._muted:
            self._muted -= 1

    def handle_data(self, data: str) -> None:
        if not self._muted:
            self._parts.append(data)

    def text(self) -> str:
        return " ".join("".join(self._parts).split())


def visible_text(body: bytes) -> str:
    parser = _VisibleText()
    try:
        parser.feed(body.decode("utf-8", "replace"))
    except Exception:
        # Malformed markup is common and is not itself a verdict; take what was parsed.
        pass
    return parser.text()


def cites(markup: str, text: str, headings: Sequence[str] = ()) -> bool:
    """Does this document argue from evidence, or summarise something that did?"""
    for heading in headings or DEFAULT_POLICY["reference_headings"]:
        if re.search(rf">\s*{re.escape(heading)}\s*<", markup, re.I):
            return True
    return len(_CITATION.findall(text)) >= _MIN_CITATIONS


def _classify_pdf(body: bytes, th: dict[str, int]) -> FullText:
    if b"%PDF-" not in body[:1024]:
        return FullText(NOT_TEXT, None, "no %PDF- magic in the first 1024 bytes")
    if b"%%EOF" not in body[-2048:]:
        return FullText(CORRUPT_PDF, None, "no %%EOF trailer: truncated transfer")
    if len(body) < th["min_pdf_bytes"]:
        return FullText(
            TOO_SHORT, None, f"{len(body)} bytes below min_pdf_bytes {th['min_pdf_bytes']}"
        )
    return FullText(PDF_FULLTEXT, None, "")


def _classify_markup(body: bytes, th: dict[str, int], policy: dict[str, Any]) -> FullText:
    markup = body.decode("utf-8", "replace")
    text = visible_text(body)
    count = len(text)

    folded = text.lower()

    # Before everything else, because every later rule would describe the source and this page is not
    # the source. A challenge is also *retryable* where a paywall is not, so which class it gets
    # decides whether a named campaign may knock again.
    challenge = next((phrase for phrase in CHALLENGE_PHRASES if phrase in folded), None)
    if challenge is not None and count < th["paywall_doubt_chars"]:
        # Bounded by length for the same reason the paywall phrases are: an article may quote any of
        # these words, and above the doubt threshold the text is there whatever the page says.
        return FullText(BOT_CHALLENGE, count,
                        f"{count} chars and the challenge phrase {challenge!r}: "
                        f"this is a fact about our crawler, not about the source")

    hit = next((phrase for phrase in policy["paywall_phrases"] if phrase in folded), None)
    if hit and count < th["paywall_doubt_chars"]:
        # A phrase alone is never sufficient: a legitimate open-access article also contains
        # "sign in". Above the doubt threshold the text is there whatever the menu says.
        return FullText(LANDING_PAGE_ONLY, count, f"{count} chars and the phrase {hit!r}")

    # The structural check precedes the length check deliberately. A 2473-character summary is
    # both short and a summary, and the second is the more useful thing to record: it says a
    # full text may exist elsewhere and is worth another attempt.
    if policy["structural_signal"] == "reference_list":
        if count < th["fulltext_chars"] and not cites(
            markup, text, policy["reference_headings"]
        ):
            return FullText(
                ABSTRACT_ONLY, count,
                f"{count} chars and no reference list: a summary of a document, not the document",
            )
        if count < th["min_text_chars"]:
            return FullText(TOO_SHORT, count, f"{count} chars, and it does cite: a truncation")
        return FullText(HTML_FULLTEXT, count, "")

    # structural_signal: none — the genre does not cite, so length is all there is. Weaker on
    # purpose and declared as such: a corpus of filings or API documentation has no
    # bibliographies, and requiring one would reject every source in it.
    if count < th["min_text_chars"]:
        return FullText(TOO_SHORT, count, f"{count} chars")
    return FullText(HTML_FULLTEXT, count, "no structural signal is required by this project")


def _classify_jats(body: bytes, th: dict[str, int], policy: dict[str, Any]) -> FullText:
    if re.search(br'<!ENTITY\b', body, re.I):
        return FullText(NOT_TEXT, None, 'XML entity declarations are not accepted')
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return FullText(NOT_TEXT, None, 'malformed XML')
    tag = lambda node: node.tag.rsplit('}', 1)[-1]
    if tag(root) != 'article':
        return FullText(NOT_TEXT, None, 'XML root is not a JATS article')
    front = next((n for n in root if tag(n) == 'front'), None)
    body_node = next((n for n in root if tag(n) == 'body'), None)
    if front is None or body_node is None or not any(tag(n) == 'article-meta' for n in front):
        return FullText(NOT_TEXT, None, 'JATS front/article-meta/body structure is missing')
    def primary_text(node: ET.Element) -> str:
        parts = [node.text or '']
        for child in node:
            if tag(child) not in {'sub-article', 'response', 'ref-list'}:
                parts.append(primary_text(child))
            parts.append(child.tail or '')
        return ''.join(parts)

    chars = len(' '.join(primary_text(body_node).split()))
    if chars < th['min_text_chars']:
        return FullText(TOO_SHORT, chars, f'{chars} body chars below min_text_chars {th["min_text_chars"]}')
    back = next((n for n in root if tag(n) == 'back'), None)
    def has_primary_reference(node: ET.Element) -> bool:
        if tag(node) in {'sub-article', 'response'}:
            return False
        return tag(node) == 'ref' or any(has_primary_reference(child) for child in node)
    references = has_primary_reference(body_node) or (back is not None and has_primary_reference(back))
    if policy['structural_signal'] == 'reference_list' and not references \
            and chars < th['fulltext_chars']:
        return FullText(ABSTRACT_ONLY, chars, 'JATS article has no references and is below fulltext_chars')
    return FullText(JATS_FULLTEXT, chars, '')


def classify(
    body: bytes,
    content_type: str,
    url: str,
    thresholds: dict[str, int] | None = None,
    policy: dict[str, Any] | None = None,
) -> FullText:
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    applied = {**DEFAULT_POLICY, **(policy or {})}
    if applied["structural_signal"] not in STRUCTURAL_SIGNALS:
        raise ValueError(
            f"unknown structural_signal {applied['structural_signal']!r}: "
            f"{', '.join(STRUCTURAL_SIGNALS)}"
        )
    if not body:
        return FullText(TOO_SHORT, 0, "empty body")
    mime = (content_type or '').split(';', 1)[0].strip().lower()
    if mime in {'application/xml', 'text/xml', 'application/jats+xml'}:
        return _classify_jats(body, th, applied)
    looks_pdf = "pdf" in (content_type or "").lower() or url.lower().endswith(".pdf")
    return _classify_pdf(body, th) if looks_pdf else _classify_markup(body, th, applied)
