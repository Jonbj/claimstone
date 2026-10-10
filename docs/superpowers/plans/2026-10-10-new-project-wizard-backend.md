# New-project wizard — backend Implementation Plan (plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an authenticated operator build a draft of a new project step by step, preview the figures Claimstone will derive from it, and create a frozen project (`projects/<name>/`, protocol v1) through the control server — with nothing started.

**Architecture:** A pure engine module (`project_builder.py`) validates each step, renders the three YAML files from a data template, loads them with `config.load_project` and creates the directory atomically. An append-only ledger (`wizard_drafts.py`) holds drafts. A service layer (`new_project_service.py`) joins them and raises one error type; thin handlers in `control.py` map it to the existing envelope.

**Tech Stack:** Python ≥ 3.11, PyYAML (already a dependency), pytest, the existing `claimstone.control` HTTP handler. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-10-new-project-wizard-design.md` (corrected by Task 0). Plan 2 (`2026-10-10-new-project-wizard-frontend.md`) builds the UI on the routes this plan delivers.

**Conventions in this repository:** run `.venv/bin/pytest -q <file>` for tests; every ledger row carries `actor`, `signer_auth`, `code_revision`, `recorded_at`; `CLAUDE.md` invariants apply (the engine holds no domain knowledge; a registry is a dated version; the floor has no override). Commit messages end with the two attribution lines from the session reminder.

---

## File structure

| File | Responsibility |
|---|---|
| `templates/project/general.yaml` (create) | Data: source classes, excluded hosts, notation presets, default floor. No code reads a field's conventions from anywhere else. |
| `claimstone/project_builder.py` (create) | Validate steps, render files, inspect (load + figures), create the directory. No I/O except the template, a temp dir and the one create. |
| `claimstone/wizard_drafts.py` (create) | The append-only draft ledger and its state replay. |
| `claimstone/new_project_service.py` (create) | The operations the routes call; one error type `ServiceError`. |
| `claimstone/config.py` (modify) | `discover_projects` skips dot-prefixed directories (the staging directory). |
| `claimstone/control.py` (modify) | `ControlError.details`, nine routes, thin handlers. |
| `compose.yaml` (modify) | `control` mounts `projects/` read-write and `templates/` read-only. |
| `tests/test_project_builder.py`, `tests/test_wizard_drafts.py`, `tests/test_new_project_service.py`, `tests/test_control_new_project.py` (create) | Tests per module. |
| `tests/test_compose.py` (modify) | Pin the control mounts. |
| `docs/contracts/new_project.md` (create), `docs/contracts/control_api.md`, `docs/DESIGN_DECISIONS.md` (modify) | Contract and decision D125. |

---

### Task 0: Correct the spec where verification found it wrong

Verification against the code showed four points the spec states incorrectly. Fix them before building.

**Files:** Modify `docs/superpowers/specs/2026-10-10-new-project-wizard-design.md`

- [ ] **Step 1: Apply the four corrections**

Run:

```bash
python3 - <<'PY'
p = "docs/superpowers/specs/2026-10-10-new-project-wizard-design.md"
s = open(p, encoding="utf-8").read()
pairs = [
 # 1. the search indexes are a plan choice (discover --api), not a project file
 ("source classes from the template; acquisition floor and its rationale; supplied copies (`count` or `separate`); search indexes (`openalex`, `crossref`, `arxiv`); the field's notation (`extraction.value_labels`); Advanced",
  "source classes from the template; acquisition floor and its rationale; supplied copies (`count` or `separate`); the field's notation (`extraction.value_labels`); extra excluded hosts; Advanced"),
 ("| classes, floor, searches (= terms × indexes, the rule of `operations.plan_batch`), requests \"—\" |",
  "| classes, floor, searches per index (= terms, the rule of `operations.plan_batch`) and with all three indexes, requests \"—\" |"),
 # 2. decision number
 ("D119.", "D125."), ("D119", "D125"),
 # 3. staging directory must not be discoverable, and an extra event
 ("writes them to a temporary directory beside `projects/`,",
  "writes them to a staging directory `projects/.incoming-<random>/` (`config.discover_projects` skips names starting with a dot; the rename must stay on the same mount),"),
 ("| `event` | `step_saved`, `discarded`, `created`, `create_failed` |",
  "| `event` | `started`, `step_saved`, `advanced_saved`, `discarded`, `created`, `create_failed` |"),
]
for old, new in pairs:
    assert old in s, old[:60]
    s = s.replace(old, new)
s = s.replace("`gen:types` regenerates\n`api-types.ts` from `portal-api.schema.json`.", "the control types are written by hand in `control.ts`, as the other control routes are.")
open(p, "w", encoding="utf-8").write(s)
PY
grep -n "D125\|incoming\|advanced_saved\|written by hand" docs/superpowers/specs/2026-10-10-new-project-wizard-design.md | head
```

Expected: lines for each of the four corrections.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-10-10-new-project-wizard-design.md
git commit -m "spec: correct the wizard design after checking it against the code

The search indexes are a plan choice, not a project file; the next decision
number is D125; the staging directory must not be discoverable; the draft
ledger also records started and advanced_saved; control types are hand-written.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 1: `discover_projects` skips dot-prefixed directories

The staging directory contains `questions.yaml` for a moment; a listing must never show it.

**Files:**
- Modify: `claimstone/config.py` (function `discover_projects`, near the end of the file)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_config.py`)

```python
def test_discover_projects_skips_a_staging_directory(tmp_path):
    for name in ("real", ".incoming-abc123"):
        _write(tmp_path / name, questions=GOOD_QUESTIONS)
    assert [p.name for p in discover_projects(tmp_path)] == ["real"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest -q tests/test_config.py::test_discover_projects_skips_a_staging_directory`
Expected: FAIL (`['.incoming-abc123', 'real'] != ['real']`).

- [ ] **Step 3: Implement**

In `claimstone/config.py`, replace the return line of `discover_projects`:

```python
    return sorted(p for p in base.iterdir()
                  if p.is_dir() and not p.name.startswith(".") and (p / "questions.yaml").exists())
```

- [ ] **Step 4: Run the test and the existing config tests**

Run: `.venv/bin/pytest -q tests/test_config.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add claimstone/config.py tests/test_config.py
git commit -m "config: discover_projects ignores dot-prefixed directories

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 2: The template, as data, and its loader

**Files:**
- Create: `templates/project/general.yaml`
- Create: `claimstone/project_builder.py` (first part: errors, constants, template loading)
- Test: `tests/test_project_builder.py`

- [ ] **Step 1: Write the template** `templates/project/general.yaml`

```yaml
# A template is DATA: the conventions a field brings to a project. The engine reads it as input
# (claimstone/project_builder.py) and holds none of it, so a project in an unrelated field can ship
# its own template without touching the package (CLAUDE.md invariant 4).
id: general
label: General literature review
description: >
  Six source classes from refereed papers to primary documentation, the engine's standing excluded
  hosts, and two notation presets. Derived from the worked example, which is built from public literature.
default_floor: 0.80
excluded_hosts:
  - sci-hub.se
  - sci-hub.st
  - libgen.is
classes:
  - id: ACA
    name: peer-reviewed academic
    weight_hint: highest
    notes: version of record in a refereed venue
    assign_when:
      openalex_source_type: [journal]
      crossref_type: [journal-article]
  - id: WP
    name: working paper / preprint
    weight_hint: high
    notes: not refereed, never silently promoted to peer-reviewed
    assign_when:
      source_api: [arxiv]
      openalex_source_type: [repository]
  - id: MET
    name: methodological reference
    weight_hint: high
    notes: textbook, handbook chapter, methods guide; supports design, not effect size
    assign_when:
      crossref_type: [book, book-chapter, monograph, reference-book]
    role: methodological
  - id: IND
    name: industry / practitioner research
    weight_hint: medium
    notes: vendor and practitioner research; disclose the commercial interest
  - id: NEW
    name: journalism / secondary reporting
    weight_hint: low
    notes: admissible as a pointer to a primary source, never as evidence for an effect
  - id: DOC
    name: primary documentation
    weight_hint: context
    notes: rules, provider documentation, regulatory filings
    gate_policy:
      structural_signal: none
notation_presets:
  - id: none
    label: No special notation
    value_labels: []
  - id: health
    label: Health and epidemiology (ratios, coefficients, intervals)
    value_labels:
      [OR, aOR, AOR, adjusted OR, odds ratio, adjusted odds ratio, RR, aRR, risk ratio, relative risk,
       HR, aHR, hazard ratio, IRR, incidence rate ratio, PR, prevalence ratio, beta, ß, β, b, B, d,
       "Cohen's d", g, "Hedges' g", r, rho, ρ, R2, R², eta2, η2, CI, 95% CI, 99% CI, IQR, SEM]
```

- [ ] **Step 2: Write the failing tests** `tests/test_project_builder.py`

```python
"""The project builder: no domain knowledge, no network, one atomic write."""

from __future__ import annotations

import pathlib

import pytest

from claimstone import project_builder as pb

REPO = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "templates" / "project"


def test_the_shipped_template_loads_and_lists():
    template = pb.load_template(TEMPLATES, "general")
    assert template["id"] == "general"
    assert [c["id"] for c in template["classes"]][:2] == ["ACA", "WP"]
    assert "sci-hub.se" in template["excluded_hosts"]
    assert [t["id"] for t in pb.list_templates(TEMPLATES)] == ["general"]


@pytest.mark.parametrize("bad", ["", "../etc/passwd", "General", "a" * 41, "no-such-template"])
def test_an_unknown_or_unsafe_template_id_is_refused(bad):
    with pytest.raises(pb.DraftInvalid) as raised:
        pb.load_template(TEMPLATES, bad)
    assert raised.value.problems[0].path == "template"
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_project_builder.py`
Expected: FAIL (`ModuleNotFoundError: claimstone.project_builder`).

- [ ] **Step 4: Implement the first part of `claimstone/project_builder.py`**

```python
"""Build a frozen project from a wizard draft.

Nothing in this module knows a field. Source classes, excluded hosts and notation presets come from
a template file (data); topics and questions come from the operator. The result is three YAML files
that `config.load_project` must accept, and a protocol digest that must survive a round trip through
the disk. This is the only code that writes under `projects/`, and it only ever creates a directory
that did not exist.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import re
import secrets
import shutil
import tempfile
from typing import Any

import yaml

from claimstone import flows
from claimstone.config import QUESTION_KINDS, ConfigError, load_project
from claimstone.store import Store, sha256_text

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
TEMPLATE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,20}$")
HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")

SEARCH_INDEXES = ("openalex", "crossref", "arxiv")
FILES = ("topics.yaml", "questions.yaml", "sources.yaml")
SUPPLIED_COPIES = ("count", "separate")

MAX_TOPICS, MAX_TERMS, MAX_QUESTIONS = 50, 40, 200
MAX_LABEL, MAX_TERM, MAX_QUESTION, MAX_TEXT = 200, 300, 1000, 4000
MIN_FLOOR_RATIONALE = 20  # the loader asks for this length once a floor is bumped; a first floor gets the same bar


@dataclasses.dataclass(frozen=True)
class Problem:
    """One thing wrong with a draft, at a path the form can point to."""

    path: str
    message: str


class DraftInvalid(ValueError):
    def __init__(self, problems: list[Problem]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(f"{p.path or 'draft'}: {p.message}" for p in self.problems))


class ProjectExists(Exception):
    """A project (or any entry) already has this name under `projects/`."""


class RoundTripMismatch(Exception):
    """The files on disk do not carry the protocol the preview promised."""


# --- templates --------------------------------------------------------------------------------


def template_dir(projects_dir: str | pathlib.Path) -> pathlib.Path:
    """Templates sit beside `projects/`, like `.env` and `store/`: `<root>/templates/project`."""
    return pathlib.Path(projects_dir).resolve().parent / "templates" / "project"


def load_template(templates_dir: str | pathlib.Path, template_id: str) -> dict[str, Any]:
    if not isinstance(template_id, str) or not TEMPLATE_ID_RE.fullmatch(template_id):
        raise DraftInvalid([Problem("template", "unknown template")])
    path = pathlib.Path(templates_dir) / f"{template_id}.yaml"
    if not path.is_file():
        raise DraftInvalid([Problem("template", "unknown template")])
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    missing = [k for k in ("id", "label", "classes", "excluded_hosts", "notation_presets",
                           "default_floor") if not isinstance(raw, dict) or k not in raw]
    if missing:
        # A broken template is the installation's fault, not the operator's.
        raise ConfigError(f"template {template_id}: missing {', '.join(missing)}")
    return raw


def list_templates(templates_dir: str | pathlib.Path) -> list[dict[str, str]]:
    found = []
    for path in sorted(pathlib.Path(templates_dir).glob("*.yaml")):
        if TEMPLATE_ID_RE.fullmatch(path.stem):
            raw = load_template(templates_dir, path.stem)
            found.append({"id": raw["id"], "label": raw["label"],
                          "description": str(raw.get("description") or "").strip()})
    return found
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/pytest -q tests/test_project_builder.py`
Expected: 6 passed (1 + 5 parametrized).

- [ ] **Step 6: Commit**

```bash
git add templates/project/general.yaml claimstone/project_builder.py tests/test_project_builder.py
git commit -m "builder: a data template and its loader

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 3: Validate each step

Each step normalizes to a plain dict the ledger stores. Server-assigned ids (`T01…`, `Q01…`) are filled where the form left them out. Only **structural** checks: nothing here judges what a question means.

**Files:**
- Modify: `claimstone/project_builder.py`
- Test: `tests/test_project_builder.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_project_builder.py`)

```python
STEP1 = {"name": "news-tone", "description": "In scope: firm-level news.",
         "topics": [{"label": "News and returns", "terms": ["news sentiment returns", " event study "]}]}
STEP2 = {"questions": [{"text": "Does news carry information about returns?", "kind": "effect"},
                       {"text": "Which datasets cover 2000?", "kind": "operational"}]}
STEP3 = {"template": "general", "classes": ["ACA", "WP"], "acquisition_floor": 0.8,
         "floor_rationale": "Set before the first measured round; below it coverage is uninterpretable.",
         "supplied_copies": "separate", "notation": "none", "custom_value_labels": [],
         "extra_excluded_hosts": []}


def _problems(step, data):
    with pytest.raises(pb.DraftInvalid) as raised:
        pb.normalize_step(step, data, TEMPLATES)
    return {(p.path) for p in raised.value.problems}


def test_step_1_assigns_ids_and_trims_terms():
    out = pb.normalize_step(1, STEP1, TEMPLATES)
    assert out["name"] == "news-tone"
    assert out["topics"] == [{"id": "T01", "label": "News and returns",
                              "terms": ["news sentiment returns", "event study"]}]


@pytest.mark.parametrize("bad", ["", "A", "Has Space", "-lead", "x" * 64, "../up", "a_b"])
def test_step_1_refuses_an_unsafe_project_name(bad):
    assert "name" in _problems(1, {**STEP1, "name": bad})


def test_step_1_needs_a_topic_with_terms_and_unique_ids():
    assert "topics" in _problems(1, {**STEP1, "topics": []})
    assert "topics[0].terms" in _problems(1, {**STEP1, "topics": [{"label": "x", "terms": []}]})
    dup = [{"id": "T01", "label": "a", "terms": ["t"]}, {"id": "T01", "label": "b", "terms": ["u"]}]
    assert "topics[1].id" in _problems(1, {**STEP1, "topics": dup})


def test_step_2_requires_a_known_kind_and_text():
    out = pb.normalize_step(2, STEP2, TEMPLATES)
    assert [q["id"] for q in out["questions"]] == ["Q01", "Q02"]
    assert "questions[0].kind" in _problems(2, {"questions": [{"text": "x?", "kind": ""}]})
    assert "questions[0].kind" in _problems(2, {"questions": [{"text": "x?", "kind": "vibes"}]})
    assert "questions[0].text" in _problems(2, {"questions": [{"text": "  ", "kind": "effect"}]})
    assert "questions" in _problems(2, {"questions": []})


def test_step_2_does_not_judge_wording():
    vague = {"questions": [{"text": "News works.", "kind": "effect"}]}
    assert pb.normalize_step(2, vague, TEMPLATES)["questions"][0]["text"] == "News works."


def test_step_3_normalizes_against_the_template():
    out = pb.normalize_step(3, {**STEP3, "classes": ["WP", "ACA"], "notation": "health"}, TEMPLATES)
    assert out["classes"] == ["ACA", "WP"]  # template order: most authoritative first
    assert out["acquisition_floor"] == 0.8 and out["supplied_copies"] == "separate"
    assert "OR" in out["value_labels"]


@pytest.mark.parametrize("field,value", [
    ("acquisition_floor", 0), ("acquisition_floor", 1.5), ("acquisition_floor", True),
    ("acquisition_floor", "0.8"), ("floor_rationale", "short"), ("floor_rationale", ""),
    ("supplied_copies", "maybe"), ("classes", []), ("classes", ["ZZZ"]),
    ("notation", "astrology"), ("extra_excluded_hosts", ["https://x.org/path"]),
    ("extra_excluded_hosts", ["*.example.org"]),
])
def test_step_3_refusals(field, value):
    assert field in _problems(3, {**STEP3, field: value})


def test_step_3_has_no_override_field_and_names_unknown_keys():
    # Invariant 3: there is no flag that waives the floor, so a stray key is refused by name.
    assert "override" in _problems(3, {**STEP3, "override": True})


def test_a_custom_notation_is_taken_as_typed():
    out = pb.normalize_step(3, {**STEP3, "notation": "custom", "custom_value_labels": ["Sharpe", " alpha "]}, TEMPLATES)
    assert out["value_labels"] == ["Sharpe", "alpha"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_project_builder.py`
Expected: FAIL (`AttributeError: ... normalize_step`).

- [ ] **Step 3: Implement** (append to `claimstone/project_builder.py`)

```python
# --- steps --------------------------------------------------------------------------------------


def _text(value: Any, path: str, limit: int, problems: list[Problem], *, required: bool = True) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        problems.append(Problem(path, "must be text"))
        return ""
    cleaned = value.strip()
    if required and not cleaned:
        problems.append(Problem(path, "is required"))
    if len(cleaned) > limit:
        problems.append(Problem(path, f"is over {limit} characters"))
    return cleaned


def _object(data: Any, allowed: set[str], problems: list[Problem]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise DraftInvalid([Problem("", "step data must be an object")])
    for key in sorted(set(data) - allowed):
        problems.append(Problem(key, "is not a field of this step"))
    return data


def normalize_step(step: int, data: Any, templates_dir: str | pathlib.Path) -> dict[str, Any]:
    """The step's content as the ledger stores it, or `DraftInvalid` naming every problem."""
    problems: list[Problem] = []
    if step == 1:
        out = _topic_step(data, problems)
    elif step == 2:
        out = _questions_step(data, problems)
    elif step == 3:
        out = _sources_step(data, templates_dir, problems)
    else:
        raise DraftInvalid([Problem("step", "steps are 1 to 3")])
    if problems:
        raise DraftInvalid(problems)
    return out


def _topic_step(data: Any, problems: list[Problem]) -> dict[str, Any]:
    data = _object(data, {"name", "description", "topics"}, problems)
    name = _text(data.get("name"), "name", 63, problems)
    if name and not NAME_RE.fullmatch(name):
        problems.append(Problem("name", "use 2 to 63 lowercase letters, digits or hyphens, "
                                        "starting with a letter or digit"))
    description = _text(data.get("description"), "description", MAX_TEXT, problems, required=False)
    entries = data.get("topics")
    topics: list[dict[str, Any]] = []
    if not isinstance(entries, list) or not entries:
        problems.append(Problem("topics", "add at least one topic"))
        entries = []
    if len(entries) > MAX_TOPICS:
        problems.append(Problem("topics", f"at most {MAX_TOPICS} topics"))
    seen: set[str] = set()
    for i, entry in enumerate(entries[:MAX_TOPICS]):
        base = f"topics[{i}]"
        if not isinstance(entry, dict):
            problems.append(Problem(base, "must be an object"))
            continue
        topic_id = str(entry.get("id") or "").strip() or f"T{i + 1:02d}"
        if not ID_RE.fullmatch(topic_id):
            problems.append(Problem(f"{base}.id", "use letters, digits, - or _ (at most 20)"))
        if topic_id in seen:
            problems.append(Problem(f"{base}.id", "is used by another topic"))
        seen.add(topic_id)
        label = _text(entry.get("label"), f"{base}.label", MAX_LABEL, problems)
        terms: list[str] = []
        raw_terms = entry.get("terms")
        if not isinstance(raw_terms, list) or not raw_terms:
            problems.append(Problem(f"{base}.terms", "add at least one search term"))
            raw_terms = []
        if len(raw_terms) > MAX_TERMS:
            problems.append(Problem(f"{base}.terms", f"at most {MAX_TERMS} terms"))
        for j, term in enumerate(raw_terms[:MAX_TERMS]):
            cleaned = _text(term, f"{base}.terms[{j}]", MAX_TERM, problems)
            if cleaned and cleaned in terms:
                problems.append(Problem(f"{base}.terms[{j}]", "is repeated in this topic"))
            if cleaned:
                terms.append(cleaned)
        topics.append({"id": topic_id, "label": label, "terms": terms})
    return {"name": name, "description": description, "topics": topics}


def _questions_step(data: Any, problems: list[Problem]) -> dict[str, Any]:
    data = _object(data, {"questions"}, problems)
    entries = data.get("questions")
    if not isinstance(entries, list) or not entries:
        problems.append(Problem("questions", "add at least one question"))
        entries = []
    if len(entries) > MAX_QUESTIONS:
        problems.append(Problem("questions", f"at most {MAX_QUESTIONS} questions"))
    questions: list[dict[str, str]] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries[:MAX_QUESTIONS]):
        base = f"questions[{i}]"
        if not isinstance(entry, dict):
            problems.append(Problem(base, "must be an object"))
            continue
        qid = str(entry.get("id") or "").strip() or f"Q{i + 1:02d}"
        if not ID_RE.fullmatch(qid):
            problems.append(Problem(f"{base}.id", "use letters, digits, - or _ (at most 20)"))
        if qid in seen:
            problems.append(Problem(f"{base}.id", "is used by another question"))
        seen.add(qid)
        text = _text(entry.get("text"), f"{base}.text", MAX_QUESTION, problems)
        kind = str(entry.get("kind") or "").strip()
        if kind not in QUESTION_KINDS:
            problems.append(Problem(f"{base}.kind", "choose one of " + ", ".join(QUESTION_KINDS)))
        questions.append({"id": qid, "text": text, "kind": kind})
    return {"questions": questions}


def _sources_step(data: Any, templates_dir: str | pathlib.Path,
                  problems: list[Problem]) -> dict[str, Any]:
    allowed = {"template", "classes", "acquisition_floor", "floor_rationale", "supplied_copies",
               "notation", "custom_value_labels", "extra_excluded_hosts"}
    data = _object(data, allowed, problems)
    template = load_template(templates_dir, data.get("template", "general"))
    known = [c["id"] for c in template["classes"]]
    chosen = data.get("classes")
    if not isinstance(chosen, list) or not chosen:
        problems.append(Problem("classes", "choose at least one source class"))
        chosen = []
    unknown = [c for c in chosen if c not in known]
    if unknown:
        problems.append(Problem("classes", "unknown class: " + ", ".join(map(str, unknown))))
    floor = data.get("acquisition_floor")
    if isinstance(floor, bool) or not isinstance(floor, (int, float)) or not 0 < float(floor) <= 1:
        problems.append(Problem("acquisition_floor", "must be a number above 0 and at most 1"))
        floor = 0.0
    rationale = _text(data.get("floor_rationale"), "floor_rationale", MAX_TEXT, problems)
    if rationale and len(rationale) < MIN_FLOOR_RATIONALE:
        problems.append(Problem("floor_rationale",
                                f"say why, in at least {MIN_FLOOR_RATIONALE} characters"))
    supplied = data.get("supplied_copies")
    if supplied not in SUPPLIED_COPIES:
        problems.append(Problem("supplied_copies", "choose count or separate"))
    notation = data.get("notation", "none")
    presets = {p["id"]: p for p in template["notation_presets"]}
    value_labels: list[str] = []
    if notation == "custom":
        raw = data.get("custom_value_labels")
        if not isinstance(raw, list):
            problems.append(Problem("custom_value_labels", "must be a list"))
            raw = []
        for j, label in enumerate(raw[:200]):
            cleaned = _text(label, f"custom_value_labels[{j}]", MAX_LABEL, problems)
            if cleaned and cleaned not in value_labels:
                value_labels.append(cleaned)
    elif notation in presets:
        value_labels = list(presets[notation]["value_labels"])
    else:
        problems.append(Problem("notation", "unknown notation"))
    hosts: list[str] = []
    raw_hosts = data.get("extra_excluded_hosts", [])
    if not isinstance(raw_hosts, list):
        problems.append(Problem("extra_excluded_hosts", "must be a list"))
        raw_hosts = []
    for j, host in enumerate(raw_hosts[:100]):
        cleaned = str(host).strip().lower() if isinstance(host, str) else ""
        if not HOST_RE.fullmatch(cleaned):
            problems.append(Problem(f"extra_excluded_hosts[{j}]", "use a bare host name, no scheme, path or wildcard"))
        elif cleaned not in hosts and cleaned not in template["excluded_hosts"]:
            hosts.append(cleaned)
    return {"template": template["id"], "classes": [c for c in known if c in chosen],
            "acquisition_floor": float(floor), "floor_rationale": rationale,
            "supplied_copies": supplied if supplied in SUPPLIED_COPIES else "",
            "notation": notation if notation in presets or notation == "custom" else "none",
            "value_labels": value_labels, "extra_excluded_hosts": hosts}
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest -q tests/test_project_builder.py`
Expected: all pass. (`test_step_3_keeps_the_floor_with_no_override_key` asserts unknown keys such as `override` are named.)

- [ ] **Step 5: Commit**

```bash
git add claimstone/project_builder.py tests/test_project_builder.py
git commit -m "builder: validate and normalize the three steps

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 4: Render, inspect and figures

`inspect` is the one place a preview and a creation agree: it loads the rendered files with the real loader and derives the figures **inside** the temporary directory (the project reads its population policy lazily).

**Files:**
- Modify: `claimstone/project_builder.py`
- Test: `tests/test_project_builder.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
def _state():
    return {1: pb.normalize_step(1, STEP1, TEMPLATES), 2: pb.normalize_step(2, STEP2, TEMPLATES),
            3: pb.normalize_step(3, STEP3, TEMPLATES)}


def test_render_freezes_version_1_with_todays_date():
    files = pb.render(_state(), TEMPLATES, today="2026-10-10")
    assert set(files) == set(pb.FILES)
    assert "registry_version: 1" in files["questions.yaml"]
    assert "frozen_at: '2026-10-10'" in files["questions.yaml"]
    assert "floor_version: 1" in files["sources.yaml"]
    assert "floor_set_at: '2026-10-10'" in files["sources.yaml"]
    assert files["topics.yaml"].startswith("description:")


def test_render_needs_all_three_steps():
    with pytest.raises(pb.DraftInvalid) as raised:
        pb.render({1: _state()[1]}, TEMPLATES, today="2026-10-10")
    assert {p.path for p in raised.value.problems} == {"step 2", "step 3"}


def test_inspect_loads_with_the_real_loader_and_derives_figures():
    info = pb.inspect(pb.render(_state(), TEMPLATES, today="2026-10-10"), name="news-tone",
                      templates_dir=TEMPLATES, template_id="general")
    fig = info["figures"]
    assert (fig["topics"], fig["terms"]) == (1, 2)
    assert (fig["searches_per_index"], fig["searches_all_indexes"]) == (2, 6)
    assert (fig["questions_total"], fig["questions_literature"], fig["questions_operational"]) == (2, 1, 1)
    assert fig["questions_by_kind"]["effect"] == 1 and fig["classes"] == ["ACA", "WP"]
    assert fig["acquisition_floor"] == 0.8 and fig["requests_max"] is None
    assert len(info["protocol_sha256"]) == 64


def test_a_description_does_not_change_the_protocol_digest():
    base = _state()
    other = {**base, 1: {**base[1], "description": "a completely different description"}}
    a = pb.inspect(pb.render(base, TEMPLATES, today="2026-10-10"), name="x1",
                   templates_dir=TEMPLATES, template_id="general")
    b = pb.inspect(pb.render(other, TEMPLATES, today="2026-10-10"), name="x1",
                   templates_dir=TEMPLATES, template_id="general")
    assert a["protocol_sha256"] == b["protocol_sha256"]


def test_an_override_must_still_load():
    files = pb.render(_state(), TEMPLATES, today="2026-10-10",
                      overrides={"sources.yaml": "classes: []\n"})
    with pytest.raises(pb.DraftInvalid) as raised:
        pb.inspect(files, name="news-tone", templates_dir=TEMPLATES, template_id="general")
    assert raised.value.problems[0].path == "sources.yaml"


def test_an_override_cannot_remove_a_template_excluded_host():
    state = _state()
    files = pb.render(state, TEMPLATES, today="2026-10-10")
    files["sources.yaml"] = files["sources.yaml"].replace("- sci-hub.se\n", "")
    with pytest.raises(pb.DraftInvalid) as raised:
        pb.inspect(files, name="news-tone", templates_dir=TEMPLATES, template_id="general")
    assert "sci-hub.se" in raised.value.problems[0].message


def test_an_unknown_override_file_is_refused():
    with pytest.raises(pb.DraftInvalid):
        pb.render(_state(), TEMPLATES, today="2026-10-10", overrides={"manifest.tsv": "x"})


def test_a_question_with_no_kind_in_an_override_is_counted_unassigned():
    files = pb.render(_state(), TEMPLATES, today="2026-10-10")
    files["questions.yaml"] = ("registry_version: 1\nfrozen_at: '2026-10-10'\nquestions:\n"
                               "- {id: Q01, text: 'x?'}\n")
    info = pb.inspect(files, name="news-tone", templates_dir=TEMPLATES, template_id="general")
    assert info["figures"]["questions_by_kind"]["unassigned"] == 1
    assert info["figures"]["questions_literature"] == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_project_builder.py`
Expected: FAIL (`AttributeError: ... render`).

- [ ] **Step 3: Implement** (append to `claimstone/project_builder.py`)

```python
# --- rendering ----------------------------------------------------------------------------------


def _dump(obj: Any) -> str:
    return yaml.safe_dump(obj, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100)


def render(state: dict[int, dict[str, Any]], templates_dir: str | pathlib.Path, *, today: str,
           overrides: dict[str, str] | None = None) -> dict[str, str]:
    """The three files' text. A fixed serializer, never string concatenation. `today` is the day the
    protocol is frozen: registry v1 and floor v1 both carry it."""
    missing = [Problem(f"step {n}", "is not saved yet") for n in (1, 2, 3) if n not in state]
    if missing:
        raise DraftInvalid(missing)
    one, two, three = state[1], state[2], state[3]
    template = load_template(templates_dir, three["template"])
    topics: dict[str, Any] = {}
    if one.get("description"):
        topics["description"] = one["description"]  # not read by the loader: the digest ignores it
    topics["topics"] = one["topics"]
    questions = {"registry_version": 1, "frozen_at": today,
                 "questions": [{"id": q["id"], "text": q["text"], "kind": q["kind"]}
                               for q in two["questions"]]}
    sources: dict[str, Any] = {
        "classes": [c for c in template["classes"] if c["id"] in three["classes"]],
        "acquisition_floor": three["acquisition_floor"],
        "floor_version": 1, "floor_set_at": today, "floor_rationale": three["floor_rationale"],
        "excluded_hosts": list(template["excluded_hosts"]) + list(three["extra_excluded_hosts"]),
        "supplied_copies": three["supplied_copies"],
    }
    if three["value_labels"]:
        sources["extraction"] = {"value_labels": three["value_labels"]}
    files = {"topics.yaml": _dump(topics), "questions.yaml": _dump(questions),
             "sources.yaml": _dump(sources)}
    for name, text in (overrides or {}).items():
        if name not in FILES:
            raise DraftInvalid([Problem(str(name), "is not one of the project's files")])
        if not isinstance(text, str):
            raise DraftInvalid([Problem(name, "must be text")])
        files[name] = text
    return files


def _file_of(message: str) -> str:
    for name in FILES:
        if message.startswith(name):
            return name
    return ""


def figures(project: Any) -> dict[str, Any]:
    """Everything the explanation panel may quote, derived from the loaded project and nothing else.
    A figure not knowable here is None and renders as a dash."""
    kinds: dict[str, int] = {}
    for question in project.questions:
        kinds[question.kind or "unassigned"] = kinds.get(question.kind or "unassigned", 0) + 1
    operational = kinds.get("operational", 0)
    total = len(project.questions)
    terms = sum(len(topic.terms) for topic in project.topics)
    return {
        "topics": len(project.topics), "terms": terms,
        "searches_per_index": terms, "indexes_available": list(SEARCH_INDEXES),
        "searches_all_indexes": terms * len(SEARCH_INDEXES),
        "questions_total": total, "questions_literature": total - operational,
        "questions_operational": operational, "questions_by_kind": kinds,
        "classes": [c.id for c in project.classes],
        "acquisition_floor": project.acquisition_floor, "floor_version": project.floor_version,
        "excluded_hosts": len(project.excluded_hosts), "supplied_copies": project.supplied_copies,
        "registry_version": project.registry_version, "frozen_at": project.frozen_at,
        "requests_max": None,  # known only when an exact plan is frozen (stage 2)
    }


def inspect(files: dict[str, str], *, name: str, templates_dir: str | pathlib.Path,
            template_id: str) -> dict[str, Any]:
    """Load the files with the real loader and derive the figures. Raises `DraftInvalid`."""
    if set(files) != set(FILES):
        raise DraftInvalid([Problem("files", "need exactly " + ", ".join(FILES))])
    template = load_template(templates_dir, template_id)
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / name
        root.mkdir()
        for filename, text in files.items():
            (root / filename).write_text(text, encoding="utf-8")
        try:
            project = load_project(root)
            lost = sorted(set(template["excluded_hosts"]) - set(project.excluded_hosts))
            if lost:
                raise DraftInvalid([Problem("sources.yaml", "the template's excluded hosts cannot "
                                            "be removed: " + ", ".join(lost))])
            return {"figures": figures(project), "protocol_sha256": flows.protocol_digest(project)}
        except ConfigError as exc:
            raise DraftInvalid([Problem(_file_of(str(exc)), str(exc))]) from exc
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest -q tests/test_project_builder.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add claimstone/project_builder.py tests/test_project_builder.py
git commit -m "builder: render the three files, load them with the real loader, derive figures

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 5: Create the project atomically, and never touch an existing one

**Files:**
- Modify: `claimstone/project_builder.py`
- Test: `tests/test_project_builder.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
import hashlib
import shutil

from claimstone.config import load_project, discover_projects
from claimstone.store import Store


def _tree_hash(root: pathlib.Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _prepared(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    files = pb.render(_state(), TEMPLATES, today="2026-10-10")
    info = pb.inspect(files, name="news-tone", templates_dir=TEMPLATES, template_id="general")
    return projects, files, info, Store("_new-projects", base=tmp_path / "store")


def test_create_writes_three_files_that_load_with_the_same_digest(tmp_path):
    projects, files, info, lock = _prepared(tmp_path)
    result = pb.create_project(projects, "news-tone", files,
                               expected_protocol_sha256=info["protocol_sha256"], lock_store=lock)
    root = projects / "news-tone"
    assert sorted(p.name for p in root.iterdir()) == sorted(pb.FILES)
    assert result["files"]["questions.yaml"] == hashlib.sha256(files["questions.yaml"].encode()).hexdigest()
    assert pb.flows.protocol_digest(load_project(root)) == info["protocol_sha256"]
    assert [p.name for p in discover_projects(projects)] == ["news-tone"]


def test_create_refuses_any_existing_entry_and_changes_nothing(tmp_path):
    projects, files, info, lock = _prepared(tmp_path)
    shutil.copytree(REPO / "projects" / "example-news-and-returns", projects / "news-tone")
    before = _tree_hash(projects)
    with pytest.raises(pb.ProjectExists):
        pb.create_project(projects, "news-tone", files,
                          expected_protocol_sha256=info["protocol_sha256"], lock_store=lock)
    assert _tree_hash(projects) == before
    assert not [p for p in projects.iterdir() if p.name.startswith(".incoming")]


def test_a_digest_mismatch_leaves_no_project_and_no_staging(tmp_path):
    projects, files, info, lock = _prepared(tmp_path)
    with pytest.raises(pb.RoundTripMismatch):
        pb.create_project(projects, "news-tone", files, expected_protocol_sha256="0" * 64,
                          lock_store=lock)
    assert list(projects.iterdir()) == []


def test_a_file_that_no_longer_loads_leaves_nothing(tmp_path):
    projects, files, info, lock = _prepared(tmp_path)
    broken = {**files, "sources.yaml": "classes: []\n"}
    with pytest.raises(pb.DraftInvalid):
        pb.create_project(projects, "news-tone", broken,
                          expected_protocol_sha256=info["protocol_sha256"], lock_store=lock)
    assert list(projects.iterdir()) == []


@pytest.mark.parametrize("bad", ["../escape", "A", "", "a/b", ".hidden"])
def test_create_refuses_a_name_that_could_be_a_path(tmp_path, bad):
    projects, files, info, lock = _prepared(tmp_path)
    with pytest.raises(pb.DraftInvalid):
        pb.create_project(projects, bad, files, expected_protocol_sha256=info["protocol_sha256"],
                          lock_store=lock)
    assert list(projects.iterdir()) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_project_builder.py -k create`
Expected: FAIL (`AttributeError: ... create_project`).

- [ ] **Step 3: Implement** (append to `claimstone/project_builder.py`)

```python
# --- creation -----------------------------------------------------------------------------------


def create_project(projects_dir: str | pathlib.Path, name: str, files: dict[str, str], *,
                   expected_protocol_sha256: str, lock_store: Store) -> dict[str, Any]:
    """Create `projects/<name>/` from three files. The only writer under `projects/`.

    It creates a directory that did not exist and nothing else: no file of an existing project is
    opened for writing. The files are written to `projects/.incoming-<random>/` (the same mount, so the
    rename is atomic; `discover_projects` ignores the dot), loaded with the real loader, compared with
    the protocol the preview promised, and only then renamed. Everything is serialized under one
    lock so two creations cannot race for a name.
    """
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise DraftInvalid([Problem("name", "not a valid project name")])
    if set(files) != set(FILES):
        raise DraftInvalid([Problem("files", "need exactly " + ", ".join(FILES))])
    projects = pathlib.Path(projects_dir)
    final = projects / name
    with lock_store.writer_lock():
        if os.path.lexists(final):
            raise ProjectExists(name)
        projects.mkdir(parents=True, exist_ok=True)
        staging = projects / f".incoming-{secrets.token_hex(8)}"
        staging.mkdir()
        try:
            for filename in FILES:
                (staging / filename).write_text(files[filename], encoding="utf-8")
            try:
                loaded = flows.protocol_digest(load_project(staging))
            except ConfigError as exc:
                raise DraftInvalid([Problem(_file_of(str(exc)), str(exc))]) from exc
            if loaded != expected_protocol_sha256:
                raise RoundTripMismatch(f"files carry {loaded}, the preview promised "
                                        f"{expected_protocol_sha256}")
            os.rename(staging, final)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    return {"project": name, "protocol_sha256": loaded,
            "files": {filename: sha256_text(files[filename]) for filename in FILES}}
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest -q tests/test_project_builder.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add claimstone/project_builder.py tests/test_project_builder.py
git commit -m "builder: create a project atomically; never touch an existing one

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 6: The draft ledger

One append per save. State is replayed from the rows; a draft belongs to the operator who started it and is never shown to another (a stranger's id answers 404).

**Files:**
- Create: `claimstone/wizard_drafts.py`
- Test: `tests/test_wizard_drafts.py`

- [ ] **Step 1: Write the failing tests** `tests/test_wizard_drafts.py`

```python
from __future__ import annotations

import pytest

from claimstone import wizard_drafts as wd


@pytest.fixture()
def store(tmp_path):
    return wd.open_store(tmp_path / "store")


def _start(store, actor="op1"):
    return wd.start(store, actor=actor, code_revision="abc")["draft_id"]


def test_a_started_draft_is_open_at_revision_1(store):
    draft = _start(store)
    state = wd.state(store, draft, "op1")
    assert (state["status"], state["revision"], state["steps"]) == ("open", 1, {})


def test_saving_a_step_needs_the_current_revision(store):
    draft = _start(store)
    row = wd.save_step(store, actor="op1", draft_id=draft, step=1, base_revision=1,
                       data={"name": "x"}, code_revision="abc")
    assert row["revision"] == 2 and row["event"] == "step_saved" and row["signer_auth"] == "portal-session"
    with pytest.raises(wd.DraftRefused) as raised:
        wd.save_step(store, actor="op1", draft_id=draft, step=1, base_revision=1,
                     data={"name": "y"}, code_revision="abc")
    assert (raised.value.status, raised.value.code) == (409, "STALE_REVISION")
    assert wd.state(store, draft, "op1")["steps"][1]["data"] == {"name": "x"}


def test_the_latest_row_per_step_is_the_state(store):
    draft = _start(store)
    wd.save_step(store, actor="op1", draft_id=draft, step=2, base_revision=1, data={"a": 1}, code_revision=None)
    wd.save_step(store, actor="op1", draft_id=draft, step=2, base_revision=2, data={"a": 2}, code_revision=None)
    assert wd.state(store, draft, "op1")["steps"][2] == {"data": {"a": 2}, "revision": 3}


def test_another_operators_draft_does_not_exist(store):
    draft = _start(store, "op1")
    with pytest.raises(wd.DraftRefused) as raised:
        wd.state(store, draft, "op2")
    assert raised.value.status == 404
    assert wd.list_drafts(store, "op2") == []


def test_a_discarded_or_created_draft_is_closed(store):
    draft = _start(store)
    wd.discard(store, actor="op1", draft_id=draft, base_revision=1, code_revision=None)
    assert wd.state(store, draft, "op1")["status"] == "discarded"
    with pytest.raises(wd.DraftRefused) as raised:
        wd.save_step(store, actor="op1", draft_id=draft, step=1, base_revision=2, data={}, code_revision=None)
    assert (raised.value.status, raised.value.code) == (409, "DRAFT_CLOSED")


def test_advanced_overrides_are_replaced_as_a_whole(store):
    draft = _start(store)
    wd.save_advanced(store, actor="op1", draft_id=draft, base_revision=1,
                     files={"sources.yaml": "a"}, code_revision=None)
    wd.save_advanced(store, actor="op1", draft_id=draft, base_revision=2, files={}, code_revision=None)
    assert wd.state(store, draft, "op1")["advanced"] == {}


def test_created_and_failed_are_recorded_without_a_revision_check(store):
    draft = _start(store)
    wd.mark_failed(store, actor="op1", draft_id=draft, reason="name taken", code_revision=None)
    assert wd.state(store, draft, "op1")["status"] == "open"
    assert wd.state(store, draft, "op1")["last_failure"] == "name taken"
    wd.mark_created(store, actor="op1", draft_id=draft, project="news-tone",
                    files={"topics.yaml": "h"}, code_revision=None)
    state = wd.state(store, draft, "op1")
    assert (state["status"], state["project"]) == ("created", "news-tone")


def test_the_list_summarizes_only_my_drafts_newest_first(store):
    first, second = _start(store), _start(store)
    wd.save_step(store, actor="op1", draft_id=first, step=1, base_revision=1,
                 data={"name": "news-tone"}, code_revision=None)
    _start(store, "op2")
    listed = wd.list_drafts(store, "op1")
    assert [d["draft_id"] for d in listed] == [first, second]  # first was updated last
    assert listed[0]["project_name"] == "news-tone" and listed[0]["steps_saved"] == [1]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_wizard_drafts.py`
Expected: FAIL (`ModuleNotFoundError: claimstone.wizard_drafts`).

- [ ] **Step 3: Implement** `claimstone/wizard_drafts.py`

```python
"""The new-project wizard's drafts — append-only, private to the operator who started them.

A draft is what someone typed before a project existed. `wizard_drafts.jsonl` lives in
`store/_new-projects/` (there is no project yet to hold it), and like every ledger it is only ever
appended to: the state of a draft is replayed from its rows. No stage, profile, verdict or export
reads it. A save names the revision it was based on, so two tabs cannot silently overwrite each other.
"""

from __future__ import annotations

import datetime as _dt
import pathlib
import secrets
from typing import Any

from claimstone.store import Store

WIZARD_VERSION = 1
LEDGER = "wizard_drafts.jsonl"
STORE_NAME = "_new-projects"


class DraftRefused(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def open_store(store_base: str | pathlib.Path) -> Store:
    return Store(STORE_NAME, base=store_base)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _row(draft_id: str, event: str, revision: int, actor: str, code_revision: str | None, *,
         step: int | None = None, data: Any = None, project: str | None = None,
         note: str | None = None) -> dict[str, Any]:
    return {"wizard_version": WIZARD_VERSION, "event": event, "draft_id": draft_id,
            "revision": revision, "step": step, "data": data, "project": project, "note": note,
            "actor": str(actor), "signer_auth": "portal-session", "code_revision": code_revision,
            "recorded_at": _now()}


def _rows(store: Store, draft_id: str) -> list[dict[str, Any]]:
    return [r for r in store.read(LEDGER) if r.get("draft_id") == draft_id]


def start(store: Store, *, actor: str, code_revision: str | None) -> dict[str, Any]:
    row = _row(secrets.token_hex(16), "started", 1, actor, code_revision)
    store.append(LEDGER, row)
    return row


def state(store: Store, draft_id: str, actor: str) -> dict[str, Any]:
    """Replay one draft. Another operator's draft, and an unknown id, are the same 404."""
    rows = _rows(store, str(draft_id))
    if not rows or rows[0].get("actor") != str(actor):
        raise DraftRefused(404, "NOT_FOUND", "no such draft")
    steps: dict[int, dict[str, Any]] = {}
    advanced: dict[str, str] = {}
    status, project, failure = "open", None, None
    for row in rows:
        event = row["event"]
        if event == "step_saved":
            steps[int(row["step"])] = {"data": row["data"], "revision": row["revision"]}
        elif event == "advanced_saved":
            advanced = dict(row["data"] or {})
        elif event == "discarded":
            status = "discarded"
        elif event == "created":
            status, project = "created", row["project"]
        elif event == "create_failed":
            failure = row["note"]
    return {"draft_id": str(draft_id), "revision": rows[-1]["revision"], "status": status,
            "steps": steps, "advanced": advanced, "project": project, "last_failure": failure,
            "started_at": rows[0]["recorded_at"], "updated_at": rows[-1]["recorded_at"]}


def _append(store: Store, draft_id: str, actor: str, event: str, code_revision: str | None, *,
            base_revision: int | None, **fields: Any) -> dict[str, Any]:
    with store.writer_lock():
        current = state(store, draft_id, actor)
        if current["status"] != "open":
            raise DraftRefused(409, "DRAFT_CLOSED", f"this draft is {current['status']}")
        if base_revision is not None and base_revision != current["revision"]:
            raise DraftRefused(409, "STALE_REVISION",
                               f"saved from revision {base_revision}; the draft is at "
                               f"revision {current['revision']}")
        row = _row(draft_id, event, current["revision"] + 1, actor, code_revision, **fields)
        store.append(LEDGER, row)
        return row


def save_step(store: Store, *, actor: str, draft_id: str, step: int, base_revision: int,
              data: dict[str, Any], code_revision: str | None) -> dict[str, Any]:
    return _append(store, draft_id, actor, "step_saved", code_revision,
                   base_revision=base_revision, step=step, data=data)


def save_advanced(store: Store, *, actor: str, draft_id: str, base_revision: int,
                  files: dict[str, str], code_revision: str | None) -> dict[str, Any]:
    return _append(store, draft_id, actor, "advanced_saved", code_revision,
                   base_revision=base_revision, data=files)


def discard(store: Store, *, actor: str, draft_id: str, base_revision: int,
            code_revision: str | None) -> dict[str, Any]:
    return _append(store, draft_id, actor, "discarded", code_revision, base_revision=base_revision)


def mark_created(store: Store, *, actor: str, draft_id: str, project: str, files: dict[str, str],
                 code_revision: str | None) -> dict[str, Any]:
    return _append(store, draft_id, actor, "created", code_revision, base_revision=None,
                   project=project, data=files)


def mark_failed(store: Store, *, actor: str, draft_id: str, reason: str,
                code_revision: str | None) -> dict[str, Any]:
    return _append(store, draft_id, actor, "create_failed", code_revision, base_revision=None,
                   note=str(reason)[:500])


def list_drafts(store: Store, actor: str) -> list[dict[str, Any]]:
    """This operator's drafts, most recently updated first."""
    mine = sorted({r["draft_id"] for r in store.read(LEDGER)
                   if r["event"] == "started" and r.get("actor") == str(actor)})
    out = []
    for draft_id in mine:
        current = state(store, draft_id, actor)
        first = (current["steps"].get(1) or {}).get("data") or {}
        out.append({"draft_id": draft_id, "status": current["status"],
                    "revision": current["revision"], "steps_saved": sorted(current["steps"]),
                    "project_name": first.get("name"), "project": current["project"],
                    "updated_at": current["updated_at"]})
    return sorted(out, key=lambda d: (d["updated_at"], d["revision"]), reverse=True)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest -q tests/test_wizard_drafts.py`
Expected: all pass. (Two rows written in the same second tie on `updated_at`; the revision breaks the tie, so the draft saved last sorts first.)

- [ ] **Step 5: Commit**

```bash
git add claimstone/wizard_drafts.py tests/test_wizard_drafts.py
git commit -m "wizard: an append-only draft ledger, private to its operator

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 7: The service layer

Joins builder and ledger; one error type for the routes. `today` is a module function so tests can fix it.

**Files:**
- Create: `claimstone/new_project_service.py`
- Test: `tests/test_new_project_service.py`

- [ ] **Step 1: Write the failing tests** `tests/test_new_project_service.py`

```python
from __future__ import annotations

import pathlib
import shutil

import pytest

from claimstone import new_project_service as svc
from claimstone.config import load_project

REPO = pathlib.Path(__file__).resolve().parents[1]

STEP1 = {"name": "news-tone", "description": "scope", "topics": [{"label": "News", "terms": ["a b", "c d"]}]}
STEP2 = {"questions": [{"text": "Does news carry information?", "kind": "effect"},
                       {"text": "Which datasets exist?", "kind": "operational"}]}
STEP3 = {"template": "general", "classes": ["ACA"], "acquisition_floor": 0.8,
         "floor_rationale": "Set before the first measured round; below it coverage is uninterpretable.",
         "supplied_copies": "separate", "notation": "none", "custom_value_labels": [],
         "extra_excluded_hosts": []}


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    (tmp_path / "projects").mkdir()
    shutil.copytree(REPO / "templates", tmp_path / "templates")
    monkeypatch.setattr(svc, "_today", lambda: "2026-10-10")
    return {"projects": tmp_path / "projects", "store": tmp_path / "store"}


def _call(fn, ws, *args, **kw):
    return fn(ws["projects"], ws["store"], "op1", "rev", *args, **kw)


def _fill(ws):
    draft = _call(svc.start, ws)[0]["draft_id"]
    rev = 1
    for step, data in ((1, STEP1), (2, STEP2), (3, STEP3)):
        payload, _ = _call(svc.save_step, ws, draft, step, rev, data)
        rev = payload["revision"]
    return draft, rev


def _refused(fn, ws, *args):
    with pytest.raises(svc.ServiceError) as raised:
        _call(fn, ws, *args)
    return raised.value


def test_a_saved_step_returns_normalized_data_and_figures(ws):
    draft = _call(svc.start, ws)[0]["draft_id"]
    payload, status = _call(svc.save_step, ws, draft, 1, 1, STEP1)
    assert status == 200 and payload["revision"] == 2
    assert payload["data"]["topics"][0]["id"] == "T01"
    assert payload["figures"] == {"topics": 1, "terms": 2, "searches_per_index": 2,
                                  "searches_all_indexes": 6}


def test_an_invalid_step_is_422_with_paths_and_writes_nothing(ws):
    draft = _call(svc.start, ws)[0]["draft_id"]
    error = _refused(svc.save_step, ws, draft, 1, 1, {**STEP1, "name": "Bad Name"})
    assert (error.status, error.code) == (422, "VALIDATION")
    assert error.details == [{"path": "name", "message": error.details[0]["message"]}]
    assert _call(svc.read, ws, draft)[0]["revision"] == 1


def test_a_taken_name_is_refused_at_step_1(ws):
    (ws["projects"] / "news-tone").mkdir()
    draft = _call(svc.start, ws)[0]["draft_id"]
    error = _refused(svc.save_step, ws, draft, 1, 1, STEP1)
    assert error.status == 422 and error.details[0]["path"] == "name"


def test_reading_a_draft_returns_the_figures_of_its_saved_steps(ws):
    draft, _ = _fill(ws)
    payload, _ = _call(svc.read, ws, draft)
    assert set(payload["steps"]) == {"1", "2", "3"}
    assert payload["figures"]["1"]["searches_per_index"] == 2
    assert payload["figures"]["2"]["questions_operational"] == 1
    assert payload["figures"]["3"]["classes"] == ["ACA"]


def test_the_preview_needs_all_three_steps_then_shows_files_and_figures(ws):
    draft = _call(svc.start, ws)[0]["draft_id"]
    assert _refused(svc.preview, ws, draft).status == 409
    draft, _ = _fill(ws)
    payload, _ = _call(svc.preview, ws, draft)
    assert payload["figures"]["questions_operational"] == 1
    assert set(payload["files"]) == {"topics.yaml", "questions.yaml", "sources.yaml"}
    assert len(payload["protocol_sha256"]) == 64


def test_advanced_text_is_validated_and_shown_in_the_preview(ws):
    draft, rev = _fill(ws)
    files = _call(svc.preview, ws, draft)[0]["files"]
    edited = files["sources.yaml"].replace("acquisition_floor: 0.8", "acquisition_floor: 0.9")
    payload, status = _call(svc.save_advanced, ws, draft, rev, {"sources.yaml": edited})
    assert status == 200
    assert _call(svc.preview, ws, draft)[0]["figures"]["acquisition_floor"] == 0.9
    error = _refused(svc.save_advanced, ws, draft, payload["revision"], {"sources.yaml": "classes: []\n"})
    assert error.status == 422 and error.details[0]["path"] == "sources.yaml"


def test_create_makes_a_frozen_project_and_closes_the_draft(ws):
    draft, _ = _fill(ws)
    payload, status = _call(svc.create, ws, draft, True)
    assert status == 201 and payload["project"] == "news-tone"
    project = load_project(ws["projects"] / "news-tone")
    assert (project.registry_version, project.frozen_at, project.floor_version) == (1, "2026-10-10", 1)
    assert _call(svc.read, ws, draft)[0]["status"] == "created"
    assert _refused(svc.create, ws, draft, True).code == "DRAFT_CLOSED"


def test_create_needs_the_literal_confirmation(ws):
    draft, _ = _fill(ws)
    assert _refused(svc.create, ws, draft, False).status == 422
    assert not (ws["projects"] / "news-tone").exists()


def test_a_name_taken_after_step_1_is_a_409_and_recorded(ws):
    draft, _ = _fill(ws)
    (ws["projects"] / "news-tone").mkdir()
    error = _refused(svc.create, ws, draft, True)
    assert (error.status, error.code) == (409, "NAME_TAKEN")
    assert _call(svc.read, ws, draft)[0]["last_failure"]
    assert _call(svc.read, ws, draft)[0]["status"] == "open"
    assert not [p for p in ws["projects"].iterdir() if p.name.startswith(".incoming")]


def test_templates_are_listed_and_read(ws):
    listed, _ = _call(svc.templates, ws)
    assert [t["id"] for t in listed["templates"]] == ["general"]
    one, _ = _call(svc.template, ws, "general")
    assert [c["id"] for c in one["classes"]][:2] == ["ACA", "WP"]
    assert any(p["id"] == "health" for p in one["notation_presets"])
    assert _refused(svc.template, ws, "nope").status == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_new_project_service.py`
Expected: FAIL (`ModuleNotFoundError: claimstone.new_project_service`).

- [ ] **Step 3: Implement** `claimstone/new_project_service.py`

```python
"""The operations behind the control server's new-project routes.

Pure with respect to HTTP: every function takes the directories, the operator id and the code
revision, and returns `(payload, status)` or raises `ServiceError`. Nothing here starts a stage, a
network request or a model call; it only reads drafts, validates, previews and creates a directory.
"""

from __future__ import annotations

import datetime as _dt
import pathlib
from typing import Any

from claimstone import project_builder as pb
from claimstone import wizard_drafts as wd


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str,
                 details: list[dict[str, str]] | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def _today() -> str:
    return _dt.date.today().isoformat()


def _guard(fn):
    """Map the builder's and the ledger's refusals onto one error."""
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except pb.DraftInvalid as exc:
            raise ServiceError(422, "VALIDATION", str(exc),
                               [{"path": p.path, "message": p.message} for p in exc.problems]) from None
        except pb.ProjectExists as exc:
            raise ServiceError(409, "NAME_TAKEN", f"a project named {exc} already exists") from None
        except pb.RoundTripMismatch as exc:
            raise ServiceError(409, "ROUND_TRIP", str(exc)) from None
        except wd.DraftRefused as exc:
            raise ServiceError(exc.status, exc.code, exc.message) from None
    wrapped.__name__ = fn.__name__
    return wrapped


def _step_figures(step: int, data: dict[str, Any]) -> dict[str, Any]:
    if step == 1:
        terms = sum(len(t["terms"]) for t in data["topics"])
        return {"topics": len(data["topics"]), "terms": terms, "searches_per_index": terms,
                "searches_all_indexes": terms * len(pb.SEARCH_INDEXES)}
    if step == 2:
        kinds: dict[str, int] = {}
        for q in data["questions"]:
            kinds[q["kind"]] = kinds.get(q["kind"], 0) + 1
        operational = kinds.get("operational", 0)
        return {"questions_total": len(data["questions"]),
                "questions_literature": len(data["questions"]) - operational,
                "questions_operational": operational, "questions_by_kind": kinds}
    return {"classes": data["classes"], "acquisition_floor": data["acquisition_floor"],
            "supplied_copies": data["supplied_copies"],
            "excluded_hosts_added": len(data["extra_excluded_hosts"])}


def _store(store_dir):
    return wd.open_store(store_dir)


def _templates_dir(projects_dir):
    return pb.template_dir(projects_dir)


@_guard
def templates(projects_dir, store_dir, actor, code_revision):
    return {"templates": pb.list_templates(_templates_dir(projects_dir))}, 200


@_guard
def template(projects_dir, store_dir, actor, code_revision, template_id):
    try:
        raw = pb.load_template(_templates_dir(projects_dir), template_id)
    except pb.DraftInvalid:
        raise ServiceError(404, "NOT_FOUND", "no such template") from None
    return {"id": raw["id"], "label": raw["label"], "default_floor": raw["default_floor"],
            "classes": [{"id": c["id"], "name": c["name"], "weight_hint": c["weight_hint"],
                         "notes": c.get("notes", "")} for c in raw["classes"]],
            "excluded_hosts": list(raw["excluded_hosts"]),
            "notation_presets": [{"id": p["id"], "label": p["label"]} for p in raw["notation_presets"]]}, 200


@_guard
def start(projects_dir, store_dir, actor, code_revision):
    row = wd.start(_store(store_dir), actor=actor, code_revision=code_revision)
    return {"draft_id": row["draft_id"], "revision": row["revision"]}, 201


@_guard
def list_drafts(projects_dir, store_dir, actor, code_revision):
    return {"drafts": wd.list_drafts(_store(store_dir), actor)}, 200


@_guard
def read(projects_dir, store_dir, actor, code_revision, draft_id):
    current = wd.state(_store(store_dir), draft_id, actor)
    current["steps"] = {str(k): v for k, v in current["steps"].items()}
    # What the explanation panel quotes for each saved step, so a resumed draft shows its figures.
    current["figures"] = {n: _step_figures(int(n), v["data"]) for n, v in current["steps"].items()}
    return current, 200


@_guard
def save_step(projects_dir, store_dir, actor, code_revision, draft_id, step, base_revision, data):
    if step not in (1, 2, 3):
        raise ServiceError(404, "NOT_FOUND", "no such step")
    normalized = pb.normalize_step(step, data, _templates_dir(projects_dir))
    if step == 1 and (pathlib.Path(projects_dir) / normalized["name"]).exists():
        raise pb.DraftInvalid([pb.Problem("name", "a project with this name already exists")])
    row = wd.save_step(_store(store_dir), actor=actor, draft_id=draft_id, step=step,
                       base_revision=base_revision, data=normalized, code_revision=code_revision)
    return {"revision": row["revision"], "data": normalized,
            "figures": _step_figures(step, normalized)}, 200


def _files_and_info(projects_dir, current: dict[str, Any]):
    state = {int(n): v["data"] for n, v in current["steps"].items()}
    files = pb.render(state, _templates_dir(projects_dir), today=_today(),
                      overrides=current["advanced"] or None)
    info = pb.inspect(files, name=state[1]["name"], templates_dir=_templates_dir(projects_dir),
                      template_id=state[3]["template"])
    return state, files, info


@_guard
def save_advanced(projects_dir, store_dir, actor, code_revision, draft_id, base_revision, files):
    store = _store(store_dir)
    current = wd.state(store, draft_id, actor)
    candidate = {**current, "advanced": files}
    if files:
        _files_and_info(projects_dir, candidate)  # raises DraftInvalid when it would not load
    row = wd.save_advanced(store, actor=actor, draft_id=draft_id, base_revision=base_revision,
                           files=files, code_revision=code_revision)
    return {"revision": row["revision"]}, 200


@_guard
def preview(projects_dir, store_dir, actor, code_revision, draft_id):
    current = wd.state(_store(store_dir), draft_id, actor)
    if current["status"] != "open":
        raise ServiceError(409, "DRAFT_CLOSED", f"this draft is {current['status']}")
    _state, files, info = _files_and_info(projects_dir, current)
    return {"figures": info["figures"], "protocol_sha256": info["protocol_sha256"],
            "files": files, "revision": current["revision"]}, 200


@_guard
def discard(projects_dir, store_dir, actor, code_revision, draft_id, base_revision):
    row = wd.discard(_store(store_dir), actor=actor, draft_id=draft_id,
                     base_revision=base_revision, code_revision=code_revision)
    return {"revision": row["revision"], "status": "discarded"}, 200


@_guard
def create(projects_dir, store_dir, actor, code_revision, draft_id, confirm):
    if confirm is not True:
        raise ServiceError(422, "VALIDATION", "confirm must be the literal true")
    store = _store(store_dir)
    current = wd.state(store, draft_id, actor)
    if current["status"] != "open":
        raise ServiceError(409, "DRAFT_CLOSED", f"this draft is {current['status']}")
    state, files, info = _files_and_info(projects_dir, current)
    name = state[1]["name"]
    try:
        made = pb.create_project(projects_dir, name, files,
                                 expected_protocol_sha256=info["protocol_sha256"], lock_store=store)
    except (pb.DraftInvalid, pb.ProjectExists, pb.RoundTripMismatch) as exc:
        wd.mark_failed(store, actor=actor, draft_id=draft_id, reason=str(exc) or type(exc).__name__,
                       code_revision=code_revision)
        raise
    wd.mark_created(store, actor=actor, draft_id=draft_id, project=name, files=made["files"],
                    code_revision=code_revision)
    return {"project": name, "protocol_sha256": made["protocol_sha256"], "files": made["files"],
            "frozen": {"registry_version": 1, "frozen_at": _today(), "floor_version": 1}}, 201
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest -q tests/test_new_project_service.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add claimstone/new_project_service.py tests/test_new_project_service.py
git commit -m "wizard: the service layer joining builder and drafts

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 8: Control routes

`ControlError` gains optional `details` (field paths for a 422); nine routes are registered; the handlers are thin.

**Files:**
- Modify: `claimstone/control.py` (imports; `ControlError`; `_error`; `_answer_exception`; `ROUTES`; handlers appended before the "the server" section)
- Test: `tests/test_control_new_project.py`

- [ ] **Step 1: Write the failing tests** `tests/test_control_new_project.py`

```python
"""The new-project routes: sessions, CSRF, validation paths, idempotency, and no write to any
existing project."""

from __future__ import annotations

import hashlib
import pathlib
import shutil
import threading
import uuid
from contextlib import contextmanager

import pytest

from claimstone import control, operators
from tests.test_control import _cookie, _login, _request

REPO = pathlib.Path(__file__).resolve().parents[1]

STEP1 = {"name": "news-tone", "description": "scope", "topics": [{"label": "News", "terms": ["a b", "c d"]}]}
STEP2 = {"questions": [{"text": "Does news carry information?", "kind": "effect"},
                       {"text": "Which datasets exist?", "kind": "operational"}]}
STEP3 = {"template": "general", "classes": ["ACA"], "acquisition_floor": 0.8,
         "floor_rationale": "Set before the first measured round; below it coverage is uninterpretable.",
         "supplied_copies": "separate", "notation": "none", "custom_value_labels": [],
         "extra_excluded_hosts": []}


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / "projects").mkdir()
    shutil.copytree(REPO / "projects" / "example-news-and-returns",
                    tmp_path / "projects" / "example-news-and-returns")
    shutil.copytree(REPO / "templates", tmp_path / "templates")
    state = tmp_path / "state"
    operators.add_operator(state, "op1", "Op One", "correct horse")
    operators.add_operator(state, "op2", "Op Two", "battery staple")
    return {"root": tmp_path, "projects": tmp_path / "projects", "store": tmp_path / "store",
            "state": state}


@contextmanager
def _served(ws):
    httpd = control.make_server(ws["projects"], ws["store"], host="127.0.0.1", port=0,
                                state_dir=ws["state"])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


class Client:
    def __init__(self, base, operator_id="op1", password="correct horse"):
        self.base = base
        status, headers, body = _login(base, operator_id, password)
        assert status == 200, body
        self.cookie, self.csrf = _cookie(headers), body["csrf_token"]

    def post(self, path, payload, key=None):
        sent = {"Cookie": self.cookie, "Origin": self.base, "X-CSRF-Token": self.csrf}
        if key:
            sent["Idempotency-Key"] = key
        return _request(f"{self.base}/control/v1{path}", method="POST", payload=payload, headers=sent)

    def get(self, path):
        return _request(f"{self.base}/control/v1{path}", headers={"Cookie": self.cookie})


def _tree(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _fill(client):
    _, _, started = client.post("/new", {})
    draft, rev = started["draft_id"], started["revision"]
    for step, data in ((1, STEP1), (2, STEP2), (3, STEP3)):
        status, _h, body = client.post(f"/new/{draft}/steps/{step}", {"base_revision": rev, "data": data})
        assert status == 200, body
        rev = body["revision"]
    return draft, rev


def test_every_new_project_route_refuses_an_anonymous_request(ws):
    with _served(ws) as base:
        for method, path in (("GET", "/new"), ("GET", "/new-templates"), ("GET", "/new/abc"),
                             ("GET", "/new/abc/preview")):
            assert _request(base + "/control/v1" + path)[0] == 401, path
        for path in ("/new", "/new/abc/steps/1", "/new/abc/advanced", "/new/abc/discard",
                     "/new/abc/create"):
            sent = {"Origin": base}
            assert _request(base + "/control/v1" + path, method="POST", payload={}, headers=sent)[0] == 401, path


def test_the_whole_wizard_creates_a_project_that_validates(ws):
    with _served(ws) as base:
        client = Client(base)
        draft, _rev = _fill(client)
        status, _h, preview = client.get(f"/new/{draft}/preview")
        assert status == 200 and preview["figures"]["questions_literature"] == 1
        status, _h, made = client.post(f"/new/{draft}/create", {"confirm": True}, key=str(uuid.uuid4()))
    assert status == 201 and made["project"] == "news-tone"
    from claimstone.config import load_project
    assert load_project(ws["projects"] / "news-tone").registry_version == 1


def test_create_is_idempotent_for_one_key(ws):
    with _served(ws) as base:
        client = Client(base)
        draft, _ = _fill(client)
        key = str(uuid.uuid4())
        first = client.post(f"/new/{draft}/create", {"confirm": True}, key=key)
        again = client.post(f"/new/{draft}/create", {"confirm": True}, key=key)
    assert first[0] == again[0] == 201 and first[2] == again[2]


def test_a_validation_error_carries_field_paths(ws):
    with _served(ws) as base:
        client = Client(base)
        _, _, started = client.post("/new", {})
        status, _h, body = client.post(f"/new/{started['draft_id']}/steps/1",
                                       {"base_revision": 1, "data": {**STEP1, "name": "Bad Name"}})
    assert status == 422 and body["error"]["code"] == "VALIDATION"
    assert body["error"]["details"][0]["path"] == "name"


def test_a_stale_revision_is_409(ws):
    with _served(ws) as base:
        client = Client(base)
        _, _, started = client.post("/new", {})
        draft = started["draft_id"]
        assert client.post(f"/new/{draft}/steps/1", {"base_revision": 1, "data": STEP1})[0] == 200
        status, _h, body = client.post(f"/new/{draft}/steps/1", {"base_revision": 1, "data": STEP1})
    assert (status, body["error"]["code"]) == (409, "STALE_REVISION")


def test_another_operators_draft_is_a_404(ws):
    with _served(ws) as base:
        mine, theirs = Client(base), Client(base, "op2", "battery staple")
        _, _, started = mine.post("/new", {})
        assert theirs.get(f"/new/{started['draft_id']}")[0] == 404
        assert theirs.get("/new")[2]["drafts"] == []


def test_unknown_keys_and_bad_bodies_are_400(ws):
    with _served(ws) as base:
        client = Client(base)
        _, _, started = client.post("/new", {})
        draft = started["draft_id"]
        assert client.post(f"/new/{draft}/steps/1", {"base_revision": 1, "data": STEP1, "x": 1})[0] == 400
        assert client.post(f"/new/{draft}/steps/1", {"base_revision": "1", "data": STEP1})[0] == 422
        assert client.post(f"/new/{draft}/steps/9", {"base_revision": 1, "data": {}})[0] == 404
        assert client.post(f"/new/{draft}/create", {"confirm": "yes"})[0] == 422


def test_no_route_changes_an_existing_project(ws):
    before = _tree(ws["projects"] / "example-news-and-returns")
    with _served(ws) as base:
        client = Client(base)
        draft, rev = _fill(client)
        client.post(f"/new/{draft}/advanced", {"base_revision": rev, "files": {}})
        client.get(f"/new/{draft}/preview")
        client.post(f"/new/{draft}/create", {"confirm": True})
        # a second draft aiming at the existing name is refused and still changes nothing
        _, _, second = client.post("/new", {})
        client.post(f"/new/{second['draft_id']}/steps/1",
                    {"base_revision": 1, "data": {**STEP1, "name": "example-news-and-returns"}})
    assert _tree(ws["projects"] / "example-news-and-returns") == before


def test_templates_are_served(ws):
    with _served(ws) as base:
        client = Client(base)
        assert [t["id"] for t in client.get("/new-templates")[2]["templates"]] == ["general"]
        assert client.get("/new-templates/general")[2]["default_floor"] == 0.8
        assert client.get("/new-templates/nope")[0] == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_control_new_project.py`
Expected: FAIL (404 on `/new`, or `AttributeError`).

- [ ] **Step 3: Implement in `claimstone/control.py`**

3a. Imports — change the `from claimstone import (...)` block to add `new_project_service`:

```python
from claimstone import (admin, decisions, drafts, export, flows, intake, new_project_service,
                        operations, operations_view, operators, portal_state, scope, synthesize,
                        today)
```

3b. `ControlError` — replace the class with:

```python
class ControlError(Exception):
    """A route's named answer: the status, the envelope code and the message. `details` is an
    optional list of `{path, message}` for a 422 that names form fields."""

    def __init__(self, status: int, code: str, message: str,
                 details: list[dict[str, str]] | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details
```

3c. `_error` — replace with:

```python
    def _error(self, code: int, name: str, message: str,
               cookies: tuple[str, ...] = (), details: list[dict[str, str]] | None = None) -> None:
        envelope: dict[str, Any] = {"code": name, "message": message}
        if details:
            envelope["details"] = details
        self._json({"error": envelope}, code=code, cookies=cookies)
```

and in `_answer_exception`, change the `ControlError` branch to:

```python
        if isinstance(exc, ControlError):
            self._error(exc.status, exc.code, exc.message, details=exc.details)
```

3d. Routes — add before the closing `)` of `ROUTES`:

```python
    # New project: drafts, preview and creation. Nothing here starts a stage or any request; the
    # only write outside `store/` is `project_builder.create_project`, which creates one directory.
    Route("POST", ("new",), "_new_start"),
    Route("GET", ("new",), "_new_list"),
    Route("GET", ("new-templates",), "_new_templates"),
    Route("GET", ("new-templates", "{template_id}"), "_new_template"),
    Route("GET", ("new", "{draft_id}"), "_new_read"),
    Route("POST", ("new", "{draft_id}", "steps", "{step}"), "_new_step"),
    Route("POST", ("new", "{draft_id}", "advanced"), "_new_advanced"),
    Route("GET", ("new", "{draft_id}", "preview"), "_new_preview"),
    Route("POST", ("new", "{draft_id}", "discard"), "_new_discard"),
    Route("POST", ("new", "{draft_id}", "create"), "_new_create"),
```

3e. Handlers — insert before the `# --- the server ---` comment line:

```python
# --- new project ----------------------------------------------------------------------------------


def _revision(body: dict[str, Any]) -> int:
    value = body.get("base_revision")
    if type(value) is not int or value < 1:
        raise ControlError(422, "VALIDATION", "base_revision must be the draft's current revision")
    return value


def _new_call(self: _Handler, function: Callable[..., Any], *args: Any) -> tuple[Any, int]:
    session = self._require_session()
    try:
        return function(self.projects_dir, self.store_dir, session.operator_id,
                        self.code_revision, *args)
    except new_project_service.ServiceError as exc:
        raise ControlError(exc.status, exc.code, exc.message, exc.details) from None


def _new_start(self: _Handler, params: dict[str, str], query: Any,
               body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset())
    return _new_call(self, new_project_service.start)


def _new_list(self: _Handler, params: dict[str, str], query: Any,
              body: dict[str, Any]) -> tuple[Any, int]:
    return _new_call(self, new_project_service.list_drafts)


def _new_templates(self: _Handler, params: dict[str, str], query: Any,
                   body: dict[str, Any]) -> tuple[Any, int]:
    return _new_call(self, new_project_service.templates)


def _new_template(self: _Handler, params: dict[str, str], query: Any,
                  body: dict[str, Any]) -> tuple[Any, int]:
    return _new_call(self, new_project_service.template, params["template_id"])


def _new_read(self: _Handler, params: dict[str, str], query: Any,
              body: dict[str, Any]) -> tuple[Any, int]:
    return _new_call(self, new_project_service.read, params["draft_id"])


def _new_step(self: _Handler, params: dict[str, str], query: Any,
              body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"base_revision", "data"}))
    if not params["step"].isdigit():
        raise ControlError(404, "NOT_FOUND", "no such step")
    return _new_call(self, new_project_service.save_step, params["draft_id"],
                     int(params["step"]), _revision(body), body.get("data"))


def _new_advanced(self: _Handler, params: dict[str, str], query: Any,
                  body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"base_revision", "files"}))
    files = body.get("files")
    if not isinstance(files, dict) or any(not isinstance(v, str) for v in files.values()):
        raise ControlError(422, "VALIDATION", "files must map a file name to its text")
    return _new_call(self, new_project_service.save_advanced, params["draft_id"],
                     _revision(body), files)


def _new_preview(self: _Handler, params: dict[str, str], query: Any,
                 body: dict[str, Any]) -> tuple[Any, int]:
    return _new_call(self, new_project_service.preview, params["draft_id"])


def _new_discard(self: _Handler, params: dict[str, str], query: Any,
                 body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"base_revision"}))
    return _new_call(self, new_project_service.discard, params["draft_id"], _revision(body))


def _new_create(self: _Handler, params: dict[str, str], query: Any,
                body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"confirm"}))
    return _new_call(self, new_project_service.create, params["draft_id"], body.get("confirm"))


for _name, _function in (("_new_start", _new_start), ("_new_list", _new_list),
                         ("_new_templates", _new_templates), ("_new_template", _new_template),
                         ("_new_read", _new_read), ("_new_step", _new_step),
                         ("_new_advanced", _new_advanced), ("_new_preview", _new_preview),
                         ("_new_discard", _new_discard), ("_new_create", _new_create)):
    setattr(_Handler, _name, _function)
```

- [ ] **Step 4: Run to verify pass, and the whole control suite**

Run: `.venv/bin/pytest -q tests/test_control_new_project.py tests/test_control.py tests/test_control_signing.py`
Expected: all pass. (`test_every_post_route_refuses_an_anonymous_request` in `test_control.py` now also enumerates the five new POST routes.)

- [ ] **Step 5: Commit**

```bash
git add claimstone/control.py tests/test_control_new_project.py
git commit -m "control: new-project routes (drafts, preview, create)

ControlError gains optional field-path details for a 422; nine routes are
registered, so the anonymous-access sweep covers them.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 9: Mounts, contract, decision, full verification

**Files:**
- Modify: `compose.yaml` (service `control`, `volumes`), `tests/test_compose.py:181`
- Create: `docs/contracts/new_project.md`
- Modify: `docs/contracts/control_api.md`, `docs/DESIGN_DECISIONS.md`, `docs/README.md`

- [ ] **Step 1: Update the compose test first** — in `tests/test_compose.py` line 181, change the control volumes assertion so it expects the writable `projects` mount and the templates mount. Run `sed -n 178,184p tests/test_compose.py` to see the exact set, then replace `"./projects:/app/projects:ro"` with `"./projects:/app/projects"` and add `"./templates:/app/templates:ro"` to that set.

Run: `.venv/bin/pytest -q tests/test_compose.py`
Expected: FAIL on the control volumes assertion.

- [ ] **Step 2: Change `compose.yaml`** — in the `control` service replace the `volumes` block with:

```yaml
    volumes:
      - ./store:/app/store
      # Writable, for one reason: `claimstone/project_builder.py` creates a NEW directory here when an
      # operator confirms the new-project wizard. It never opens a file of an existing project for
      # writing (tests/test_control_new_project.py hashes the tree before and after).
      - ./projects:/app/projects
      - ./templates:/app/templates:ro
      - ./.claimstone:/app/.claimstone
```

Run: `.venv/bin/pytest -q tests/test_compose.py`
Expected: pass.

- [ ] **Step 3: Write `docs/contracts/new_project.md`**

```markdown
# `wizard_drafts.jsonl` and the new-project routes — the contract

**Written by:** the control server (`new_project_service`, via `POST /control/v1/new…`). **Read by:** the
same routes, for the operator who started the draft. **Never read by** any stage, profile, verdict or
export. Spec: `docs/superpowers/specs/2026-10-10-new-project-wizard-design.md`. Decision: D125.

A draft is what an operator typed before a project existed. The ledger lives in
`store/_new-projects/wizard_drafts.jsonl` and is append-only; a draft's state is replayed from its rows.

| field | meaning |
|---|---|
| `wizard_version` | `1` |
| `event` | `started`, `step_saved`, `advanced_saved`, `discarded`, `created`, `create_failed` |
| `draft_id` | random 128-bit hex, generated by the server |
| `revision` | 1 for `started`, +1 per row; a save must name the current revision |
| `step` | 1–3 for `step_saved`, else null |
| `data` | the step's normalized content; for `advanced_saved` a map file → text; for `created` the file hashes |
| `project` | the project name once created, else null |
| `note` | the reason, for `create_failed` |
| `actor`, `signer_auth`, `code_revision`, `recorded_at` | as in every control ledger |

## Routes (`/control/v1`, every rule of `control_api.md` applies)

| route | answer |
|---|---|
| `POST /new` | 201 `{draft_id, revision}` |
| `GET /new` | `{drafts: [...]}`, the operator's own |
| `GET /new/{id}` | the replayed state plus `figures` per saved step; another operator's id is 404 |
| `POST /new/{id}/steps/{1-3}` `{base_revision, data}` | 200 `{revision, data, figures}`; 422 with `details: [{path, message}]` and nothing written; 409 `STALE_REVISION`, `DRAFT_CLOSED` |
| `POST /new/{id}/advanced` `{base_revision, files}` | 200 `{revision}`; the files must still load; `{}` clears |
| `GET /new/{id}/preview` | `{figures, protocol_sha256, files, revision}`; needs steps 1–3 |
| `POST /new/{id}/discard` `{base_revision}` | 200 |
| `POST /new/{id}/create` `{confirm: true}` | 201 `{project, protocol_sha256, files, frozen}`; 409 `NAME_TAKEN`, `ROUND_TRIP`, `DRAFT_CLOSED` |
| `GET /new-templates`, `GET /new-templates/{id}` | the data templates (`templates/project/*.yaml`) |

## What creation does, and does not do

It validates the whole draft with the loaders `claimstone validate` uses; writes
`projects/.incoming-<random>/`; loads it; requires the protocol digest to equal the preview's; renames it to
`projects/<name>/`. Registry `registry_version: 1` and floor `floor_version: 1` carry the creation date. It
**does not** bind a flow, open a round, authorize or start a search, a fetch or a model call: those are stage 2.

## Figures

Every figure in `figures` derives from the loaded project. Unknown is `null` (`requests_max`) and renders "—".
Searches per index equal the topic terms, the rule of `operations.plan_batch`; the search indexes are chosen
when a plan is frozen (`discover --api`), not in the project files.
```

- [ ] **Step 4: Update `control_api.md`** — in the "Routes" section header list add, after B12:

```markdown
### New project — drafts and creation

See `docs/contracts/new_project.md`. These routes keep a private draft ledger and, on confirmation, create
one new directory under `projects/` through `project_builder.create_project`, the only code that writes
there. The `control` service therefore mounts `projects/` read-write; it still never runs a stage and never
starts network or paid work.
```

and in "What the control server never does", after the bullet "It never decides scientific policy…", append: "The new-project wizard records the policy the operator declares; the server checks it against the engine's loaders and decides none of it."

- [ ] **Step 5: Add decision D125** — append to `docs/DESIGN_DECISIONS.md`:

```markdown
## D125 — A project can be created from the portal, as a draft and then one atomic write (2026-10-10)

Projects were three hand-written files. The wizard lets an authenticated operator build a **draft**,
step by step, and create a frozen project (registry v1, floor v1, both dated) on confirmation. Decided with
the operator on 2026-10-10:

- A step save is a draft only. Nothing exists under `projects/` until the final confirmation, so a half
  project is impossible and the registry is never written before it is frozen (invariant 5).
- The control server creates the project through `project_builder.create_project`, which creates a new
  directory and never opens an existing project's file for writing. Measured by
  `tests/test_control_new_project.py::test_no_route_changes_an_existing_project`, which hashes every file of
  an existing project before and after a full wizard run. The `control` service's `projects/` mount changes
  from read-only to read-write for this reason alone. A separate builder service and a host-side command
  were weighed and set aside (one more service for a once-per-project write; the last step leaving the
  interface).
- Conventions of a field (source classes, notation, excluded hosts) are **data** in `templates/project/`, so
  the engine stays free of domain knowledge (invariant 4). The staging directory is `projects/.incoming-*`;
  `discover_projects` ignores names starting with a dot.
- The wizard refuses nothing a loader accepts except an empty question `kind`, and judges no wording:
  a vague question is not detected, because that would be a semantic judgement the engine does not make.
- A description is kept in `topics.yaml` under a key the loader does not read; the protocol digest ignores
  it (`test_a_description_does_not_change_the_protocol_digest`).
- Not built here, by design: flow binding, opening a round, any search, copy or model call (stage 2).
```

and in `docs/README.md`, in the contracts table, add the row:

```markdown
| [`contracts/new_project.md`](contracts/new_project.md) | the new-project wizard's drafts and routes |
```

- [ ] **Step 6: Full verification**

Run:

```bash
.venv/bin/pytest -q
.venv/bin/claimstone validate --all-projects
git status --short
```

Expected: the whole suite passes; `validate --all-projects` reports every project OK; no stray `projects/.incoming-*`.

- [ ] **Step 7: Commit**

```bash
git add compose.yaml tests/test_compose.py docs/contracts/new_project.md docs/contracts/control_api.md docs/DESIGN_DECISIONS.md docs/README.md
git commit -m "docs, compose: the new-project contract, the control mounts, D125

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

## Self-review (spec coverage)

| Spec requirement | Task |
|---|---|
| Drafts per step, nothing in `projects/` until confirmation | 6, 7, 8 |
| Server validates with the engine's loaders; round trip with equal digest | 4, 5 |
| Atomic creation, never touch an existing project, staging not discoverable | 1, 5, 8 (hash test) |
| Templates as data; excluded hosts cannot shrink; notation presets | 2, 3, 4 |
| Figures computed offline by the server; unknown is null | 4, 7 |
| Routes with session, CSRF, origin, size, unknown keys, idempotency | 8 (existing mechanisms + tests) |
| Registry v1 and floor v1 dated; rationale required; no override | 3, 4, 7 |
| `description` ignored by the protocol digest | 4 |
| Contract, mounts, decision | 9 |
| Corrections found while checking the spec | 0 |

Frontend (steps UI, i18n, explanation panel, Shell button, guides, live check) is plan 2.
