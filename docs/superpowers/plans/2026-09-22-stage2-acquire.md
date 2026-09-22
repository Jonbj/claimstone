# Stage 2 — acquire: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a 26-source manifest into a measured acquisition rate — with OA status, licence and failure reason recorded per source — where nothing counts as acquired unless the bytes pass a mechanical gate.

**Architecture:** Five modules with one responsibility each. `resolve.py` builds the cascade of places a legal copy might live; `fulltext.py` judges bytes with no network and no state; `acquire.py` orchestrates and writes the append-only ledger; `admissibility.py` computes the rate and compares it to the floor; `net.py` keeps HTTP, robots and the per-domain budget. The fetcher enters every function as a parameter satisfying a `Protocol`, which is what lets the whole stage be tested offline.

**Tech Stack:** Python ≥ 3.11, stdlib plus `requests`, `PyYAML`, `numpy`. No framework. pytest.

**Spec:** `docs/superpowers/specs/2026-09-22-stage2-acquire-design.md`. Read it before Task 1; every task below cites the section it implements.

---

## Conventions for every task

- Run tests with `.venv/bin/pytest`, the CLI with `.venv/bin/claimstone`.
- **Every commit message ends with the trailer** `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`, shown in full in Task 1 and abbreviated as `<trailer>` afterwards.
- **No test may construct a real `net.Fetcher`.** Its `__post_init__` calls `contact_email()`, which raises unless `CLAIMSTONE_CONTACT_EMAIL` is set, and CI does not set it. Tests use the `FakeFetcher` built in Task 1.
- Commit after every task. A task that leaves the suite red is not finished.

## Starting state

`claimstone/acquire.py` (289 lines) and `claimstone/discover.py` (246 lines) exist untracked, written in a previous session which is now stopped. They are a working draft of the cascade. This plan **moves** most of that code into `resolve.py` and corrects three defects recorded in spec §10. Nothing is rewritten that does not need to be.

## File structure

| File | Action | Responsibility |
|---|---|---|
| `claimstone/net.py` | modify | HTTP, robots, budget. Gains the fetcher `Protocol` and the failure-class taxonomy. |
| `claimstone/fulltext.py` | create | bytes → verdict. No network, no state. |
| `claimstone/resolve.py` | create | candidate → ordered `[Location]`. Fetcher injected. |
| `claimstone/acquire.py` | rewrite | orchestration and the ledger row. |
| `claimstone/admissibility.py` | create | rate, per-class breakdown, floor. |
| `claimstone/config.py` | modify | loads `manifest.tsv` as the fourth project file. |
| `claimstone/cli.py` | modify | `import-manifest`, `acquire`, `report`. |
| `tests/fakes.py` | create | `FakeFetcher` and response builders, shared by every test below. |
| `tests/test_fulltext.py` | create | the gate |
| `tests/test_resolve.py` | create | the cascade |
| `tests/test_acquire.py` | create | orchestration, ledger, retry policy |
| `tests/test_admissibility.py` | create | rate arithmetic and the floor |
| `tests/test_manifest.py` | create | manifest validation |
| `tests/test_live.py` | create | three known-OA DOIs, skipped unless `CLAIMSTONE_LIVE=1` |
| `docs/contracts/acquisitions.md` | create | the row schema stage 3 will read |

---

### Task 1: The fetcher Protocol, the failure taxonomy, and FakeFetcher

Implements spec §2 (injected fetcher) and §7 (terminal/transient classes).

**Files:**
- Modify: `claimstone/net.py` (add after the existing failure-class block, lines 26-37)
- Create: `tests/fakes.py`
- Create: `tests/test_net_taxonomy.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_net_taxonomy.py`:

```python
"""Every failure class must be classified exactly once.

An unclassified class silently means "never retried", which is the difference between a
source that is gone and a source nobody tried again.
"""

from claimstone import net


def _declared_classes() -> set[str]:
    return {
        value
        for name, value in vars(net).items()
        if name.isupper() and isinstance(value, str) and name not in {"USER_AGENT"}
    }


def test_every_failure_class_is_terminal_or_transient():
    unclassified = _declared_classes() - net.TERMINAL - net.TRANSIENT
    assert unclassified == set(), f"unclassified failure classes: {sorted(unclassified)}"


def test_no_class_is_both():
    assert net.TERMINAL & net.TRANSIENT == frozenset()


def test_is_terminal_agrees_with_the_sets():
    assert net.is_terminal(net.PAYWALL) is True
    assert net.is_terminal(net.TIMEOUT) is False
    assert net.is_terminal("SOMETHING_NOBODY_DECLARED") is True
```

The last assertion is deliberate: an unknown class is treated as terminal, so a typo costs us a retry rather than an unbounded loop against a publisher.

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_net_taxonomy.py -q`
Expected: FAIL with `AttributeError: module 'claimstone.net' has no attribute 'TERMINAL'`

- [ ] **Step 3: Add the taxonomy and the Protocol to `claimstone/net.py`**

Insert immediately after the line `EMPTY = "EMPTY_RESPONSE"` (currently line 37):

```python
# Set by the content gate in fulltext.py rather than by HTTP: a 200 that carries a
# landing page is a failure of acquisition even though the transfer succeeded.
LANDING = "LANDING_PAGE_ONLY"
TOO_SHORT = "TOO_SHORT"
CORRUPT_PDF = "CORRUPT_PDF"
NOT_TEXT = "NOT_TEXT"
WAYBACK_MISS = "WAYBACK_MISS"
NO_LOCATIONS = "NO_LOCATIONS"

# Terminal: retrying changes nothing until the world changes, so a retry needs a named
# campaign. Transient: the next run should try again on its own.
TERMINAL = frozenset(
    {PAYWALL, ROBOTS, EXCLUDED, NOT_FOUND, BAD_TYPE, LANDING, TOO_SHORT, CORRUPT_PDF,
     NOT_TEXT, NO_LOCATIONS}
)
TRANSIENT = frozenset(
    {TIMEOUT, CONNECTION, SERVER_ERROR, RATE_LIMITED, BUDGET, EMPTY, WAYBACK_MISS}
)


def is_terminal(failure_class: str | None) -> bool:
    """An unrecognised class counts as terminal: a typo must cost a retry, not a loop."""
    return failure_class not in TRANSIENT
```

Then add the `Protocol` near the top, immediately after the `import requests` line:

```python
from typing import Protocol


class FetcherLike(Protocol):
    """What the stages need from a fetcher. Tests supply their own implementation."""

    def get(
        self, url: str, *, expect: tuple[str, ...] = (), as_json: bool = False
    ) -> "Outcome": ...

    def get_json(self, url: str) -> tuple[dict[str, Any] | None, "Outcome"]: ...
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_net_taxonomy.py -q`
Expected: PASS, 3 passed

- [ ] **Step 5: Make `tests/` importable**

`from tests.fakes import ...` only resolves if `tests/` is a package. Create an empty
`tests/__init__.py`:

```bash
touch tests/__init__.py
```

- [ ] **Step 6: Write `tests/fakes.py`**

```python
"""Test doubles. No socket is opened and CLAIMSTONE_CONTACT_EMAIL is never needed."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from claimstone import net


def ok(url: str, body: bytes, content_type: str = "application/pdf") -> net.Outcome:
    return net.Outcome(url, True, 200, None, "", content_type, body, 0.1)


def fail(url: str, status: int, failure_class: str, content_type: str = "text/html") -> net.Outcome:
    return net.Outcome(url, False, status, failure_class, "", content_type, None, 0.1)


@dataclass
class FakeFetcher:
    """Answers from dictionaries. `calls` records every URL, in order."""

    pages: dict[str, net.Outcome] = field(default_factory=dict)
    # Keyed by URL prefix, because Unpaywall URLs carry a contact email.
    json_pages: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def get(self, url: str, *, expect: tuple[str, ...] = (), as_json: bool = False) -> net.Outcome:
        self.calls.append(url)
        if url in self.pages:
            return self.pages[url]
        return net.Outcome(url, False, 404, net.NOT_FOUND, "fake: url not configured")

    def get_json(self, url: str) -> tuple[dict[str, Any] | None, net.Outcome]:
        self.calls.append(url)
        for prefix, payload in self.json_pages.items():
            if url.startswith(prefix):
                return payload, net.Outcome(url, True, 200)
        return None, net.Outcome(url, False, 404, net.NOT_FOUND, "fake: url not configured")
```

- [ ] **Step 7: Verify the fake satisfies the Protocol**

Append to `tests/test_net_taxonomy.py`:

```python
def test_fake_fetcher_satisfies_the_protocol():
    from tests.fakes import FakeFetcher

    fetcher: net.FetcherLike = FakeFetcher()
    assert fetcher.get("https://example.org").ok is False
```

Run: `.venv/bin/pytest tests/test_net_taxonomy.py -q`
Expected: PASS, 4 passed

- [ ] **Step 8: Commit**

```bash
git add claimstone/net.py tests/__init__.py tests/fakes.py tests/test_net_taxonomy.py
git commit -m "net: classify every failure as terminal or transient, and name the fetcher contract

An unclassified failure class silently means never retried, which confuses a
source that is gone with a source nobody tried again. A test asserts the
partition is total, so a class added later cannot skip classification.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: The byte gate

Implements spec §5. This is the task that decides whether the headline number is honest.

**Files:**
- Create: `claimstone/fulltext.py`
- Create: `tests/test_fulltext.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fulltext.py`:

```python
"""The gate. A landing page answering 200 is the failure mode this exists to catch."""

from claimstone import fulltext


def pdf(size: int = 12000, *, eof: bool = True) -> bytes:
    body = b"%PDF-1.4\n" + b"x" * size
    return body + b"\n%%EOF" if eof else body


def page(paragraphs: int, extra: str = "") -> bytes:
    """Synthetic markup. Real publisher pages are not copied into this repository."""
    body = "".join(
        f"<p>Sentence {i} of a document about abnormal returns around news events.</p>"
        for i in range(paragraphs)
    )
    return f"<html><head><style>p{{color:red}}</style></head><body>{extra}{body}</body></html>".encode()


def test_a_well_formed_pdf_is_full_text():
    verdict = fulltext.classify(pdf(), "application/pdf", "https://x.org/a.pdf")
    assert verdict.kind == fulltext.PDF_FULLTEXT
    assert verdict.accepted is True


def test_a_truncated_pdf_is_corrupt_not_full_text():
    verdict = fulltext.classify(pdf(eof=False), "application/pdf", "https://x.org/a.pdf")
    assert verdict.kind == fulltext.CORRUPT_PDF
    assert verdict.accepted is False


def test_an_error_page_served_as_pdf_is_not_text():
    verdict = fulltext.classify(page(4), "application/pdf", "https://x.org/a.pdf")
    assert verdict.kind == fulltext.NOT_TEXT


def test_a_tiny_pdf_is_too_short():
    verdict = fulltext.classify(pdf(500), "application/pdf", "https://x.org/a.pdf")
    assert verdict.kind == fulltext.TOO_SHORT


def test_a_landing_page_is_rejected():
    body = page(40, extra="<p>Purchase PDF to read the full article.</p>")
    verdict = fulltext.classify(body, "text/html", "https://publisher.example/article")
    assert verdict.kind == fulltext.LANDING_PAGE_ONLY
    assert "purchase pdf" in verdict.reason


def test_a_long_article_is_accepted_despite_a_sign_in_link():
    body = page(400, extra="<nav>Sign in to continue</nav>")
    verdict = fulltext.classify(body, "text/html", "https://repo.example/article")
    assert verdict.kind == fulltext.HTML_FULLTEXT


def test_short_markup_is_too_short():
    verdict = fulltext.classify(page(2), "text/html", "https://x.org/a")
    assert verdict.kind == fulltext.TOO_SHORT


def test_script_and_style_do_not_count_as_text():
    noisy = b"<html><body><script>" + b"var x = 1;" * 2000 + b"</script><p>hi</p></body></html>"
    verdict = fulltext.classify(noisy, "text/html", "https://x.org/a")
    assert verdict.kind == fulltext.TOO_SHORT
    assert verdict.chars is not None and verdict.chars < 100


def test_thresholds_are_reported_with_the_verdict():
    verdict = fulltext.classify(pdf(), "application/pdf", "https://x.org/a.pdf")
    row = verdict.as_row({"min_pdf_bytes": 10000})
    assert row["gate_version"] == fulltext.GATE_VERSION
    assert row["thresholds"]["min_pdf_bytes"] == 10000
```

Note `test_a_long_article_is_accepted_despite_a_sign_in_link`: the phrase is present and the verdict is still full text, because above `paywall_doubt_chars` the text is there whatever the menu says. That asymmetry is the whole design of the HTML rule.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_fulltext.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.fulltext'`

- [ ] **Step 3: Write `claimstone/fulltext.py`**

```python
"""Does this look like full text?

A publisher landing page answers HTTP 200 with a perfectly good content type. Counting it
as an acquisition inflates the rate that decides whether a round may produce verdicts at
all, which is the failure this project exists to prevent. So a transfer succeeding is not
the question; what came back is.

The HTML rule is strict because that is where the inflation happens. The PDF rule is
structural — no PDF parser exists before stage 3 — and catches the case that actually
occurs: an HTML error page wearing a PDF content type.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

PDF_FULLTEXT = "PDF_FULLTEXT"
HTML_FULLTEXT = "HTML_FULLTEXT"
LANDING_PAGE_ONLY = "LANDING_PAGE_ONLY"
TOO_SHORT = "TOO_SHORT"
CORRUPT_PDF = "CORRUPT_PDF"
NOT_TEXT = "NOT_TEXT"

ACCEPTED = (PDF_FULLTEXT, HTML_FULLTEXT)

# Bumped whenever a rule below changes. Written onto every ledger row, because a rate
# computed under different thresholds is not comparable to one computed under these.
GATE_VERSION = 1

DEFAULT_THRESHOLDS: dict[str, int] = {
    # Low on purpose: a short conference note can be a legitimate 12 KB PDF, and a false
    # TOO_SHORT removes a real source from the numerator.
    "min_pdf_bytes": 10000,
    "min_text_chars": 3000,
    "paywall_doubt_chars": 12000,
}

PAYWALL_PHRASES = (
    "get access", "purchase pdf", "buy article", "rent this article",
    "sign in to continue", "institutional access", "add to cart",
    "subscribe to continue", "you do not have access",
)

_SKIP_TAGS = frozenset({"script", "style", "nav", "header", "footer", "aside"})


@dataclass(frozen=True)
class FullText:
    kind: str
    chars: int | None
    reason: str
    gate_version: int = GATE_VERSION

    @property
    def accepted(self) -> bool:
        return self.kind in ACCEPTED

    def as_row(self, thresholds: dict[str, int]) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "chars": self.chars,
            "reason": self.reason,
            "gate_version": self.gate_version,
            "thresholds": dict(thresholds),
        }


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


def _classify_pdf(body: bytes, th: dict[str, int]) -> FullText:
    if b"%PDF-" not in body[:1024]:
        return FullText(NOT_TEXT, None, "no %PDF- magic in the first 1024 bytes")
    if b"%%EOF" not in body[-2048:]:
        return FullText(CORRUPT_PDF, None, "no %%EOF trailer: truncated transfer")
    if len(body) < th["min_pdf_bytes"]:
        return FullText(TOO_SHORT, None, f"{len(body)} bytes below min_pdf_bytes {th['min_pdf_bytes']}")
    return FullText(PDF_FULLTEXT, None, "")


def _classify_markup(body: bytes, th: dict[str, int]) -> FullText:
    text = visible_text(body)
    count = len(text)
    if count < th["min_text_chars"]:
        return FullText(TOO_SHORT, count, f"{count} chars below min_text_chars {th['min_text_chars']}")
    if count < th["paywall_doubt_chars"]:
        folded = text.lower()
        hit = next((phrase for phrase in PAYWALL_PHRASES if phrase in folded), None)
        if hit:
            return FullText(LANDING_PAGE_ONLY, count, f"{count} chars and the phrase {hit!r}")
    # Above the doubt threshold the text is there, whatever the menu says. A legitimate
    # open-access article also contains "sign in", so a phrase alone is never sufficient.
    return FullText(HTML_FULLTEXT, count, "")


def classify(
    body: bytes, content_type: str, url: str, thresholds: dict[str, int] | None = None
) -> FullText:
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    if not body:
        return FullText(TOO_SHORT, 0, "empty body")
    looks_pdf = "pdf" in (content_type or "").lower() or url.lower().endswith(".pdf")
    return _classify_pdf(body, th) if looks_pdf else _classify_markup(body, th)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_fulltext.py -q`
Expected: PASS, 9 passed

- [ ] **Step 5: Commit**

```bash
git add claimstone/fulltext.py tests/test_fulltext.py
git commit -m "fulltext: a 200 is not an acquisition

A publisher landing page answers 200 with a good content type. The HTML rule is
strict because that is where the rate inflates; the PDF rule is structural
because no parser exists before stage 3, and it says so rather than implying a
check it does not perform.

<trailer>"
```

---

### Task 3: The cascade

Implements spec §3 and §4. Most of this code already exists in the draft `acquire.py` and **moves** here.

**Files:**
- Create: `claimstone/resolve.py`
- Create: `tests/test_resolve.py`
- Modify: `claimstone/acquire.py` (delete what moved; done in Task 4)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_resolve.py`:

```python
"""The cascade: where a legal copy might live, cheapest and most likely first."""

from claimstone import resolve
from tests.fakes import FakeFetcher, ok

UNPAYWALL = "https://api.unpaywall.org/v2/"
OPENALEX_WORK = "https://api.openalex.org/works/doi:"
OPENALEX_SEARCH = "https://api.openalex.org/works?"
WAYBACK = "https://archive.org/wayback/available"


def test_arxiv_comes_first_because_it_is_certainly_legal():
    candidate = {"url": "https://arxiv.org/abs/2401.01234", "title": "A paper"}
    locations, _ = resolve.plan(FakeFetcher(), candidate, use_apis=False)
    assert locations[0].url == "https://arxiv.org/pdf/2401.01234"
    assert locations[0].provenance == "arxiv"


def test_a_known_wall_is_tried_last():
    fetcher = FakeFetcher(json_pages={
        UNPAYWALL: {"oa_status": "green", "oa_locations": [
            {"url_for_pdf": "https://repo.example/paper.pdf", "version": "acceptedVersion",
             "license": "cc-by", "host_type": "repository"}]},
    })
    candidate = {"url": "https://www.sciencedirect.com/science/article/pii/S0304405X",
                 "doi": "10.1016/j.jfineco.2019.05.001", "title": "A paper"}
    locations, oa_status = resolve.plan(fetcher, candidate)
    assert locations[-1].provenance == "candidate"
    assert "sciencedirect.com" in locations[-1].url
    assert oa_status == "green"


def test_openalex_is_consulted_only_when_unpaywall_returns_nothing():
    fetcher = FakeFetcher(json_pages={
        UNPAYWALL: {"oa_status": "closed", "oa_locations": []},
        OPENALEX_WORK: {"open_access": {"oa_status": "bronze"}, "locations": [
            {"is_oa": True, "pdf_url": "https://oa.example/x.pdf", "version": "publishedVersion"}]},
    })
    candidate = {"url": "https://x.example/a", "doi": "10.1/abc", "title": "A paper"}
    locations, _ = resolve.plan(fetcher, candidate)
    assert any(loc.provenance == "openalex" for loc in locations)


def test_published_version_outranks_a_preprint():
    fetcher = FakeFetcher(json_pages={
        UNPAYWALL: {"oa_status": "hybrid", "oa_locations": [
            {"url": "https://a.example/preprint.pdf", "version": "submittedVersion"},
            {"url": "https://b.example/vor.pdf", "version": "publishedVersion"}]},
    })
    candidate = {"url": "https://x.example/a", "doi": "10.1/abc", "title": "A paper"}
    locations, _ = resolve.plan(fetcher, candidate)
    versions = [loc.version for loc in locations if loc.provenance == "unpaywall"]
    assert versions[0] == "publishedVersion"


def test_the_same_url_is_never_planned_twice():
    fetcher = FakeFetcher(json_pages={
        UNPAYWALL: {"oa_status": "green", "oa_locations": [
            {"url": "https://a.example/x.pdf?utm_source=alert"},
            {"url": "https://a.example/x.pdf"}]},
    })
    candidate = {"url": "https://x.example/a", "doi": "10.1/abc", "title": "A paper"}
    locations, _ = resolve.plan(fetcher, candidate)
    assert len(locations) == len({loc.url for loc in locations})


def test_a_title_resolves_a_doi_only_on_an_exact_match():
    fetcher = FakeFetcher(json_pages={
        OPENALEX_SEARCH: {"results": [
            {"doi": "https://doi.org/10.1/close", "title": "News sentiment and returns, revisited"}]},
    })
    assert resolve.resolve_doi_by_title(fetcher, "News sentiment and returns") is None
    assert resolve.resolve_doi_by_title(
        fetcher, "News sentiment and returns, revisited") == "10.1/close"


def test_a_source_without_a_doi_falls_back_to_the_wayback_machine():
    fetcher = FakeFetcher(json_pages={
        OPENALEX_SEARCH: {"results": []},
        WAYBACK: {"archived_snapshots": {"closest": {
            "available": True, "url": "https://web.archive.org/web/2023/https://news.example/a"}}},
    })
    candidate = {"url": "https://news.example/a", "title": "A news item", "source_class": "NEW"}
    locations, _ = resolve.plan(fetcher, candidate)
    assert [loc.provenance for loc in locations][-1] == "wayback"
    assert locations[-1].licence == "unknown"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_resolve.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.resolve'`

- [ ] **Step 3: Create `claimstone/resolve.py`**

Move `Location`, `unpaywall_locations`, `openalex_locations`, `resolve_doi_by_title`, `_version_rank` and `plan_locations` out of the draft `claimstone/acquire.py` unchanged, rename `plan_locations` to `plan`, and add the Wayback step. The module header and the new parts:

```python
"""Where a legal copy of this source might live, in the order worth trying.

Open access first, always. A publisher that returns 403 is not argued with: Unpaywall and
OpenAlex are asked where a free copy lives and the cascade continues there. A shadow
library is never a location — `excluded_hosts` is enforced in net.Fetcher before any
request, and this module never proposes one.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Any

from claimstone import ids, net

KNOWN_WALLS = (
    "sciencedirect.com", "onlinelibrary.wiley.com", "link.springer.com",
    "tandfonline.com", "jstor.org", "academic.oup.com", "papers.ssrn.com",
    "journals.sagepub.com", "doi.org",
)

WAYBACK_API = "https://archive.org/wayback/available?url="


@dataclass(frozen=True)
class Location:
    """One place a copy might live, and why we believe it."""

    url: str
    provenance: str           # unpaywall | openalex | arxiv | candidate | wayback
    version: str = ""         # publishedVersion | acceptedVersion | submittedVersion
    licence: str | None = None
    oa_status: str | None = None
    host_type: str | None = None
```

Then, after the moved functions, add:

```python
def wayback_location(fetcher: net.FetcherLike, url: str) -> Location | None:
    """The last resort for a source with no DOI: a legal archived snapshot.

    A news page eighteen months old is often dead or behind a wall. `licence` is recorded
    as "unknown" rather than left absent: "nobody wrote it down" and "we did not look" are
    different facts and the ledger must keep them apart.
    """
    if not url:
        return None
    payload, _ = fetcher.get_json(WAYBACK_API + urllib.parse.quote(url, safe=""))
    snapshot = ((payload or {}).get("archived_snapshots") or {}).get("closest") or {}
    if snapshot.get("available") and snapshot.get("url"):
        return Location(str(snapshot["url"]), "wayback", licence="unknown")
    return None


def plan(
    fetcher: net.FetcherLike, candidate: dict[str, Any], *, use_apis: bool = True
) -> tuple[list[Location], str | None]:
    """Build the cascade for one candidate, cheapest and most likely first."""
    doi = ids.normalize_doi(candidate.get("doi")) or ids.normalize_doi(candidate.get("url"))
    original = str(candidate.get("url") or "")
    on_a_wall = bool(original) and any(w in net.host_of(original) for w in KNOWN_WALLS)
    oa_status: str | None = None
    locations: list[Location] = []

    arxiv = ids.arxiv_id(original) or ids.arxiv_id(candidate.get("title"))
    if arxiv:
        locations.append(
            Location(f"https://arxiv.org/pdf/{arxiv}", "arxiv", "submittedVersion", oa_status="green")
        )

    if original and not on_a_wall:
        locations.append(Location(original, "candidate"))

    if not doi and use_apis and candidate.get("title"):
        doi = resolve_doi_by_title(fetcher, str(candidate["title"]))

    if doi and use_apis:
        upw, oa_status = unpaywall_locations(fetcher, doi)
        locations.extend(upw)
        if not upw:
            locations.extend(openalex_locations(fetcher, doi))

    ordered = sorted(locations, key=lambda loc: _version_rank(loc.version))

    # A known wall is tried last: better a landing page than nothing, but only after
    # every legal open copy has been attempted.
    if on_a_wall:
        ordered.append(Location(original, "candidate"))

    # No DOI and no arXiv id means no open-access infrastructure exists for this source.
    # The archive is the only remaining legal option, and it goes after the live URL.
    if not doi and not arxiv and use_apis:
        snapshot = wayback_location(fetcher, original)
        if snapshot:
            ordered.append(snapshot)

    deduped: list[Location] = []
    seen: set[str] = set()
    for loc in ordered:
        key = ids.normalize_url(loc.url)
        if key and key not in seen:
            seen.add(key)
            deduped.append(loc)
    return deduped, oa_status
```

Note the ordering change from the draft: the wall is appended **after** the version sort rather than before it, so sorting cannot promote it back up the list. That was latent in the draft and only shows when a wall URL has a version string.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_resolve.py -q`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add claimstone/resolve.py tests/test_resolve.py
git commit -m "resolve: the cascade as its own module, with an archive fallback

Moves the location planning out of acquire so it can be tested without a store
or a ledger. Adds the Wayback step for sources with no DOI and no arXiv id,
where no open-access infrastructure exists at all, and appends the known wall
after the version sort so sorting cannot promote it back up the list.

<trailer>"
```

---

### Task 4: Orchestration and the ledger row

Implements spec §6 (schema and its three rules).

**Files:**
- Rewrite: `claimstone/acquire.py`
- Create: `tests/test_acquire.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_acquire.py`:

```python
"""Orchestration: plan, attempt, gate, store, record. Never raises on a failed fetch."""

import pytest

from claimstone import acquire, net
from claimstone.store import Store
from tests.fakes import FakeFetcher, fail, ok
from tests.test_fulltext import page, pdf


def candidate(**overrides):
    base = {"candidate_key": "doi:10.1/abc", "source_id": "S01", "source_class": "ACA",
            "doi": "10.1/abc", "url": "https://repo.example/paper.pdf", "title": "A paper"}
    return {**base, **overrides}


def test_a_candidate_without_a_source_class_is_an_error(tmp_path):
    store = Store("t", base=tmp_path)
    with pytest.raises(acquire.MissingSourceClass):
        acquire.acquire_one(FakeFetcher(), store, candidate(source_class=None), use_apis=False)


def test_a_gated_landing_page_is_not_an_acquisition(tmp_path):
    store = Store("t", base=tmp_path)
    url = "https://publisher.example/article"
    fetcher = FakeFetcher(pages={url: ok(url, page(40, "<p>Purchase PDF</p>"), "text/html")})
    row = acquire.acquire_one(fetcher, store, candidate(url=url, doi=None), use_apis=False)
    assert row["acquired"] is False
    assert row["failure_class"] == net.LANDING
    assert row["attempts"][-1]["gate_kind"] == "LANDING_PAGE_ONLY"


def test_a_real_pdf_is_stored_under_its_hash(tmp_path):
    store = Store("t", base=tmp_path)
    url = "https://repo.example/paper.pdf"
    fetcher = FakeFetcher(pages={url: ok(url, pdf(), "application/pdf")})
    row = acquire.acquire_one(fetcher, store, candidate(), use_apis=False)
    assert row["acquired"] is True
    assert row["gate"]["kind"] == "PDF_FULLTEXT"
    assert row["gate"]["gate_version"] == 1
    assert (tmp_path / "t" / "raw" / f"{row['sha256']}.pdf").exists()


def test_the_cascade_continues_past_a_403(tmp_path):
    store = Store("t", base=tmp_path)
    wall = "https://www.sciencedirect.com/science/article/pii/S03"
    open_copy = "https://repo.example/paper.pdf"
    fetcher = FakeFetcher(
        pages={wall: fail(wall, 403, net.PAYWALL), open_copy: ok(open_copy, pdf())},
        json_pages={"https://api.unpaywall.org/v2/": {
            "oa_status": "green",
            "oa_locations": [{"url_for_pdf": open_copy, "version": "acceptedVersion",
                              "license": "cc-by"}]}},
    )
    row = acquire.acquire_one(fetcher, store, candidate(url=wall))
    assert row["acquired"] is True
    assert row["provenance"] == "unpaywall"
    assert row["licence"] == "cc-by"
    # The wall was tried and refused before the open copy succeeded; both are on the row.
    assert [a["http_status"] for a in row["attempts"]] == [403, 200]


def test_every_attempt_is_kept_not_just_the_last(tmp_path):
    store = Store("t", base=tmp_path)
    a, b = "https://a.example/x.pdf", "https://b.example/y.pdf"
    fetcher = FakeFetcher(
        pages={a: fail(a, 404, net.NOT_FOUND), b: fail(b, 403, net.PAYWALL)},
        json_pages={"https://api.unpaywall.org/v2/": {
            "oa_status": "closed",
            "oa_locations": [{"url": a}, {"url": b}]}},
    )
    row = acquire.acquire_one(fetcher, store, candidate(url="https://doi.org/10.1/abc"))
    assert len(row["attempts"]) >= 2
    assert row["failure_class"] == net.PAYWALL


def test_a_candidate_with_nowhere_to_look_says_so(tmp_path):
    store = Store("t", base=tmp_path)
    row = acquire.acquire_one(
        FakeFetcher(), store, candidate(url="", doi=None, title=""), use_apis=False)
    assert row["acquired"] is False
    assert row["failure_class"] == net.NO_LOCATIONS
    assert row["attempts"] == []


def test_the_campaign_is_written_on_every_row(tmp_path):
    store = Store("t", base=tmp_path)
    url = "https://repo.example/paper.pdf"
    fetcher = FakeFetcher(pages={url: ok(url, pdf())})
    row = acquire.acquire_one(fetcher, store, candidate(), campaign="elsevier-retry",
                              use_apis=False)
    assert row["campaign"] == "elsevier-retry"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_acquire.py -q`
Expected: FAIL with `AttributeError: module 'claimstone.acquire' has no attribute 'MissingSourceClass'`

- [ ] **Step 3: Rewrite `claimstone/acquire.py`**

Replace the whole file. Everything the draft had about locations now lives in `resolve.py`.

```python
"""Stage 2 — acquire: candidates become frozen texts, legally, with every attempt recorded.

This is the binding constraint on the science, not extraction quality: the corpus that
motivated this project sits at 0.42 because publishers return 403. Every attempt is
recorded, successful or not, because a swallowed failure inflates the rate that decides
whether a round may produce verdicts at all.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterable, Iterator

from claimstone import fulltext, net, resolve
from claimstone.store import Store

PDF_TYPES = ("application/pdf", "application/octet-stream")
HTML_TYPES = ("text/html", "application/xhtml+xml", "application/xml", "text/xml", "text/plain")

ROUTINE = "routine"


class MissingSourceClass(ValueError):
    """Invariant 6: a blog post and a refereed paper never share a pool unrecorded."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _suffix_for(content_type: str, url: str) -> str:
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        return ".pdf"
    if "xml" in content_type:
        return ".xml"
    return ".html"


def acquire_one(
    fetcher: net.FetcherLike,
    store: Store,
    candidate: dict[str, Any],
    *,
    campaign: str = ROUTINE,
    use_apis: bool = True,
    thresholds: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Try the cascade for one candidate. Returns the ledger row; never raises on a fetch."""
    if not candidate.get("source_class"):
        raise MissingSourceClass(
            f"candidate {candidate.get('candidate_key')!r} carries no source_class; "
            "a pool that mixes classes unrecorded cannot be synthesised (invariant 6)"
        )

    th = {**fulltext.DEFAULT_THRESHOLDS, **(thresholds or {})}
    locations, oa_status = resolve.plan(fetcher, candidate, use_apis=use_apis)
    attempts: list[dict[str, Any]] = []
    common = {
        "candidate_key": candidate["candidate_key"],
        "source_id": candidate.get("source_id"),
        "source_class": candidate["source_class"],
        "campaign": campaign,
        "fetched_at": _now(),
    }

    for location in locations:
        expect = PDF_TYPES if location.url.lower().endswith(".pdf") else PDF_TYPES + HTML_TYPES
        outcome = fetcher.get(location.url, expect=expect)
        attempt = outcome.as_row() | {
            "provenance": location.provenance,
            "version": location.version,
            "gate_kind": None,
        }

        if not outcome.ok or not outcome.body:
            attempts.append(attempt)
            continue

        verdict = fulltext.classify(outcome.body, outcome.content_type, location.url, th)
        attempt["gate_kind"] = verdict.kind
        attempt["gate_reason"] = verdict.reason
        attempts.append(attempt)

        if not verdict.accepted:
            # A 200 carrying a landing page is a failure of acquisition. Keep going: a
            # later location in the cascade may hold the real thing.
            attempt["failure_class"] = verdict.kind
            continue

        digest, path = store.store_bytes(
            outcome.body, _suffix_for(outcome.content_type, location.url)
        )
        return common | {
            "acquired": True,
            "sha256": digest,
            "stored_path": str(path),
            "url": location.url,
            "provenance": location.provenance,
            "version": location.version,
            "licence": location.licence,
            "oa_status": location.oa_status or oa_status,
            "host_type": location.host_type,
            "content_type": outcome.content_type,
            "bytes": len(outcome.body),
            "gate": verdict.as_row(th),
            "attempts": attempts,
            "failure_class": None,
        }

    return common | {
        "acquired": False,
        "sha256": None,
        "stored_path": None,
        "url": str(candidate.get("url") or ""),
        "oa_status": oa_status,
        "gate": None,
        "attempts": attempts,
        # The class of the last attempt is the honest headline: it says what stopped us.
        "failure_class": attempts[-1]["failure_class"] if attempts else net.NO_LOCATIONS,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_acquire.py -q`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add claimstone/acquire.py tests/test_acquire.py
git commit -m "acquire: gate the bytes, keep every attempt, refuse a classless candidate

A 200 carrying a landing page no longer ends the cascade successfully; it is
recorded with its gate verdict and the next location is tried. A candidate with
no source_class raises rather than defaulting, which is invariant 6 made
executable.

<trailer>"
```

---

### Task 5: The retry policy

Implements spec §7.

**Files:**
- Modify: `claimstone/acquire.py` (append `should_attempt` and `run`)
- Modify: `tests/test_acquire.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_acquire.py`:

```python
import time


def _row(failure_class, *, acquired=False, age_s=0):
    stamp = _dt.datetime.fromtimestamp(time.time() - age_s, _dt.timezone.utc)
    return {"acquired": acquired, "failure_class": failure_class,
            "fetched_at": stamp.isoformat(timespec="seconds")}


def test_a_candidate_never_tried_is_attempted():
    assert acquire.should_attempt(None, retry_classes=frozenset()) is True


def test_an_acquired_candidate_is_left_alone():
    assert acquire.should_attempt(_row(None, acquired=True), retry_classes=frozenset()) is False


def test_a_403_is_not_reattempted_without_a_named_campaign():
    assert acquire.should_attempt(_row(net.PAYWALL), retry_classes=frozenset()) is False


def test_a_403_is_reattempted_when_its_class_is_named():
    assert acquire.should_attempt(
        _row(net.PAYWALL), retry_classes=frozenset({net.PAYWALL})) is True


def test_a_fresh_timeout_waits():
    assert acquire.should_attempt(
        _row(net.TIMEOUT, age_s=60), retry_classes=frozenset(), retry_after_s=6 * 3600) is False


def test_an_old_timeout_is_retried_on_its_own():
    assert acquire.should_attempt(
        _row(net.TIMEOUT, age_s=7 * 3600), retry_classes=frozenset(), retry_after_s=6 * 3600) is True


def test_an_exhausted_budget_returns_to_the_queue():
    assert acquire.should_attempt(
        _row(net.BUDGET, age_s=7 * 3600), retry_classes=frozenset(), retry_after_s=6 * 3600) is True


def test_a_skipped_candidate_writes_no_row(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", {"candidate_key": "doi:10.1/abc", **_row(net.PAYWALL)})
    rows = list(acquire.run([candidate()], store, FakeFetcher(), use_apis=False))
    assert rows == []
    assert len(list(store.read("acquisitions.jsonl"))) == 1
```

Add `import datetime as _dt` at the top of the test file.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_acquire.py -q -k "should_attempt or skipped"`
Expected: FAIL with `AttributeError: module 'claimstone.acquire' has no attribute 'should_attempt'`

- [ ] **Step 3: Append to `claimstone/acquire.py`**

```python
DEFAULT_RETRY_AFTER_S = 6 * 3600


def _age_seconds(row: dict[str, Any]) -> float:
    stamp = row.get("fetched_at")
    if not stamp:
        return float("inf")
    try:
        when = _dt.datetime.fromisoformat(str(stamp))
    except ValueError:
        return float("inf")
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.timezone.utc)
    return (_dt.datetime.now(_dt.timezone.utc) - when).total_seconds()


def should_attempt(
    previous: dict[str, Any] | None,
    *,
    retry_classes: frozenset[str],
    retry_after_s: int = DEFAULT_RETRY_AFTER_S,
) -> bool:
    """Decide whether to knock again.

    Terminal failures are left alone unless their class was explicitly named, which is the
    named-campaign rule: a host that returned 403 is not re-requested on a routine run.
    Transient failures come back on their own once the TTL has passed, so a downloader
    blocked for an afternoon does not quietly leave those sources out of the denominator.
    """
    if previous is None:
        return True
    if previous.get("acquired"):
        return False
    failure_class = previous.get("failure_class")
    if failure_class in retry_classes:
        return True
    if net.is_terminal(failure_class):
        return False
    return _age_seconds(previous) >= retry_after_s


def run(
    candidates: Iterable[dict[str, Any]],
    store: Store,
    fetcher: net.FetcherLike,
    *,
    campaign: str = ROUTINE,
    retry_classes: frozenset[str] = frozenset(),
    retry_after_s: int = DEFAULT_RETRY_AFTER_S,
    use_apis: bool = True,
    thresholds: dict[str, int] | None = None,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Acquire what the retry policy allows. A candidate it declines writes no row."""
    previous = store.latest_by("acquisitions.jsonl", "candidate_key")
    attempted = 0
    for candidate in candidates:
        if limit is not None and attempted >= limit:
            return
        prior = previous.get(str(candidate["candidate_key"]))
        if not should_attempt(prior, retry_classes=retry_classes, retry_after_s=retry_after_s):
            continue
        row = acquire_one(
            fetcher, store, candidate, campaign=campaign, use_apis=use_apis, thresholds=thresholds
        )
        row["attempt_no"] = int((prior or {}).get("attempt_no") or 0) + 1
        store.append("acquisitions.jsonl", row)
        attempted += 1
        yield row
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_acquire.py -q`
Expected: PASS, 15 passed

- [ ] **Step 5: Commit**

```bash
git add claimstone/acquire.py tests/test_acquire.py
git commit -m "acquire: terminal failures need a named campaign, transient ones come back

A routine run no longer knocks on every wall it knocked on last time. An
exhausted domain budget is transient on purpose: the source returns to the queue
instead of disappearing from the denominator, which is how a blocked downloader
disguises itself as a saturated corpus.

<trailer>"
```

---

### Task 6: The rate and the floor

Implements spec §6 rule 2 and §8.

**Files:**
- Create: `claimstone/admissibility.py`
- Create: `tests/test_admissibility.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_admissibility.py`:

```python
"""The figure that gates verdicts, and the collapse that keeps it honest."""

from claimstone import admissibility
from claimstone.config import load_project
from claimstone.store import Store


def _ledger(store, rows):
    for row in rows:
        store.append("acquisitions.jsonl", row)


def row(key, *, acquired, klass="ACA", failure=None, url="https://x.example/a"):
    return {"candidate_key": key, "source_class": klass, "acquired": acquired,
            "failure_class": failure, "url": url, "fetched_at": "2026-09-22T10:00:00+00:00"}


def test_a_failed_retry_does_not_erase_a_recorded_success(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row("a", acquired=True), row("a", acquired=False, failure="PAYWALL_403")])
    assert admissibility.rate(store)["acquired"] == 1


def test_the_rate_is_acquired_over_attempted(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row("a", acquired=True), row("b", acquired=True),
                    row("c", acquired=False, failure="PAYWALL_403")])
    result = admissibility.rate(store)
    assert (result["attempted"], result["acquired"]) == (3, 2)
    assert round(result["rate"], 2) == 0.67


def test_classes_are_reported_separately(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row("a", acquired=True, klass="ACA"),
                    row("b", acquired=False, klass="DOC", failure="NOT_FOUND_404"),
                    row("c", acquired=False, klass="DOC", failure="PAYWALL_403")])
    by_class = admissibility.rate(store)["by_class"]
    assert by_class["ACA"] == {"attempted": 1, "acquired": 1, "rate": 1.0}
    assert by_class["DOC"]["rate"] == 0.0


def test_an_empty_ledger_has_no_rate_rather_than_a_rate_of_zero(tmp_path):
    store = Store("t", base=tmp_path)
    result = admissibility.rate(store)
    assert result["attempted"] == 0
    assert result["rate"] is None


def test_below_the_floor_the_round_produces_no_verdicts(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row("a", acquired=True), row("b", acquired=False, failure="PAYWALL_403")])
    project = load_project("projects/example-news-and-returns")
    verdict = admissibility.admit(project, store)
    assert verdict["status"] == "INSUFFICIENT_ACQUISITION"
    assert verdict["floor"] == 0.80


def test_at_or_above_the_floor_the_round_is_admissible(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row(k, acquired=True) for k in "abcd"] +
                   [row("e", acquired=False, failure="PAYWALL_403")])
    project = load_project("projects/example-news-and-returns")
    assert admissibility.admit(project, store)["status"] == "OK"


def test_there_is_no_override(tmp_path):
    import inspect

    source = inspect.getsource(admissibility.admit)
    assert "force" not in source and "override" not in source
```

That last test is unusual and deliberate: invariant 3 says the floor has no override flag, and a test is the cheapest way to make a future contributor argue with the spec rather than add one quietly.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_admissibility.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.admissibility'`

- [ ] **Step 3: Create `claimstone/admissibility.py`**

```python
"""The acquisition rate, and whether it permits verdicts at all.

A corpus read at 42% that certifies itself complete is worse than no corpus: that is the
observed state that motivated this project. So the rate is computed every round, reported
per source class before it is reported pooled, and compared against a floor the project
declared in advance. There is no flag that waives it.
"""

from __future__ import annotations

from typing import Any

from claimstone import net
from claimstone.config import Project
from claimstone.store import Store

OK = "OK"
INSUFFICIENT = "INSUFFICIENT_ACQUISITION"


def collapse(store: Store) -> dict[str, dict[str, Any]]:
    """One row per candidate, preferring the latest **successful** attempt.

    Plain latest-wins would let a retry campaign that fails erase a success whose bytes are
    on disk, and the rate would fall while the corpus was unchanged.
    """
    best: dict[str, dict[str, Any]] = {}
    for row in store.read("acquisitions.jsonl"):
        key = row.get("candidate_key")
        if key is None:
            continue
        key = str(key)
        held = best.get(key)
        if held is None or row.get("acquired") or not held.get("acquired"):
            best[key] = row
    return best


def rate(store: Store) -> dict[str, Any]:
    """Acquisition accounting. `rate` is None when nothing was attempted — not 0.0."""
    rows = collapse(store)
    attempted = len(rows)
    acquired = sum(1 for row in rows.values() if row.get("acquired"))

    by_class: dict[str, dict[str, Any]] = {}
    failures: dict[str, int] = {}
    hosts: dict[str, int] = {}
    for row in rows.values():
        klass = str(row.get("source_class") or "UNCLASSIFIED")
        bucket = by_class.setdefault(klass, {"attempted": 0, "acquired": 0, "rate": 0.0})
        bucket["attempted"] += 1
        if row.get("acquired"):
            bucket["acquired"] += 1
            continue
        failures[str(row.get("failure_class"))] = failures.get(str(row.get("failure_class")), 0) + 1
        host = net.host_of(str(row.get("url") or ""))
        if host:
            hosts[host] = hosts.get(host, 0) + 1

    for bucket in by_class.values():
        bucket["rate"] = bucket["acquired"] / bucket["attempted"]

    return {
        "attempted": attempted,
        "acquired": acquired,
        "rate": (acquired / attempted) if attempted else None,
        "by_class": dict(sorted(by_class.items())),
        "failures_by_class": dict(sorted(failures.items(), key=lambda kv: -kv[1])),
        "failures_by_host": dict(sorted(hosts.items(), key=lambda kv: -kv[1])),
    }


def admit(project: Project, store: Store) -> dict[str, Any]:
    """Whether this round may produce verdicts. Invariant 3: nothing waives the floor."""
    measured = rate(store)
    achieved = measured["rate"]
    status = OK if achieved is not None and achieved >= project.acquisition_floor else INSUFFICIENT
    return {"status": status, "floor": project.acquisition_floor, **measured}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_admissibility.py -q`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add claimstone/admissibility.py tests/test_admissibility.py
git commit -m "admissibility: a failed retry must not erase a success, and nothing waives the floor

Latest-wins collapse let a retry campaign lower the rate while the bytes sat on
disk. The collapse now prefers the latest successful row. An empty ledger
reports no rate rather than a rate of zero, because those are different facts.

<trailer>"
```

---

### Task 7: The manifest as the fourth project file

Implements spec §11.

**Files:**
- Modify: `claimstone/config.py` (add after `load_questions`, and extend `Project` and `load_project`)
- Create: `tests/test_manifest.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_manifest.py`:

```python
"""The manifest holds the source list constant, so the rate is comparable round to round."""

import pytest

from claimstone.config import ConfigError, load_manifest

HEADER = "source_id\tclass\tformat\turl\ttitle\n"


def write(tmp_path, body):
    (tmp_path / "manifest.tsv").write_text(HEADER + body, encoding="utf-8")
    return tmp_path


def test_a_well_formed_manifest_loads(tmp_path):
    root = write(tmp_path, "S01\tACA\tpdf\thttps://x.example/a\tA paper\n")
    entries = load_manifest(root, frozenset({"ACA"}))
    assert entries[0].source_id == "S01"
    assert entries[0].source_class == "ACA"


def test_an_undeclared_class_is_a_configuration_error(tmp_path):
    root = write(tmp_path, "S01\tNOPE\tpdf\thttps://x.example/a\tA paper\n")
    with pytest.raises(ConfigError, match="NOPE"):
        load_manifest(root, frozenset({"ACA"}))


def test_a_duplicate_source_id_is_an_error(tmp_path):
    root = write(tmp_path, "S01\tACA\tpdf\thttps://x.example/a\tA\nS01\tACA\tpdf\thttps://y.example/b\tB\n")
    with pytest.raises(ConfigError, match="S01"):
        load_manifest(root, frozenset({"ACA"}))


def test_a_row_with_neither_url_nor_title_is_an_error(tmp_path):
    root = write(tmp_path, "S01\tACA\tpdf\t\t\n")
    with pytest.raises(ConfigError, match="S01"):
        load_manifest(root, frozenset({"ACA"}))


def test_a_missing_manifest_is_not_an_error(tmp_path):
    assert load_manifest(tmp_path, frozenset({"ACA"})) == ()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_manifest.py -q`
Expected: FAIL with `ImportError: cannot import name 'load_manifest'`

- [ ] **Step 3: Modify `claimstone/config.py`**

Add the dataclass beside the others:

```python
@dataclass(frozen=True)
class ManifestEntry:
    source_id: str
    source_class: str
    declared_format: str
    url: str
    title: str
```

Add `manifest: tuple[ManifestEntry, ...] = ()` as the last field of `Project`.

Add the loader after `load_questions`:

```python
MANIFEST_COLUMNS = ("source_id", "class", "format", "url", "title")


def load_manifest(root: pathlib.Path, class_ids: frozenset[str]) -> tuple[ManifestEntry, ...]:
    """Load the optional curated source list. Absent is fine; malformed is not.

    Its purpose is to hold the source list constant across rounds: the milestone asks
    whether the acquisition rate moved on the manifest that produced 0.42, not whether a
    fresh search found easier papers.
    """
    import csv

    path = pathlib.Path(root) / "manifest.tsv"
    if not path.exists():
        return ()

    entries: list[ManifestEntry] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        missing = [c for c in MANIFEST_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ConfigError(f"manifest.tsv: missing column(s): {', '.join(missing)}")
        for line_no, entry in enumerate(reader, start=2):
            source_id = (entry.get("source_id") or "").strip()
            klass = (entry.get("class") or "").strip()
            url = (entry.get("url") or "").strip()
            title = (entry.get("title") or "").strip()
            if not source_id:
                raise ConfigError(f"manifest.tsv line {line_no}: 'source_id' is required")
            if klass not in class_ids:
                raise ConfigError(
                    f"manifest.tsv line {line_no}: class {klass!r} is not declared in "
                    f"sources.yaml (declared: {', '.join(sorted(class_ids))})"
                )
            if not url and not title:
                raise ConfigError(
                    f"manifest.tsv line {line_no} ({source_id}): needs a 'url' or a 'title'"
                )
            entries.append(
                ManifestEntry(source_id, klass, (entry.get("format") or "").strip(), url, title)
            )

    _require_unique([e.source_id for e in entries], what="source_id", where="manifest.tsv")
    return tuple(entries)
```

In `load_project`, after the questions are loaded, add `manifest = load_manifest(path, frozenset(c.id for c in classes))` and pass `manifest=manifest` to the `Project(...)` construction.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_manifest.py tests/test_config.py -q`
Expected: PASS, 5 passed plus the existing config tests

- [ ] **Step 5: Let a project override the gate thresholds**

Spec §5 says the thresholds are overridable per project under an `acquisition:` key in
`sources.yaml`. Nothing reads that key yet. Add a separate loader rather than changing
`load_sources`, which works and is not the concern here.

Append to `tests/test_manifest.py`:

```python
from claimstone.config import load_gate_thresholds


def test_absent_acquisition_key_means_the_defaults(tmp_path):
    (tmp_path / "sources.yaml").write_text("classes: []\nacquisition_floor: 0.8\n", encoding="utf-8")
    assert load_gate_thresholds(tmp_path) == {}


def test_a_project_may_raise_the_text_threshold(tmp_path):
    (tmp_path / "sources.yaml").write_text(
        "classes: []\nacquisition_floor: 0.8\nacquisition:\n  min_text_chars: 5000\n",
        encoding="utf-8")
    assert load_gate_thresholds(tmp_path) == {"min_text_chars": 5000}


def test_an_unknown_threshold_name_is_an_error(tmp_path):
    (tmp_path / "sources.yaml").write_text(
        "classes: []\nacquisition_floor: 0.8\nacquisition:\n  min_chars: 5000\n",
        encoding="utf-8")
    with pytest.raises(ConfigError, match="min_chars"):
        load_gate_thresholds(tmp_path)
```

Add to `claimstone/config.py`, after `load_manifest`:

```python
GATE_THRESHOLD_NAMES = ("min_pdf_bytes", "min_text_chars", "paywall_doubt_chars")


def load_gate_thresholds(root: pathlib.Path) -> dict[str, int]:
    """Per-project overrides for the content gate. Absent means the engine defaults.

    A misspelt key is an error rather than a silent no-op: a threshold the operator
    believed they had raised, and had not, produces a rate they would trust wrongly.
    """
    raw = _read_yaml(pathlib.Path(root) / "sources.yaml").get("acquisition") or {}
    if not isinstance(raw, dict):
        raise ConfigError("sources.yaml: 'acquisition' must be a mapping")
    unknown = sorted(set(raw) - set(GATE_THRESHOLD_NAMES))
    if unknown:
        raise ConfigError(
            f"sources.yaml: unknown acquisition threshold(s): {', '.join(unknown)} "
            f"(known: {', '.join(GATE_THRESHOLD_NAMES)})"
        )
    for name, value in raw.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ConfigError(f"sources.yaml: acquisition.{name} must be a non-negative integer")
    return {str(k): int(v) for k, v in raw.items()}
```

Add `gate_thresholds: dict[str, int] = field(default_factory=dict)` to `Project` — this
requires `from dataclasses import dataclass, field` at the top of `config.py` — and set it
in `load_project` with `gate_thresholds=load_gate_thresholds(path)`.

Finally, thread it through the CLI. In `_acquire` (Task 8), pass
`thresholds=project.gate_thresholds` to `acquire.run(...)`.

Run: `.venv/bin/pytest tests/test_manifest.py -q`
Expected: PASS, 8 passed

- [ ] **Step 6: Add the manifest to `.gitignore`**

Append under the existing project block:

```
# A project's curated source list is its reading list: same reason as projects/*.
projects/*/manifest.tsv
```

- [ ] **Step 7: Commit**

```bash
git add claimstone/config.py tests/test_manifest.py .gitignore
git commit -m "config: the manifest is the fourth project file, validated like the others

An undeclared source class is a configuration error rather than a skipped row:
a silently dropped source is a silently wrong denominator. Gitignored for the
same reason as the rest of projects/ — it is a reading list.

<trailer>"
```

---

### Task 8: Wiring the CLI

Implements spec §8.

**Files:**
- Modify: `claimstone/cli.py`
- Modify: `claimstone/discover.py` (make `import_manifest` take validated entries)
- Create: `tests/test_cli_acquire.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_acquire.py`:

```python
"""The CLI is where the floor becomes enforceable by a script."""

from claimstone.cli import build_parser, main


def test_acquire_is_no_longer_a_placeholder():
    args = build_parser().parse_args(["acquire", "projects/example-news-and-returns"])
    assert args.func.__name__ != "_not_implemented"


def test_retrying_a_terminal_class_requires_a_named_campaign(capsys):
    code = main(["acquire", "projects/example-news-and-returns", "--retry-class", "PAYWALL_403"])
    assert code == 2
    assert "--campaign" in capsys.readouterr().err


def test_report_gate_exits_three_below_the_floor(tmp_path, capsys):
    from claimstone.store import Store

    store = Store("example-news-and-returns", base=tmp_path)
    store.append("acquisitions.jsonl", {"candidate_key": "a", "source_class": "ACA",
                                        "acquired": False, "failure_class": "PAYWALL_403",
                                        "url": "https://x.example/a"})
    code = main(["report", "projects/example-news-and-returns", "--store", str(tmp_path), "--gate"])
    assert code == 3
    assert "INSUFFICIENT_ACQUISITION" in capsys.readouterr().out
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_cli_acquire.py -q`
Expected: FAIL — `acquire` is still bound to `_not_implemented`

- [ ] **Step 3: Rewrite the command table in `claimstone/cli.py`**

Replace the `STAGES` loop and add the three commands. Keep `validate` untouched, and keep the placeholder loop for the four stages that remain unimplemented.

```python
STAGES = ("normalize", "extract", "review", "synthesize")


def _store_for(args, project) -> "Store":
    from claimstone.store import Store

    return Store(project.name, base=args.store)


def _import_manifest(args: argparse.Namespace) -> int:
    from claimstone import discover
    from claimstone.store import Store

    project = load_project(args.project)
    if not project.manifest:
        print(f"no manifest.tsv under {args.project}/", file=sys.stderr)
        return 1
    result = discover.import_manifest(Store(project.name, base=args.store), project.manifest)
    print(f"{project.name}: {result['new']} new of {result['rows']} manifest rows")
    return 0


def _acquire(args: argparse.Namespace) -> int:
    from claimstone import acquire, net
    from claimstone.store import Store

    retry_classes = frozenset(args.retry_class or ())
    if retry_classes and not args.campaign:
        print(
            "refusing to re-request a terminal failure on an unnamed run: pass --campaign "
            "NAME so the ledger records why this round knocked again",
            file=sys.stderr,
        )
        return 2

    project = load_project(args.project)
    store = Store(project.name, base=args.store)
    fetcher = net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts))
    candidates = list(store.latest_by("candidates.jsonl", "candidate_key").values())

    done = 0
    for row in acquire.run(
        candidates, store, fetcher,
        campaign=args.campaign or acquire.ROUTINE,
        retry_classes=retry_classes,
        use_apis=not args.no_apis,
        thresholds=project.gate_thresholds,
        limit=args.limit,
    ):
        done += 1
        mark = "ok  " if row["acquired"] else "fail"
        detail = row.get("provenance") or row.get("failure_class")
        print(f"{mark} {row.get('source_id') or row['candidate_key']}  {detail}")
    print(f"{done} attempted")
    return 0


def _report(args: argparse.Namespace) -> int:
    from claimstone import admissibility
    from claimstone.store import Store

    project = load_project(args.project)
    result = admissibility.admit(project, Store(project.name, base=args.store))

    if args.json:
        import json

        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        achieved = "—" if result["rate"] is None else f"{result['rate']:.2f}"
        print(f"{project.name} — {result['attempted']} candidates")
        # Per class before pooled: D3 says classes are not mixed, and an aggregate that
        # hides one class sitting at zero is a different fact from a uniform one.
        for klass, bucket in result["by_class"].items():
            print(f"  {klass:<6} {bucket['acquired']}/{bucket['attempted']}  {bucket['rate']:.2f}")
        print(f"  total  {result['acquired']}/{result['attempted']}  {achieved}"
              f"   floor {result['floor']:.2f}   {result['status']}")
        for name, counts in (("failures", result["failures_by_class"]),
                             ("by host", result["failures_by_host"])):
            if counts:
                print(f"  {name}  " + "  ".join(f"{k} {v}" for k, v in counts.items()))

    return 3 if args.gate and result["status"] == admissibility.INSUFFICIENT else 0
```

And in `build_parser`, after the `validate` block:

```python
    for name, handler, help_text in (
        ("import-manifest", _import_manifest, "seed candidates from manifest.tsv"),
        ("acquire", _acquire, "stage 2: obtain the full texts"),
        ("report", _report, "acquisition rate, per class, against the floor"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("project", help="path to a project directory")
        command.add_argument("--store", default="store", help="where generated data lives")
        command.set_defaults(func=handler)
        if name == "acquire":
            command.add_argument("--campaign", help="name this run; required with --retry-class")
            command.add_argument("--retry-class", action="append",
                                 help="re-request a terminal failure class, e.g. PAYWALL_403")
            command.add_argument("--limit", type=int, default=None)
            command.add_argument("--no-apis", action="store_true",
                                 help="plan from the candidate URL alone; no Unpaywall or OpenAlex")
            command.add_argument("--dry-run", action="store_true",
                                 help="print the planned cascade and fetch nothing")
        if name == "report":
            command.add_argument("--json", action="store_true")
            command.add_argument("--gate", action="store_true",
                                 help="exit 3 when the round is INSUFFICIENT_ACQUISITION")
```

- [ ] **Step 4: Implement `--dry-run` inside `_acquire`**

Insert immediately before the `for row in acquire.run(...)` loop:

```python
    if args.dry_run:
        from claimstone import resolve

        for candidate in candidates:
            locations, _ = resolve.plan(fetcher, candidate, use_apis=not args.no_apis)
            print(f"{candidate.get('source_id') or candidate['candidate_key']}")
            for position, location in enumerate(locations, start=1):
                print(f"  {position}. {location.provenance:<10} {location.url}")
        return 0
```

- [ ] **Step 5: Change `discover.import_manifest` to take validated entries**

Replace its signature and body so the parsing lives in `config.load_manifest` and this function only writes rows:

```python
def import_manifest(store: Store, entries: Iterable[Any]) -> dict[str, Any]:
    """Seed candidates from a validated manifest. Parsing and validation live in config."""
    known = set(store.latest_by("candidates.jsonl", "candidate_key"))
    added = 0
    rows = 0
    for entry in entries:
        rows += 1
        row = _row(
            title=entry.title,
            url=entry.url,
            doi=ids.normalize_doi(entry.url),
            year=None,
            venue="",
            source_api="manifest",
            query="manifest.tsv",
            topic_id="",
            channel=CHANNEL_KEYWORD,
            extra={
                "source_id": entry.source_id,
                "source_class": entry.source_class,
                "declared_format": entry.declared_format,
            },
        )
        if row["candidate_key"] in known:
            continue
        known.add(row["candidate_key"])
        store.append("candidates.jsonl", row)
        added += 1
    return {"rows": rows, "new": added, "total": len(known)}
```

- [ ] **Step 6: Run the whole suite**

Run: `.venv/bin/pytest -q`
Expected: PASS, all tests

Run: `.venv/bin/claimstone validate --all-projects`
Expected: `OK` for both projects

- [ ] **Step 7: Commit**

```bash
git add claimstone/cli.py claimstone/discover.py tests/test_cli_acquire.py
git commit -m "cli: import-manifest, acquire and report, with the floor enforceable by exit code

acquire exits 0 even below the floor, because measuring is not failing; report
--gate exits 3 so a script cannot ignore an inadmissible round. Refusing
--retry-class without --campaign is the named-campaign rule at the only place a
human can violate it.

<trailer>"
```

---

### Task 9: The contract document and the live smoke test

Implements spec §12 and §13.

**Files:**
- Create: `docs/contracts/acquisitions.md`
- Create: `tests/test_live.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Register the marker in `pyproject.toml`**

Append:

```toml
[tool.pytest.ini_options]
markers = ["network: hits the real internet; skipped unless CLAIMSTONE_LIVE=1"]
```

- [ ] **Step 2: Write `tests/test_live.py`**

```python
"""Three known open-access DOIs, against the real internet.

Skipped everywhere by default, including CI. Its job is to catch the cascade rotting —
an API changing shape, a host starting to refuse us — which no fake can detect.
"""

import os

import pytest

from claimstone import net, resolve

pytestmark = pytest.mark.skipif(
    os.environ.get("CLAIMSTONE_LIVE") != "1",
    reason="set CLAIMSTONE_LIVE=1 and CLAIMSTONE_CONTACT_EMAIL to run",
)

KNOWN_OA_DOIS = (
    "10.1371/journal.pone.0173461",
    "10.1093/nar/gkw1099",
    "10.1186/s13059-014-0550-8",
)


@pytest.mark.network
@pytest.mark.parametrize("doi", KNOWN_OA_DOIS)
def test_unpaywall_still_knows_where_the_open_copy_is(doi):
    fetcher = net.Fetcher()
    locations, oa_status = resolve.unpaywall_locations(fetcher, doi)
    assert locations, f"Unpaywall returned no open location for {doi}"
    assert oa_status in {"gold", "green", "hybrid", "bronze"}
```

- [ ] **Step 3: Verify it is skipped by default**

Run: `.venv/bin/pytest tests/test_live.py -q`
Expected: `3 skipped`

- [ ] **Step 4: Write `docs/contracts/acquisitions.md`**

```markdown
# `acquisitions.jsonl` — the contract

Written by stage 2 (`claimstone acquire`). Append-only. One row per candidate per run that
the retry policy allowed; a candidate it declined writes no row, so silence means "not
tried this run" and the previous row stands.

**Stage 3 depends on two fields only — `sha256` and `stored_path`.** Everything else is
accounting, and accounting is why the file exists: the acquisition rate computed from it
decides whether a round may produce verdicts at all.

## Fields

| field | meaning |
|---|---|
| `candidate_key` | identity from `ids.candidate_key`: DOI, else folded title, else URL |
| `source_id` | the manifest's own identifier, when the candidate came from a manifest |
| `source_class` | mandatory, no default. A classless candidate raises rather than passing |
| `campaign` | which run this was; `routine` unless named. Terminal retries must name one |
| `attempt_no` | 1 for the first attempt at this candidate, incremented per recorded row |
| `acquired` | whether bytes passed the content gate. **Not** whether HTTP returned 200 |
| `gate` | the gate's verdict: `kind`, `chars`, `reason`, `gate_version`, `thresholds` |
| `sha256` | content hash of the stored bytes; `null` when not acquired |
| `stored_path` | where those bytes live under `store/<project>/raw/` |
| `url` | the location that succeeded, or the candidate URL when nothing did |
| `provenance` | who told us about that location: `unpaywall`, `openalex`, `arxiv`, `candidate`, `wayback` |
| `version` | `publishedVersion`, `acceptedVersion`, `submittedVersion`, or empty |
| `licence` | as reported by the resolver; `"unknown"` for archived web sources |
| `oa_status` | `gold`, `green`, `hybrid`, `bronze`, `closed`, or `null` where not applicable |
| `host_type` | `publisher` or `repository`, when the resolver said |
| `content_type`, `bytes` | what came back |
| `failure_class` | the class of the **last** attempt: what stopped us. `null` when acquired |
| `attempts` | every step of the cascade, in order, each with its own `failure_class` and `gate_kind` |
| `fetched_at` | UTC, ISO 8601, seconds |

`gate.thresholds` and `gate.gate_version` are on the row because a rate computed under
different thresholds is not comparable to one computed under these, and without recording
them the difference is invisible.

## Failure classes

Terminal — retrying changes nothing until the world changes, so a retry needs a named
campaign:

`PAYWALL_403` · `ROBOTS_DISALLOWED` · `EXCLUDED_HOST` · `NOT_FOUND_404` ·
`UNEXPECTED_CONTENT_TYPE` · `LANDING_PAGE_ONLY` · `TOO_SHORT` · `CORRUPT_PDF` ·
`NOT_TEXT` · `NO_LOCATIONS`

Transient — the next ordinary run tries again on its own once the TTL has passed:

`TIMEOUT` · `CONNECTION_ERROR` · `SERVER_ERROR_5XX` · `RATE_LIMITED_429` ·
`DOMAIN_BUDGET_EXHAUSTED` · `EMPTY_RESPONSE` · `WAYBACK_MISS`

An unrecognised class counts as terminal: a typo must cost a retry, not an unbounded loop
against a publisher. `DOMAIN_BUDGET_EXHAUSTED` is transient on purpose — a source dropped
because the budget ran out must return to the queue, or a blocked downloader reads as a
saturated corpus.

## Collapsing the log

A reader that wants one row per candidate takes **the latest successful row**, falling back
to the latest row only when none succeeded. Plain latest-wins would let a failed retry
campaign erase a success whose bytes are still on disk, lowering the rate while the corpus
was unchanged. `admissibility.collapse` is the reference implementation.
```

- [ ] **Step 5: Run everything and commit**

Run: `.venv/bin/pytest -q` — expected: all pass, 3 skipped
Run: `.venv/bin/claimstone validate --all-projects` — expected: OK for both

```bash
git add docs/contracts/acquisitions.md tests/test_live.py pyproject.toml
git commit -m "docs: the acquisition row contract, and a live test that is skipped by default

No fake can detect an API changing shape or a host starting to refuse us, so
there is one test against the real internet — off everywhere, including CI,
until CLAIMSTONE_LIVE=1 is set.

<trailer>"
```

---

### Task 10: The first real number

This task produces the deliverable. It needs `projects/alembic-s4/manifest.tsv`, which the user supplies.

- [ ] **Step 1: Confirm the manifest is present and valid**

Run: `.venv/bin/claimstone validate projects/alembic-s4`
Expected: `OK alembic-s4: …`. A malformed manifest fails here with the offending line number.

- [ ] **Step 2: Set the contact address**

Run: `export CLAIMSTONE_CONTACT_EMAIL=<the address>`
Crossref and Unpaywall require it, and `net.Fetcher` refuses to construct without it.

- [ ] **Step 3: Seed the candidates**

Run: `.venv/bin/claimstone import-manifest projects/alembic-s4`
Expected: `alembic-s4: 26 new of 26 manifest rows`

- [ ] **Step 4: Look at the plan before spending requests**

Run: `.venv/bin/claimstone acquire projects/alembic-s4 --dry-run`
Expected: 26 blocks, each listing its cascade in order. Check by eye that no excluded host appears and that walls are last.

- [ ] **Step 5: Run it**

Run: `.venv/bin/claimstone acquire projects/alembic-s4`
Expected: one line per source. This takes minutes: the fetcher pauses 0.34s between requests and each timeout costs 30s.

- [ ] **Step 6: Read the number**

Run: `.venv/bin/claimstone report projects/alembic-s4`

Record the result in `docs/DESIGN_DECISIONS.md` under D8 as a dated line: the rate, the per-class breakdown, and the failure classes that account for the gap. **The number is the deliverable whatever it is.** A rate that did not move is a finding about the cascade, and recording it is the point; D11 exists because the alternative was a corpus certifying itself complete at 0.42.

- [ ] **Step 7: Commit the measurement**

```bash
git add docs/DESIGN_DECISIONS.md
git commit -m "D8: the acquisition rate on the 26-source manifest, measured

<trailer>"
```

---

## What this plan does not do

- No dashboard. That is `2026-09-22-dashboard-design.md` and gets its own plan, written after this one lands, because `round_state.py` reads ledgers whose shape this plan settles.
- No stage 3. GROBID, chunking and the citation discovery channel are out of scope; the only forward commitment is that stage 3 confirms extractable text and may write back a `fulltext_confirmed` signal.
- No institutional authentication (spec §14). A source reachable only that way stays `PAYWALL_403` and lowers the rate.
