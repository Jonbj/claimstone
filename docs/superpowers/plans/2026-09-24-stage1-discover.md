# Stage 1 — discover: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `discover` produce candidates `acquire` will accept — each carrying a source class assigned by rules the project declares — and turn the bibliography stage 3 extracts into a second, independent channel.

**Architecture:** `classify.py` maps a candidate to a class using rules from `sources.yaml`, so the engine applies rules it does not know. `searchers.py` holds the three API searchers, isolated because they are the part that ages. `discover.py` orchestrates both channels, stamps the round, and writes only its own ledger. `discover_report.py` reports three quantities and refuses to combine them into one.

**Tech Stack:** Python ≥ 3.11, stdlib plus `requests`. No new dependency. pytest.

**Spec:** `docs/superpowers/specs/2026-09-24-stage1-discover-design.md`. Read it before Task 1; every task cites the section it implements.

---

## Conventions for every task

- Run tests with `.venv/bin/pytest`, the CLI with `.venv/bin/claimstone`.
- **Every commit message ends with the trailer** `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`, shown in full in Task 1 and abbreviated as `<trailer>` afterwards.
- **No test reaches a real API.** The fetcher is injected and answered by `tests.fakes.FakeFetcher`, which already exists from stage 2. `tests/conftest.py` already supplies `CLAIMSTONE_CONTACT_EMAIL`.
- **Use DOIs with 4-9 digits in the registrant code** (`10.1234/abc`). `ids.normalize_doi` matches the real DOI shape, so a toy DOI is silently dropped.
- Commit after every task. A task that leaves the suite red is not finished.

## Starting state

`claimstone/discover.py` (244 lines) was committed in `630ca52` and has never been specified. It
holds `search_openalex`, `search_crossref`, `search_arxiv`, a `run` loop and `import_manifest`.
Two of those searchers need one extra field each; the rest of this plan moves them, adds what was
missing, and leaves `import_manifest` alone — it is the only part that already assigns a class.

**The defect this plan fixes:** `_row` writes no `source_class`, and `acquire.acquire_one` raises
`MissingSourceClass` without one. Every candidate the three searchers produce today is unusable.

## One field each API was not asked for

Measured against the live select clauses:

- **Crossref** does not request `type`, so `crossref_type` has nothing to match on. Task 2 adds it.
- **OpenAlex** selects `primary_location` whole, so `source.type` is already there — it just was
  never read out. Task 2 reads it.

## File structure

| File | Action | Responsibility |
|---|---|---|
| `claimstone/classify.py` | create | candidate + declared rules → class id. Pure, no I/O. |
| `claimstone/searchers.py` | create | the three API searchers, fetcher injected. |
| `claimstone/discover.py` | rewritten | both channels, the round, `candidates.jsonl`. Keeps `import_manifest`. |
| `claimstone/discover_report.py` | create | the three quantities, and nothing that combines them. |
| `claimstone/config.py` | modify | `assign_when` per class; `citation_channel` thresholds. |
| `claimstone/cli.py` | modify | `discover`, `discover-report`. |
| `projects/example-news-and-returns/sources.yaml` | modify | declare `assign_when` so the shipped example works. |
| `tests/test_classify.py` | create | each predicate, declaration order, an uncovered candidate |
| `tests/test_searchers.py` | create | the three APIs against saved fake payloads |
| `tests/test_discover.py` | create | both channels, the round, dedup, the near-match note |
| `tests/test_discover_report.py` | create | three quantities separately; no population estimate |
| `docs/contracts/candidates.md` | create | the row stage 2 reads |

---

### Task 1: Declared class rules

Implements spec §3.

**Files:**
- Modify: `claimstone/config.py`
- Create: `claimstone/classify.py`
- Create: `tests/test_classify.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_classify.py`:

```python
"""Assigning a source class from rules the project declares, never from what the engine guesses."""

import pytest

from claimstone import classify
from claimstone.config import ConfigError, SourceClass

CLASSES = (
    SourceClass(id="ACA", name="academic", weight_hint="highest",
                assign_when={"openalex_source_type": ("journal",),
                             "crossref_type": ("journal-article",)}),
    SourceClass(id="WP", name="working paper", weight_hint="high",
                assign_when={"source_api": ("arxiv",),
                             "openalex_source_type": ("repository",),
                             "host": ("papers.ssrn.com", "nber.org")}),
    SourceClass(id="NEW", name="journalism", weight_hint="low", assign_when={}),
)


def candidate(**overrides):
    base = {"source_api": "openalex", "venue_type": "journal",
            "url": "https://doi.org/10.1234/abc", "title": "A paper"}
    return {**base, **overrides}


def test_a_journal_in_openalex_is_academic():
    assert classify.classify(candidate(), CLASSES) == "ACA"


def test_a_journal_article_in_crossref_is_academic():
    assert classify.classify(
        candidate(source_api="crossref", venue_type="journal-article"), CLASSES) == "ACA"


def test_arxiv_is_a_working_paper_whatever_its_venue_says():
    assert classify.classify(
        candidate(source_api="arxiv", venue_type=""), CLASSES) == "WP"


def test_a_repository_in_openalex_is_a_working_paper():
    assert classify.classify(candidate(venue_type="repository"), CLASSES) == "WP"


def test_a_host_matches_on_its_suffix():
    assert classify.classify(
        candidate(venue_type="", url="https://papers.ssrn.com/abstract=123"), CLASSES) == "WP"
    assert classify.classify(
        candidate(venue_type="", url="https://www.nber.org/papers/w1234"), CLASSES) == "WP"


def test_a_similar_looking_host_does_not_match():
    # Suffix matching must not turn notnber.org into nber.org.
    assert classify.classify(
        candidate(venue_type="", url="https://notnber.org/x"), CLASSES) is None


def test_declaration_order_decides_when_two_classes_match():
    """sources.yaml declares classes most-authoritative-first, so the order is already the right one
    and no separate priority system is needed.

    The candidate has to match two classes for this to test anything. An arXiv row with
    `venue_type="journal"` does not: a venue type only counts alongside the API that reported it, and
    arXiv does not report OpenAlex vocabulary — so that candidate matches WP alone and demonstrates
    nothing about order. A real double match is a refereed paper whose open copy sits on SSRN:
    OpenAlex calls the work a journal article and the URL is a working-paper host.
    """
    both = candidate(venue_type="journal", url="https://papers.ssrn.com/abstract=99")
    assert classify.classify(both, CLASSES) == "ACA"
    # And it is the right answer: the work is refereed and we merely obtained the preprint copy,
    # which `oa_status` and `version` record. Reading the host first would demote every paper whose
    # only open copy is a preprint.


def test_a_class_with_no_rules_never_matches():
    # NEW declares no assign_when: it arrives from the manifest, not from a search.
    assert classify.classify(candidate(source_api="searxng", venue_type="", url=""),
                             CLASSES) is None


def test_an_uncovered_candidate_is_none_not_a_guess():
    assert classify.classify(
        candidate(venue_type="book-series"), CLASSES) is None


def test_the_uncovered_attributes_are_reported_so_a_rule_can_be_written():
    seen = classify.uncovered([candidate(venue_type="book-series"),
                               candidate(venue_type="conference"),
                               candidate(venue_type="conference")], CLASSES)
    assert seen == {"openalex_source_type": {"book-series": 1, "conference": 2}}


# --- config validation -------------------------------------------------------

def test_an_unknown_predicate_is_a_configuration_error(tmp_path):
    from claimstone.config import load_sources

    (tmp_path / "sources.yaml").write_text(
        "acquisition_floor: 0.8\nclasses:\n"
        "  - id: ACA\n    name: a\n    weight_hint: highest\n"
        "    assign_when:\n      publisher_mood: [cheerful]\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="publisher_mood"):
        load_sources(tmp_path)


def test_a_predicate_must_hold_a_list(tmp_path):
    from claimstone.config import load_sources

    (tmp_path / "sources.yaml").write_text(
        "acquisition_floor: 0.8\nclasses:\n"
        "  - id: ACA\n    name: a\n    weight_hint: highest\n"
        "    assign_when:\n      source_api: arxiv\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="source_api"):
        load_sources(tmp_path)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_classify.py -q`
Expected: FAIL with `TypeError: SourceClass.__init__() got an unexpected keyword argument 'assign_when'`

- [ ] **Step 3: Extend `SourceClass` and validate the rules in `claimstone/config.py`**

Add the field to `SourceClass`, after `aliases`:

```python
    # Conditions that assign a candidate to this class. Declared by the project, applied by the
    # engine: invariant 4 says the engine holds no domain knowledge, and "a journal is refereed"
    # is domain knowledge.
    assign_when: dict[str, tuple[str, ...]] = field(default_factory=dict)
```

`SourceClass` is a frozen dataclass, so add `from dataclasses import dataclass, field` if the
import is not already widened — Task 7 of the stage 2 plan already did this for `Project`.

Add the predicate names beside the other name tuples:

```python
ASSIGN_PREDICATES = ("source_api", "openalex_source_type", "crossref_type", "host")
```

And in `load_sources`, inside the per-entry loop, before constructing `SourceClass`:

```python
        rules_raw = entry.get("assign_when") or {}
        if not isinstance(rules_raw, dict):
            raise ConfigError("sources.yaml: 'assign_when' must be a mapping")
        unknown = sorted(set(rules_raw) - set(ASSIGN_PREDICATES))
        if unknown:
            raise ConfigError(
                f"sources.yaml: unknown assign_when predicate(s): {', '.join(unknown)} "
                f"(known: {', '.join(ASSIGN_PREDICATES)})"
            )
        rules: dict[str, tuple[str, ...]] = {}
        for name, values in rules_raw.items():
            if not isinstance(values, list) or not values:
                raise ConfigError(
                    f"sources.yaml: assign_when.{name} must be a non-empty list of values"
                )
            rules[str(name)] = tuple(str(v).strip() for v in values)
```

Then pass `assign_when=rules` to the `SourceClass(...)` construction.

- [ ] **Step 4: Write `claimstone/classify.py`**

```python
"""Which source class a candidate belongs to, according to rules the project declared.

Invariant 4: the engine holds no domain knowledge. "A journal article is refereed" is domain
knowledge, so it lives in `sources.yaml` and this module only applies what it finds there — the
same arrangement as the manifest's class aliases.

A candidate no rule covers gets no class. It is not guessed and not discarded: stage 2 will refuse
it, which is correct, and `uncovered()` says which attribute values went unmatched so the remedy is
to declare a rule rather than to loosen one.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from claimstone import net
from claimstone.config import SourceClass

# Which candidate field each predicate reads, and the source_api it is restricted to. A venue type
# only means something alongside the API that reported it: "journal" from OpenAlex and
# "journal-article" from Crossref are different vocabularies.
_VENUE_PREDICATES = {
    "openalex_source_type": "openalex",
    "crossref_type": "crossref",
}


def _host_matches(url: str, patterns: Sequence[str]) -> bool:
    host = net.host_of(url)
    if not host:
        return False
    # Suffix matching on a label boundary, so notnber.org is not nber.org.
    return any(host == p or host.endswith(f".{p}") for p in patterns)


def _predicate_matches(candidate: dict[str, Any], name: str, values: Sequence[str]) -> bool:
    if name == "source_api":
        return str(candidate.get("source_api") or "") in values
    if name == "host":
        return _host_matches(str(candidate.get("url") or ""), values)
    required_api = _VENUE_PREDICATES[name]
    if str(candidate.get("source_api") or "") != required_api:
        return False
    return str(candidate.get("venue_type") or "") in values


def classify(candidate: dict[str, Any], classes: Iterable[SourceClass]) -> str | None:
    """The first declared class whose rules match. Declaration order is the priority."""
    for klass in classes:
        if not klass.assign_when:
            continue
        if any(
            _predicate_matches(candidate, name, values)
            for name, values in klass.assign_when.items()
        ):
            return klass.id
    return None


def uncovered(
    candidates: Iterable[dict[str, Any]], classes: Sequence[SourceClass]
) -> dict[str, dict[str, int]]:
    """For candidates no rule covered, which attribute values were seen and how often.

    The point is that "7 unclassified" is not actionable and "7 unclassified, all
    openalex_source_type=conference" is: it names the rule that is missing.
    """
    seen: dict[str, dict[str, int]] = {}
    for candidate in candidates:
        if classify(candidate, classes) is not None:
            continue
        api = str(candidate.get("source_api") or "")
        for predicate, required_api in _VENUE_PREDICATES.items():
            if api == required_api:
                value = str(candidate.get("venue_type") or "")
                if value:
                    bucket = seen.setdefault(predicate, {})
                    bucket[value] = bucket.get(value, 0) + 1
    return seen
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_classify.py -q`
Expected: PASS, 12 passed

- [ ] **Step 6: Declare the rules in the shipped example**

In `projects/example-news-and-returns/sources.yaml`, add `assign_when` to the three classes a
search can produce, and leave the other three without — they arrive from the manifest:

```yaml
classes:
  - id: ACA
    name: peer-reviewed academic
    weight_hint: highest
    notes: version of record in a refereed venue
    # Applied by the engine, declared here: "a journal article is refereed" is domain
    # knowledge and invariant 4 keeps it out of the package.
    assign_when:
      openalex_source_type: [journal]
      crossref_type: [journal-article]
  - id: WP
    name: working paper / preprint
    weight_hint: high
    notes: NBER, SSRN, arXiv; not refereed — never silently promoted to ACA
    assign_when:
      source_api: [arxiv]
      openalex_source_type: [repository]
      host: [papers.ssrn.com, nber.org, ssrn.com]
  - id: MET
    name: methodological reference
    weight_hint: high
    notes: textbook, handbook chapter, methods guide; supports design not effect size
    assign_when:
      crossref_type: [book, book-chapter, monograph, reference-book]
```

- [ ] **Step 7: Run everything and commit**

Run: `.venv/bin/pytest -q` — expected: all pass
Run: `.venv/bin/claimstone validate --all-projects` — expected: OK for both

```bash
git add claimstone/classify.py claimstone/config.py tests/test_classify.py \
        projects/example-news-and-returns/sources.yaml
git commit -m "classify: a candidate's class comes from rules the project declares

discover assigned no source_class, and acquire raises without one — correctly,
since invariant 6 says the class travels with the item. So every candidate the API
searchers produced was unusable, and nobody had ever decided how to fix that.

The rules live in sources.yaml because "a journal article is refereed" is domain
knowledge and invariant 4 keeps it out of the package. The first declared class to
match wins, which needs no priority system: sources.yaml already declares classes
most-authoritative-first.

A candidate no rule covers gets no class, and uncovered() names the attribute values
that went unmatched — "7 unclassified" is not actionable, "7 unclassified, all
openalex_source_type=conference" names the missing rule. Host matching is on a label
boundary so notnber.org is not nber.org.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: The searchers, with the fields classify needs

Implements spec §7, and the two missing API fields.

**Files:**
- Create: `claimstone/searchers.py`
- Create: `tests/test_searchers.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_searchers.py`:

```python
"""The three API searchers, against saved payloads. No request leaves the process."""

from claimstone import searchers
from tests.fakes import FakeFetcher, ok

OPENALEX = "https://api.openalex.org/works?"
CROSSREF = "https://api.crossref.org/works?"
ARXIV = "https://export.arxiv.org/api/query?"

OPENALEX_PAYLOAD = {"results": [{
    "id": "https://openalex.org/W123",
    "doi": "https://doi.org/10.1234/abc",
    "title": "News versus Sentiment",
    "publication_year": 2019,
    "primary_location": {"pdf_url": "https://repo.example/a.pdf",
                         "landing_page_url": "https://x.example/a",
                         "source": {"display_name": "Journal of Finance", "type": "journal"}},
    "open_access": {"is_oa": True},
    "cited_by_count": 42,
}]}

CROSSREF_PAYLOAD = {"message": {"items": [{
    "DOI": "10.1234/def",
    "title": ["A reality check for data snooping"],
    "issued": {"date-parts": [[1999]]},
    "container-title": ["Econometrica"],
    "URL": "https://doi.org/10.1234/def",
    "type": "journal-article",
    "is-referenced-by-count": 900,
}]}}

ARXIV_ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.01234v1</id>
    <title>Can ChatGPT Forecast Stock Price Movements?</title>
    <published>2024-01-02T00:00:00Z</published>
  </entry>
</feed>"""


def test_openalex_reports_the_venue_type_classify_needs():
    fetcher = FakeFetcher(json_pages={OPENALEX: OPENALEX_PAYLOAD})
    row = next(iter(searchers.search_openalex(fetcher, "news sentiment", "T02")))
    assert row["venue_type"] == "journal"
    assert row["source_api"] == "openalex"
    assert row["doi"] == "10.1234/abc"
    assert row["venue"] == "Journal of Finance"
    assert row["url"] == "https://repo.example/a.pdf"
    assert row["topic_id"] == "T02"
    assert row["channel"] == "keyword"


def test_crossref_asks_for_type_and_reports_it():
    # The live select clause omitted `type`, so crossref_type had nothing to match on.
    fetcher = FakeFetcher(json_pages={CROSSREF: CROSSREF_PAYLOAD})
    row = next(iter(searchers.search_crossref(fetcher, "data snooping", "T01")))
    assert row["venue_type"] == "journal-article"
    assert "type" in fetcher.calls[-1]
    assert row["year"] == 1999


def test_arxiv_parses_atom_and_is_always_a_preprint_venue():
    url = ARXIV + "search_query=all%3A%22chatgpt%22&max_results=25"
    fetcher = FakeFetcher(pages={url: ok(url, ARXIV_ATOM, "application/atom+xml")})
    rows = list(searchers.search_arxiv(fetcher, "chatgpt", "T02", max_results=25))
    assert rows[0]["url"] == "https://arxiv.org/pdf/2401.01234"
    assert rows[0]["venue"] == "arXiv"
    assert rows[0]["venue_type"] == "preprint"
    assert rows[0]["is_oa"] is True


def test_an_empty_payload_yields_nothing():
    fetcher = FakeFetcher(json_pages={OPENALEX: {}})
    assert list(searchers.search_openalex(fetcher, "x", "T01")) == []


def test_a_failed_request_yields_nothing_rather_than_raising():
    assert list(searchers.search_openalex(FakeFetcher(), "x", "T01")) == []
    assert list(searchers.search_crossref(FakeFetcher(), "x", "T01")) == []
    assert list(searchers.search_arxiv(FakeFetcher(), "x", "T01")) == []


def test_malformed_atom_yields_nothing():
    url = ARXIV + "search_query=all%3A%22x%22&max_results=25"
    fetcher = FakeFetcher(pages={url: ok(url, b"<feed><entry", "application/atom+xml")})
    assert list(searchers.search_arxiv(fetcher, "x", max_results=25, topic_id="T01")) == []


def test_a_row_records_the_query_that_found_it():
    fetcher = FakeFetcher(json_pages={OPENALEX: OPENALEX_PAYLOAD})
    row = next(iter(searchers.search_openalex(fetcher, "news sentiment", "T02")))
    assert row["query"] == "news sentiment"
    assert row["query_hash"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_searchers.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.searchers'`

- [ ] **Step 3: Create `claimstone/searchers.py`**

Move `_row`, `_now`, `CHANNEL_KEYWORD`, `CHANNEL_CITATION`, the three `search_*` functions, the
`SEARCHERS` mapping and `_limit_kw` out of `claimstone/discover.py` into this new module. Then make
three changes:

Add `venue_type` to `_row`'s signature and output:

```python
def _row(
    *,
    title: str,
    url: str,
    doi: str | None,
    year: int | None,
    venue: str,
    venue_type: str,
    source_api: str,
    query: str,
    topic_id: str,
    channel: str,
    is_oa: bool | None = None,
    citations: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doi = ids.normalize_doi(doi)
    return {
        "candidate_key": ids.candidate_key(doi=doi, title=title, url=url),
        "title": title,
        "url": url,
        "doi": doi,
        "year": year,
        "venue": venue,
        # What the API called this venue. Only meaningful alongside source_api: "journal" from
        # OpenAlex and "journal-article" from Crossref are different vocabularies.
        "venue_type": venue_type,
        "source_api": source_api,
        "query": query,
        "query_hash": sha256_text(f"{source_api}|{query}")[:16],
        "topic_id": topic_id,
        "channel": channel,
        "is_oa": is_oa,
        "citations": citations,
        "found_at": _now(),
        **(extra or {}),
    }
```

In `search_openalex`, read the type that was already being fetched and pass it through:

```python
        source = (location.get("source") or {}) if isinstance(location, dict) else {}
        landing = location.get("pdf_url") or location.get("landing_page_url") or work.get("id")
        yield _row(
            title=str(work.get("title") or "").strip(),
            url=str(landing or ""),
            doi=work.get("doi"),
            year=work.get("publication_year"),
            venue=str(source.get("display_name") or ""),
            # primary_location was already selected whole; this field was simply never read.
            venue_type=str(source.get("type") or ""),
            source_api="openalex",
            query=term,
            topic_id=topic_id,
            channel=CHANNEL_KEYWORD,
            is_oa=(work.get("open_access") or {}).get("is_oa"),
            citations=work.get("cited_by_count"),
        )
```

In `search_crossref`, ask for `type` and pass it through:

```python
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
        {"query.bibliographic": term, "rows": rows, "mailto": net.contact_email(),
         "select": "DOI,title,issued,container-title,URL,type,is-referenced-by-count"}
    )
```

```python
            venue=str(containers[0] if containers else ""),
            venue_type=str(item.get("type") or ""),
```

In `search_arxiv`, everything on arXiv is a preprint, and saying so lets a project write one rule
instead of two:

```python
            venue="arXiv",
            venue_type="preprint",
```

Finally change every `fetcher: net.Fetcher` annotation in this module to `fetcher: net.FetcherLike`,
so the searchers accept the fake as well as the real thing.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_searchers.py -q`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add claimstone/searchers.py claimstone/discover.py tests/test_searchers.py
git commit -m "searchers: their own module, and the one field each API was not asked for

The searchers are the part that ages — an API changes shape and nothing else does —
so they move out where a saved payload can exercise them without a store or a
ledger.

Two fields were missing for classification. Crossref's select clause omitted type,
so crossref_type had nothing to match against. OpenAlex selected primary_location
whole, so source.type was already arriving and was simply never read out. And arXiv
reports venue_type as preprint, which lets a project write one rule where it would
otherwise need two.

<trailer>"
```

---

### Task 3: The keyword channel, classified and stamped with a round

Implements spec §4's keyword half.

**Files:**
- Rewrite: `claimstone/discover.py`
- Create: `tests/test_discover.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_discover.py`:

```python
"""Both channels, the round, and what happens to a candidate no rule covers."""

from claimstone import discover
from claimstone.config import load_project
from claimstone.store import Store
from tests.fakes import FakeFetcher
from tests.test_searchers import CROSSREF, CROSSREF_PAYLOAD, OPENALEX, OPENALEX_PAYLOAD

PROJECT = "projects/example-news-and-returns"


def _fetcher():
    return FakeFetcher(json_pages={OPENALEX: OPENALEX_PAYLOAD, CROSSREF: CROSSREF_PAYLOAD})


def test_a_discovered_candidate_carries_a_source_class(tmp_path):
    # The whole point: without this, acquire raises MissingSourceClass on every row.
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    discover.run(project, store, _fetcher(), apis=("openalex",), topics=("T02",))
    rows = list(store.read("candidates.jsonl"))
    assert rows
    assert all(row["source_class"] == "ACA" for row in rows)


def test_the_round_is_written_on_every_candidate(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    discover.run(project, store, _fetcher(), apis=("openalex",), topics=("T02",),
                 round_name="autumn-sweep")
    assert all(row["round"] == "autumn-sweep" for row in store.read("candidates.jsonl"))


def test_the_round_defaults_to_routine(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    discover.run(project, store, _fetcher(), apis=("openalex",), topics=("T02",))
    assert all(row["round"] == "routine" for row in store.read("candidates.jsonl"))


def test_an_unclassified_candidate_is_written_and_counted(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    payload = {"results": [{**OPENALEX_PAYLOAD["results"][0],
                            "primary_location": {"landing_page_url": "https://x.example/a",
                                                 "source": {"display_name": "A conf",
                                                            "type": "conference"}}}]}
    fetcher = FakeFetcher(json_pages={OPENALEX: payload})
    result = discover.run(project, store, fetcher, apis=("openalex",), topics=("T02",))
    assert result["unclassified"] == 1
    rows = list(store.read("candidates.jsonl"))
    assert rows[0]["source_class"] is None
    # Not discarded: it is visible, and the remedy is to declare a rule.
    assert result["uncovered"] == {"openalex_source_type": {"conference": 1}}


def test_the_same_candidate_is_not_written_twice(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    discover.run(project, store, _fetcher(), apis=("openalex",), topics=("T02",))
    second = discover.run(project, store, _fetcher(), apis=("openalex",), topics=("T02",))
    assert second["new"] == 0
    assert len(list(store.read("candidates.jsonl"))) == 1


def test_only_the_requested_topics_are_searched(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    fetcher = _fetcher()
    discover.run(project, store, fetcher, apis=("openalex",), topics=("T02",))
    topic = next(t for t in project.topics if t.id == "T02")
    assert len(fetcher.calls) == len(topic.terms)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_discover.py -q`
Expected: FAIL with `TypeError: run() got an unexpected keyword argument 'round_name'`

- [ ] **Step 3: Rewrite the keyword half of `claimstone/discover.py`**

Replace the module's head and its `run`, keeping `import_manifest` at the bottom unchanged except
for the one field the new `_row` requires:

```python
"""Stage 1 — discover: topics become candidates, through two independent channels.

Deterministic HTTP against scholarly metadata APIs; no model is involved, because a model adds
nothing to a keyword query and would make the round irreproducible.

Every candidate carries a **source class**, assigned by rules the project declared (see
`classify`). Without one, stage 2 refuses it — that is invariant 6 working, and it is why this
stage existed for a while producing rows nothing downstream could use.

Completeness is later estimated by comparing two *independent* channels: keyword search here, and
citations extracted from acquired texts in stage 3. This module reads that bibliography and writes
candidates; it never writes another stage's ledger.
"""

from __future__ import annotations

from typing import Any, Iterable

from claimstone import classify, net
from claimstone.config import Project
from claimstone.searchers import CHANNEL_CITATION, CHANNEL_KEYWORD, SEARCHERS, _limit_kw, _row
from claimstone.store import Store

ROUTINE = "routine"


def run(
    project: Project,
    store: Store,
    fetcher: net.FetcherLike,
    *,
    apis: Iterable[str] = ("openalex", "crossref", "arxiv"),
    topics: Iterable[str] | None = None,
    per_query: int = 25,
    round_name: str = ROUTINE,
) -> dict[str, Any]:
    """Search every term of every selected topic; append only candidates not already seen."""
    wanted = set(topics) if topics else None
    known = set(store.latest_by("candidates.jsonl", "candidate_key"))
    new = 0
    seen_this_run = 0
    unclassified: list[dict[str, Any]] = []
    queries = 0

    for topic in project.topics:
        if wanted and topic.id not in wanted:
            continue
        for term in topic.terms:
            for api in apis:
                queries += 1
                searcher = SEARCHERS[api]
                for row in searcher(fetcher, term, topic.id, **{_limit_kw(api): per_query}):
                    if not row["title"] and not row["url"]:
                        continue
                    seen_this_run += 1
                    if row["candidate_key"] in known:
                        continue
                    row["source_class"] = classify.classify(row, project.classes)
                    row["round"] = round_name
                    if row["source_class"] is None:
                        unclassified.append(row)
                    known.add(row["candidate_key"])
                    store.append("candidates.jsonl", row)
                    new += 1

    return {
        "returned": seen_this_run,
        "new": new,
        "total": len(known),
        "queries": queries,
        "unclassified": len(unclassified),
        # Which attribute values went unmatched, so the remedy is a declared rule.
        "uncovered": classify.uncovered(unclassified, project.classes),
        "round": round_name,
    }
```

In `import_manifest`, pass the field the new `_row` requires — a manifest states a format, not a
venue type, so it is empty and the class comes from the manifest's own column:

```python
            venue="",
            venue_type="",
```

and set the round on each manifest row too, so every candidate in the ledger has one:

```python
def import_manifest(
    store: Store, entries: Iterable[Any], *, round_name: str = ROUTINE
) -> dict[str, Any]:
```

with `row["round"] = round_name` before the dedup check.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_discover.py tests/test_import_manifest.py -q`
Expected: PASS. `tests/test_import_manifest.py` needs `"updated": 0` results unchanged and one new
key; if it asserts an exact dict, widen that assertion to check the three counts it cares about.

- [ ] **Step 5: Commit**

```bash
git add claimstone/discover.py tests/test_discover.py tests/test_import_manifest.py
git commit -m "discover: every candidate now carries a class and a round

The keyword channel classifies each row as it writes it, so stage 2 stops refusing
everything this stage produces. A candidate no rule covers is written with a null
class and counted, and the run reports which attribute values went unmatched — the
remedy is to declare a rule, not to loosen one.

The round lands on every row, manifest imports included, because "how many are new
this round" is a round-over-round figure and reconstructing it from timestamps is
what append-only storage exists to make unnecessary.

<trailer>"
```

---

### Task 4: The citation channel

Implements spec §4's citation half.

**Files:**
- Modify: `claimstone/config.py`
- Modify: `claimstone/discover.py`
- Modify: `tests/test_discover.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_discover.py`:

```python
import pytest


def reference(key, *, title, cited=2, year=2010, doi=None):
    return {"key": key, "title": title, "year": year, "authors": ["Someone"], "doi": doi,
            "cited_by": [f"S{n:02d}" for n in range(cited)], "citations_in_corpus": cited}


def test_a_reference_cited_twice_becomes_a_candidate(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", reference(
        "title:is all that talk just noise", title="Is all that talk just noise?", cited=3))
    result = discover.run_citations(project, store)
    assert result["new"] == 1
    row = next(iter(store.read("candidates.jsonl")))
    assert row["channel"] == "citation"
    assert row["source_api"] == "citation"
    assert row["citations_in_corpus"] == 3
    assert row["cited_by"] == ["S00", "S01", "S02"]


def test_a_reference_cited_once_is_not_admitted(tmp_path):
    # 657 of the 711 measured references are cited once. Admitting them all would mean 711
    # acquisition attempts, mostly against textbooks with no open copy.
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", reference("title:a", title="A lone citation", cited=1))
    assert discover.run_citations(project, store)["new"] == 0


def test_a_reference_too_old_is_not_admitted(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", reference("title:b", title="Risk, return, and equilibrium",
                                              cited=3, year=1973))
    assert discover.run_citations(project, store)["new"] == 0


def test_a_title_fragment_is_not_admitted(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", reference("title:see example", title="See Example", cited=3))
    assert discover.run_citations(project, store)["new"] == 0


def test_the_citation_channel_opens_no_socket(tmp_path, monkeypatch):
    import socket

    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", reference("title:x", title="A long enough title here",
                                               cited=2))

    def refuse(*args, **kwargs):
        raise AssertionError("the citation channel reads a ledger, not the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    discover.run_citations(project, store)


def test_no_references_file_is_reported_as_nothing_to_read(tmp_path):
    # Not "zero citation candidates", which would read as the bibliography having found nothing.
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    result = discover.run_citations(project, store)
    assert result["references_available"] is False
    assert result["new"] == 0


def test_a_citation_candidate_gets_a_class_from_its_host_or_none(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", reference(
        "title:a working paper title", title="A working paper title long enough", cited=2,
        doi="10.1234/xyz"))
    discover.run_citations(project, store)
    row = next(iter(store.read("candidates.jsonl")))
    # No venue type and a doi.org URL: no rule covers it, so it is null and counted.
    assert row["source_class"] is None


def test_the_threshold_is_configurable(tmp_path):
    from claimstone.config import load_citation_channel

    (tmp_path / "sources.yaml").write_text(
        "acquisition_floor: 0.8\nclasses:\n  - id: ACA\n    name: a\n    weight_hint: highest\n"
        "citation_channel:\n  min_citations_in_corpus: 1\n  min_year: 2000\n"
        "  require_title_chars: 10\n", encoding="utf-8")
    assert load_citation_channel(tmp_path) == {
        "min_citations_in_corpus": 1, "min_year": 2000, "require_title_chars": 10}


def test_an_unknown_citation_setting_is_an_error(tmp_path):
    from claimstone.config import ConfigError, load_citation_channel

    (tmp_path / "sources.yaml").write_text(
        "acquisition_floor: 0.8\nclasses: []\ncitation_channel:\n  min_fame: 3\n",
        encoding="utf-8")
    with pytest.raises(ConfigError, match="min_fame"):
        load_citation_channel(tmp_path)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_discover.py -q -k citation`
Expected: FAIL with `AttributeError: module 'claimstone.discover' has no attribute 'run_citations'`

- [ ] **Step 3: Add the thresholds to `claimstone/config.py`**

```python
CITATION_CHANNEL_NAMES = ("min_citations_in_corpus", "min_year", "require_title_chars")

CITATION_CHANNEL_DEFAULTS = {
    # 54 of the 711 references measured on the first corpus, against 711 if this were 1.
    "min_citations_in_corpus": 2,
    "min_year": 1990,
    # Discards parsing fragments: GROBID produced references whose whole title was "See Example".
    "require_title_chars": 25,
}


def load_citation_channel(root: pathlib.Path) -> dict[str, int]:
    """The rule admitting a reference as a candidate. Absent means the defaults."""
    raw = _read_yaml(pathlib.Path(root) / "sources.yaml").get("citation_channel") or {}
    if not isinstance(raw, dict):
        raise ConfigError("sources.yaml: 'citation_channel' must be a mapping")
    unknown = sorted(set(raw) - set(CITATION_CHANNEL_NAMES))
    if unknown:
        raise ConfigError(
            f"sources.yaml: unknown citation_channel setting(s): {', '.join(unknown)} "
            f"(known: {', '.join(CITATION_CHANNEL_NAMES)})"
        )
    for name, value in raw.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ConfigError(
                f"sources.yaml: citation_channel.{name} must be a non-negative integer"
            )
    return {**CITATION_CHANNEL_DEFAULTS, **{str(k): int(v) for k, v in raw.items()}}
```

Add `citation_channel: dict[str, int] = field(default_factory=dict)` to `Project` and set it in
`load_project` with `citation_channel=load_citation_channel(path)`.

- [ ] **Step 4: Add `run_citations` to `claimstone/discover.py`**

```python
def run_citations(
    project: Project, store: Store, *, round_name: str = ROUTINE
) -> dict[str, Any]:
    """Admit references extracted in stage 3 as candidates, by the project's declared rule.

    Opens no socket: this reads a ledger. So it is re-runnable at no cost when the threshold
    changes — the same arrangement as `gate-audit` and `normalize --confirm-audit`.

    The rule filters on `citations_in_corpus`, which is a property of this channel and not of the
    keyword channel's terms, so the two channels stay independent — the condition D10 needs. What
    it does introduce is a bias toward canonical works, recorded in the spec as a limit of any
    completeness estimate rather than hidden.
    """
    references = store.latest_by("references.jsonl", "key")
    if not references:
        # Distinct from "zero admitted": nothing was there to read, and reporting 0 candidates
        # would read as the bibliography having found nothing.
        return {"references_available": False, "considered": 0, "admitted": 0, "new": 0,
                "unclassified": 0, "uncovered": {}, "round": round_name}

    # config.load_citation_channel already merged the engine defaults, so this is complete.
    rule = dict(project.citation_channel)
    known = set(store.latest_by("candidates.jsonl", "candidate_key"))
    admitted = new = 0
    unclassified: list[dict[str, Any]] = []

    for reference in references.values():
        title = str(reference.get("title") or "")
        year = reference.get("year")
        if int(reference.get("citations_in_corpus") or 0) < rule["min_citations_in_corpus"]:
            continue
        if len(title) < rule["require_title_chars"]:
            continue
        if year is not None and int(year) < rule["min_year"]:
            continue
        admitted += 1

        doi = reference.get("doi")
        row = _row(
            title=title,
            url=f"https://doi.org/{doi}" if doi else "",
            doi=doi,
            year=int(year) if year else None,
            venue="",
            venue_type="",
            source_api="citation",
            query="references.jsonl",
            topic_id="",
            channel=CHANNEL_CITATION,
            citations=int(reference.get("citations_in_corpus") or 0),
            extra={
                "cited_by": list(reference.get("cited_by") or []),
                "citations_in_corpus": int(reference.get("citations_in_corpus") or 0),
            },
        )
        if row["candidate_key"] in known:
            continue
        row["source_class"] = classify.classify(row, project.classes)
        row["round"] = round_name
        if row["source_class"] is None:
            unclassified.append(row)
        known.add(row["candidate_key"])
        store.append("candidates.jsonl", row)
        new += 1

    return {
        "references_available": True,
        "considered": len(references),
        "admitted": admitted,
        "new": new,
        "unclassified": len(unclassified),
        "uncovered": classify.uncovered(unclassified, project.classes),
        "round": round_name,
    }
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/pytest -q`
Expected: PASS, all tests

- [ ] **Step 6: Commit**

```bash
git add claimstone/discover.py claimstone/config.py tests/test_discover.py
git commit -m "discover: the citation channel, which was declared in code and never used

Reads stage 3's references.jsonl and admits by the project's declared rule. Default
two citations in corpus, which on the measured data admits 54 of 711 rather than
711 — and 657 of those are cited once, mostly textbooks with no open copy, so
admitting them all would sink the acquisition rate for a reason that says nothing
about the cascade.

Filtering on citations_in_corpus is a property of this channel rather than a reuse
of the keyword channel's terms, so the two stay independent, which is the condition
D10 needs. The bias it introduces toward canonical works is recorded in the spec as
a limit on any completeness estimate.

No socket: the channel reads a ledger, so it re-runs for free when the threshold
changes. An absent references.jsonl reports that nothing was there to read, which
is a different fact from zero candidates admitted.

<trailer>"
```

---

### Task 5: Near-matches are noted, never merged

Implements spec §5.

**Files:**
- Modify: `claimstone/discover.py`
- Modify: `tests/test_discover.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_discover.py`:

```python
def test_a_banner_title_is_noted_as_a_possible_duplicate(tmp_path):
    # Measured: GROBID took an NBER cover banner as a title, so one work has two keys. 15 such
    # cases in the first corpus.
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {
        "candidate_key": "title:which news moves stock prices a textual analysis",
        "title": "Which News Moves Stock Prices? A Textual Analysis", "source_class": "ACA"})
    store.append("references.jsonl", reference(
        "title:nber working paper series which news moves stock prices a textual analysis",
        title="NBER WORKING PAPER SERIES WHICH NEWS MOVES STOCK PRICES A TEXTUAL ANALYSIS",
        cited=2))
    discover.run_citations(project, store)
    added = [r for r in store.read("candidates.jsonl") if r.get("channel") == "citation"]
    assert added[0]["possible_duplicate_of"] == \
        "title:which news moves stock prices a textual analysis"


def test_a_noted_duplicate_is_still_written_as_its_own_candidate(tmp_path):
    # A duplicate costs one wasted fetch, and not even a second download since bytes are
    # content-addressed. A wrong merge loses a source and misattributes its claims.
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {
        "candidate_key": "title:which news moves stock prices a textual analysis",
        "title": "Which News Moves Stock Prices? A Textual Analysis"})
    store.append("references.jsonl", reference(
        "title:nber working paper series which news moves stock prices a textual analysis",
        title="NBER WORKING PAPER SERIES WHICH NEWS MOVES STOCK PRICES A TEXTUAL ANALYSIS",
        cited=2))
    result = discover.run_citations(project, store)
    assert result["new"] == 1
    assert result["possible_duplicates"] == 1


def test_a_short_shared_prefix_is_not_a_near_match(tmp_path):
    # The check needs 25 characters of the shorter title, or every paper about returns would
    # look like every other one.
    assert discover.near_match("title:on returns", {"title:on returns and news and more"}) is None


def test_containment_is_the_declared_rule_and_its_false_positive_is_known():
    # Measured: "And the Cross-Section of Expected Returns" (Harvey, Liu, Zhu) is contained in
    # "Media coverage and the cross-section of expected returns" (Fang, Peress) and they are
    # different papers. The rule keeps it because the outcome is a note, never a merge.
    held = {"title:media coverage and the cross section of expected returns"}
    assert discover.near_match("title:and the cross section of expected returns", held) == \
        "title:media coverage and the cross section of expected returns"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_discover.py -q -k "duplicate or near_match"`
Expected: FAIL with `AttributeError: module 'claimstone.discover' has no attribute 'near_match'`

- [ ] **Step 3: Add `near_match` to `claimstone/discover.py`**

```python
NEAR_MATCH_MIN_CHARS = 25


def near_match(key: str, known: Iterable[str]) -> str | None:
    """A key whose title looks like an existing one. Recorded, never acted on.

    "Approximate" is defined rather than left to judgement: one folded title contains the other
    and the shorter of the two is at least 25 characters. That is the check that found both the 15
    banner cases in the measured corpus and its one false positive — "And the Cross-Section of
    Expected Returns" inside "Media coverage and the cross-section of expected returns", which are
    different papers.

    The rule survives that false positive because of an asymmetry. A duplicate costs one wasted
    acquisition attempt, and not even a second download, since bytes are content-addressed. A
    wrong merge loses a source permanently and attributes its claims to another work. So the
    outcome here is a note on a row and nothing else.
    """
    if not key.startswith("title:"):
        return None
    mine = key[len("title:"):]
    if len(mine) < NEAR_MATCH_MIN_CHARS:
        return None
    for other in known:
        if other == key or not other.startswith("title:"):
            continue
        theirs = other[len("title:"):]
        shorter = mine if len(mine) <= len(theirs) else theirs
        if len(shorter) < NEAR_MATCH_MIN_CHARS:
            continue
        if mine in theirs or theirs in mine:
            return other
    return None
```

Then in `run_citations`, after `row["round"] = round_name` and before the append:

```python
        note = near_match(row["candidate_key"], known)
        if note:
            row["possible_duplicate_of"] = note
            possible_duplicates += 1
```

with `possible_duplicates = 0` initialised beside `admitted`, and
`"possible_duplicates": possible_duplicates` added to the returned dict.

Then the same in `run`'s keyword loop, after `row["round"] = round_name`:

```python
                    note = near_match(row["candidate_key"], known)
                    if note:
                        row["possible_duplicate_of"] = note
                        possible_duplicates += 1
```

with `possible_duplicates = 0` initialised beside `new = 0`, and
`"possible_duplicates": possible_duplicates` added to that function's returned dict too.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest -q`
Expected: PASS, all tests

- [ ] **Step 5: Commit**

```bash
git add claimstone/discover.py tests/test_discover.py
git commit -m "discover: note a near-match, never merge on one

Measured, title matching fails in both directions. GROBID took an NBER cover banner
as a title, so one work has two keys — 15 such cases. And "And the Cross-Section of
Expected Returns" is contained in "Media coverage and the cross-section of expected
returns" while being a different paper, so the containment rule that would fix the
first produces the second.

So the rule is kept and its outcome is weakened to a note. The asymmetry decides it:
a duplicate costs one wasted fetch and not even a second download, since bytes are
content-addressed, while a wrong merge loses a source permanently and attributes its
claims to another work. One is noise; the other corrupts the evidence.

<trailer>"
```

---

### Task 6: The report that refuses to combine its numbers

Implements spec §6.

**Files:**
- Create: `claimstone/discover_report.py`
- Create: `tests/test_discover_report.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_discover_report.py`:

```python
"""Three quantities, reported separately, and a fourth that must not exist."""

from claimstone import discover_report
from claimstone.store import Store


def candidate(key, *, channel, klass="ACA", round_name="routine", topic="T01"):
    return {"candidate_key": key, "channel": channel, "source_class": klass,
            "round": round_name, "topic_id": topic, "source_api": "openalex",
            "query_hash": "abcd1234", "title": key}


def _store(tmp_path, rows, references=0):
    store = Store("t", base=tmp_path)
    for row in rows:
        store.append("candidates.jsonl", row)
    for n in range(references):
        store.append("references.jsonl", {"key": f"title:ref {n}", "citations_in_corpus": 1})
    return store


def test_the_two_channels_are_counted_separately(tmp_path):
    store = _store(tmp_path, [candidate("a", channel="keyword"),
                              candidate("b", channel="keyword"),
                              candidate("c", channel="citation")], references=711)
    summary = discover_report.summarise(store)
    assert summary["keyword"]["candidates"] == 2
    assert summary["citation"]["candidates"] == 1
    assert summary["citation"]["references_seen"] == 711


def test_the_overlap_is_the_third_quantity(tmp_path):
    store = _store(tmp_path, [candidate("title:shared work here and now", channel="keyword"),
                              candidate("title:only from search at all", channel="keyword")])
    store.append("references.jsonl", {"key": "title:shared work here and now",
                                      "citations_in_corpus": 3})
    summary = discover_report.summarise(store)
    assert summary["overlap"] == 1


def test_unclassified_candidates_are_reported_with_their_attributes(tmp_path):
    rows = [{**candidate("a", channel="keyword", klass=None), "venue_type": "conference"},
            {**candidate("b", channel="keyword", klass=None), "venue_type": "conference"},
            {**candidate("c", channel="keyword", klass=None), "venue_type": "book-series"}]
    summary = discover_report.summarise(_store(tmp_path, rows))
    assert summary["unclassified"] == 3
    # "3 unclassified" is not actionable; naming the values is what points at the missing rule.
    assert summary["uncovered"] == {"conference": 2, "book-series": 1}


def test_a_round_can_be_isolated(tmp_path):
    store = _store(tmp_path, [candidate("a", channel="keyword", round_name="spring"),
                              candidate("b", channel="keyword", round_name="autumn")])
    assert discover_report.summarise(store, round_name="autumn")["keyword"]["candidates"] == 1


def test_there_is_no_population_estimate_anywhere_in_the_module():
    # Lincoln-Petersen is computable from these three numbers and all three of its assumptions
    # are violated here — one of them by our own citation threshold. This test exists so that
    # adding it means arguing with spec section 6 rather than quietly shipping it.
    import inspect

    source = inspect.getsource(discover_report)
    for forbidden in ("lincoln", "petersen", "population", "completeness", "coverage_pct"):
        assert forbidden not in source.lower(), f"{forbidden!r} appears in discover_report"


def test_the_summary_says_what_it_refuses_to_say(tmp_path):
    store = _store(tmp_path, [candidate("a", channel="keyword")], references=711)
    summary = discover_report.summarise(store)
    assert "estimate" in summary["caveat"].lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_discover_report.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.discover_report'`

- [ ] **Step 3: Write `claimstone/discover_report.py`**

```python
"""What the two channels found, as three separate numbers.

The three are: how many candidates the keyword channel produced, how many the citation channel
produced, and how many works both found. They are **not** combined into one figure here, and that
is a requirement of the spec rather than an omission.

A capture-recapture estimate is computable from exactly these three numbers — on the first
measured corpus it gives about 2,962 works and a corpus covering 0.8% — and all three of its
assumptions are violated. The overlap is understated by an unknown amount, because title matching
misses a work whose title GROBID took from a cover banner. The keyword channel here was a
hand-curated manifest, not a random sample. And catchability is unequal by construction, since a
canonical paper is cited by everyone and an obscure one by nobody — which the citation channel's
own threshold relies on, so our filter violates the assumption the estimate needs.

What may be concluded from the three numbers is `synthesize`'s problem. What is solid, and belongs
in any reading of them, is the raw comparison: on the first corpus 705 of 711 references were not
in the manifest, so the second channel finds hundreds of things the first missed, and no estimate
is needed to know that.
"""

from __future__ import annotations

from typing import Any

from claimstone.store import Store

CAVEAT = (
    "Three quantities, deliberately not combined: an estimate from them would rest on "
    "assumptions this corpus violates. See the stage 1 spec, section 6."
)


def summarise(store: Store, *, round_name: str | None = None) -> dict[str, Any]:
    """Per channel: candidates, topics, queries, classes. Plus the overlap between them."""
    candidates = [
        row
        for row in store.latest_by("candidates.jsonl", "candidate_key").values()
        if round_name is None or row.get("round") == round_name
    ]
    references = store.latest_by("references.jsonl", "key")

    channels: dict[str, dict[str, Any]] = {}
    unclassified = 0
    uncovered: dict[str, int] = {}
    for row in candidates:
        name = str(row.get("channel") or "unknown")
        bucket = channels.setdefault(name, {
            "candidates": 0, "topics": set(), "queries": set(), "by_class": {},
        })
        bucket["candidates"] += 1
        if row.get("topic_id"):
            bucket["topics"].add(row["topic_id"])
        if row.get("query_hash"):
            bucket["queries"].add(row["query_hash"])
        klass = row.get("source_class")
        if klass is None:
            unclassified += 1
            value = str(row.get("venue_type") or "")
            if value:
                uncovered[value] = uncovered.get(value, 0) + 1
        else:
            bucket["by_class"][klass] = bucket["by_class"].get(klass, 0) + 1

    for name in ("keyword", "citation"):
        channels.setdefault(name, {"candidates": 0, "topics": set(), "queries": set(),
                                   "by_class": {}})
    for bucket in channels.values():
        bucket["topics"] = len(bucket["topics"])
        bucket["queries"] = len(bucket["queries"])
        bucket["by_class"] = dict(sorted(bucket["by_class"].items()))
    channels["citation"]["references_seen"] = len(references)

    keyword_keys = {
        str(row["candidate_key"]) for row in candidates if row.get("channel") == "keyword"
    }
    overlap = len(keyword_keys & set(references))

    return {
        "round": round_name,
        "candidates": len(candidates),
        "keyword": channels["keyword"],
        "citation": channels["citation"],
        "overlap": overlap,
        "unclassified": unclassified,
        "uncovered": dict(sorted(uncovered.items(), key=lambda kv: -kv[1])),
        "caveat": CAVEAT,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_discover_report.py -q`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add claimstone/discover_report.py tests/test_discover_report.py
git commit -m "discover-report: three numbers, and a test that forbids the fourth

Channel one size, channel two size, overlap — reported separately. A
capture-recapture estimate is computable from exactly those three and all three of
its assumptions fail here: the overlap is understated by an unknown amount because
a cover banner became a title, the keyword channel was hand-curated rather than
sampled, and catchability is unequal by construction — which the citation
threshold relies on, so our own filter breaks the assumption the estimate needs.

A test asserts the module mentions none of it. Adding the figure later means
arguing with the spec rather than quietly shipping fabricated precision about
corpus completeness, which is the specific claim this project exists to refuse.

<trailer>"
```

---

### Task 7: Wiring the CLI

Implements spec §8.

**Files:**
- Modify: `claimstone/cli.py`
- Create: `tests/test_cli_discover.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_discover.py`:

```python
"""discover and discover-report at the command line."""

from claimstone.cli import build_parser, main


def test_discover_is_a_real_command():
    args = build_parser().parse_args(["discover", "projects/example-news-and-returns"])
    assert args.func.__name__ == "_discover"
    assert args.channel == "both"
    assert args.round == "routine"


def test_the_citation_channel_alone_needs_no_contact_address(tmp_path, capsys, monkeypatch):
    # It reads a ledger. Requiring a crawler identity for that would be theatre.
    monkeypatch.delenv("CLAIMSTONE_CONTACT_EMAIL", raising=False)
    code = main(["discover", "projects/example-news-and-returns", "--channel", "citation",
                 "--store", str(tmp_path)])
    assert code == 0
    assert "nothing to read" in capsys.readouterr().out


def test_an_unknown_api_is_refused_by_name(capsys):
    code = main(["discover", "projects/example-news-and-returns", "--api", "scholar"])
    assert code == 2
    assert "scholar" in capsys.readouterr().err


def test_discover_report_on_an_empty_store_says_so(tmp_path, capsys):
    code = main(["discover-report", "projects/example-news-and-returns",
                 "--store", str(tmp_path)])
    assert code == 0
    assert "no candidates" in capsys.readouterr().out


def test_the_report_prints_the_caveat_not_an_estimate(tmp_path, capsys):
    from claimstone.store import Store

    store = Store("example-news-and-returns", base=tmp_path)
    store.append("candidates.jsonl", {"candidate_key": "a", "channel": "keyword",
                                      "source_class": "ACA", "round": "routine"})
    main(["discover-report", "projects/example-news-and-returns", "--store", str(tmp_path)])
    out = capsys.readouterr().out
    assert "deliberately not combined" in out
    assert "2962" not in out
    assert "coverage" not in out.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_cli_discover.py -q`
Expected: FAIL — `discover` is not a known command

- [ ] **Step 3: Add both handlers to `claimstone/cli.py`**

```python
APIS = ("openalex", "crossref", "arxiv")


def _discover(args: argparse.Namespace) -> int:
    from claimstone import discover
    from claimstone.store import Store

    unknown = [api for api in (args.api or ()) if api not in APIS]
    if unknown:
        print(f"unknown api: {', '.join(unknown)} (known: {', '.join(APIS)})", file=sys.stderr)
        return 2

    project = load_project(args.project)
    store = Store(project.name, base=args.store)
    topics = tuple(t.strip() for t in args.topics.split(",")) if args.topics else None

    # Keyword first, then citations, and the order matters for more than tidiness. Both channels
    # skip a candidate_key already present, so whichever runs first owns a work both found. A
    # keyword row carries its topic and query; a citation row does not. And the overlap in
    # discover-report is computed as keyword keys against reference keys, so letting citations
    # claim a shared work first would make that number undercount the very thing it measures.
    if args.channel in ("keyword", "both"):
        from claimstone import net

        fetcher = net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts))
        result = discover.run(project, store, fetcher,
                              apis=tuple(args.api) if args.api else APIS,
                              topics=topics, per_query=args.per_query, round_name=args.round)
        print(f"keyword channel: {result['new']} new of {result['returned']} returned, "
              f"{result['queries']} queries")
        if result["unclassified"]:
            print(f"  {result['unclassified']} unclassified: {result['uncovered']}")
            print("  declare an assign_when rule in sources.yaml rather than loosening one")

    if args.channel in ("citation", "both"):
        result = discover.run_citations(project, store, round_name=args.round)
        if not result["references_available"]:
            print("citation channel: nothing to read — no references.jsonl yet "
                  "(run `claimstone normalize` first)")
        else:
            print(f"citation channel: {result['new']} new of {result['admitted']} admitted, "
                  f"from {result['considered']} references")
            if result["possible_duplicates"]:
                print(f"  {result['possible_duplicates']} noted as possible duplicates, "
                      f"none merged")
    return 0


def _discover_report(args: argparse.Namespace) -> int:
    from claimstone import discover_report
    from claimstone.store import Store

    project = load_project(args.project)
    summary = discover_report.summarise(
        Store(project.name, base=args.store), round_name=args.round)

    if args.json:
        import json

        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    if not summary["candidates"]:
        print(f"{project.name}: no candidates recorded")
        return 0

    print(f"{project.name} — round {summary['round'] or 'all'}")
    keyword, citation = summary["keyword"], summary["citation"]
    print(f"  keyword channel   {keyword['candidates']:>5} candidates   "
          f"{keyword['topics']} topics, {keyword['queries']} queries")
    print(f"  citation channel  {citation['candidates']:>5} candidates   "
          f"of {citation['references_seen']} references")
    print(f"  overlap           {summary['overlap']:>5} works found by both channels")
    if summary["unclassified"]:
        print(f"  unclassified      {summary['unclassified']:>5}   {summary['uncovered']}")
    for name in ("keyword", "citation"):
        by_class = summary[name]["by_class"]
        if by_class:
            print(f"  {name:<17} " + "  ".join(f"{k} {v}" for k, v in by_class.items()))
    print(f"\n  {summary['caveat']}")
    return 0
```

Register them in the command loop's tuple:

```python
        ("discover", _discover, "stage 1: topics and citations become candidates"),
        ("discover-report", _discover_report, "what the two channels found"),
```

and their flags:

```python
        if name == "discover":
            command.add_argument("--round", default="routine",
                                 help="name this round; it lands on every candidate")
            command.add_argument("--topics", help="comma-separated topic ids; default all")
            command.add_argument("--api", action="append",
                                 help=f"repeatable; one of {', '.join(APIS)}. Default all")
            command.add_argument("--per-query", type=int, default=25)
            command.add_argument("--channel", choices=("keyword", "citation", "both"),
                                 default="both")
        if name == "discover-report":
            command.add_argument("--round", default=None, help="isolate one round")
            command.add_argument("--json", action="store_true")
```

- [ ] **Step 4: Run everything**

Run: `.venv/bin/pytest -q`
Expected: PASS, all tests

Run: `.venv/bin/claimstone discover --help`
Expected: usage showing `--channel`, `--round`, repeatable `--api`

- [ ] **Step 5: Commit**

```bash
git add claimstone/cli.py tests/test_cli_discover.py
git commit -m "cli: discover and discover-report

--channel citation constructs no Fetcher, so it needs no contact address: it reads
a ledger, and demanding a crawler identity for that would be theatre. An absent
references.jsonl says nothing to read and names the command that would produce one.

The report prints the three quantities and the caveat beneath them, and never a
combined figure. Unclassified candidates print the attribute values that went
unmatched, with the instruction to declare a rule rather than loosen one.

<trailer>"
```

---

### Task 8: The candidate contract

Implements spec §9's remaining surface: the row stage 2 reads.

**Files:**
- Create: `docs/contracts/candidates.md`

- [ ] **Step 1: Write `docs/contracts/candidates.md`**

```markdown
# `candidates.jsonl` — the contract

Written by stage 1 (`claimstone discover`, `claimstone import-manifest`). Append-only. A candidate
whose recorded facts change gets a new row rather than an edit, and `latest_by` prefers it.

**Stage 2 depends on `candidate_key`, `url`, `doi`, `title` and `source_class`** — and it refuses a
row whose `source_class` is null, which is invariant 6 enforced at the boundary rather than
documented.

| field | meaning |
|---|---|
| `candidate_key` | identity: DOI, else folded title, else normalised URL |
| `title`, `url`, `doi`, `year`, `venue` | the work, as the channel reported it |
| `venue_type` | what the API called the venue; only meaningful beside `source_api` |
| `source_class` | assigned by the project's `assign_when` rules. **Null means no rule covered it** |
| `source_api` | `openalex`, `crossref`, `arxiv`, `citation`, `manifest` |
| `channel` | `keyword` or `citation` — the two channels D10 keeps independent |
| `query`, `query_hash`, `topic_id` | which search found it, so a round is reproducible |
| `cited_by`, `citations_in_corpus` | citation channel only: which corpus documents cite it |
| `possible_duplicate_of` | a near-match on title. **A note. Nothing is ever merged on it** |
| `round` | which round wrote this row; `routine` unless named |
| `source_id`, `declared_format` | manifest only |
| `is_oa`, `citations` | as the API reported, where it did |
| `found_at` | UTC, ISO 8601, seconds |

## Two fields that are easy to misread

`source_class: null` does not mean "unclassifiable". It means no declared rule matched, and
`discover-report` prints which attribute values went unmatched so a rule can be written. Stage 2
refusing the row is the intended behaviour: a classless candidate entering a pool breaks invariant
6 silently, which is worse than one that stops at the gate.

`possible_duplicate_of` is never acted on. Title matching was measured failing in both directions —
a cover banner became a title, and one real title contains another real title from a different
paper — so a duplicate is tolerated and a merge is not. A duplicate costs one wasted acquisition
attempt, and not even a second download since bytes are content-addressed; a wrong merge loses a
source and misattributes its claims.

## Channels

`keyword` is search against OpenAlex, Crossref and arXiv. `citation` is stage 3's extracted
bibliography, admitted by the project's `citation_channel` rule. They must stay independent for
D10's completeness reasoning to mean anything, which is why the citation rule filters on
`citations_in_corpus` — a property of that channel — and never on the topic terms.
```

- [ ] **Step 2: Run everything and commit**

Run: `.venv/bin/pytest -q` — expected: all pass
Run: `.venv/bin/claimstone validate --all-projects` — expected: OK for both

```bash
git add docs/contracts/candidates.md
git commit -m "docs: the candidate contract, and the two fields easy to misread

source_class null means no declared rule matched, not unclassifiable — and stage 2
refusing the row is intended. possible_duplicate_of is never acted on, because
title matching was measured failing in both directions.

<trailer>"
```

---

## What this plan does not do

- **No SearXNG, no web search** (spec §10). `NEW`, `IND` and `DOC` arrive from the manifest. The measured reason: web search on these topics returns product pages, and six of six HTML sources in the first corpus were gated as `ABSTRACT_ONLY`.
- **No DOI resolution for references.** `acquire.resolve_doi_by_title` already exists, and resolving 711 titles belongs to the stage about to fetch them.
- **No banner-title correction.** A stage 3 TEI artefact; fixed there or not at all.
- **No published completeness figure** (spec §6), and a test in Task 6 keeps it that way.
