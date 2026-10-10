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


def _identifier(value: Any, default: str, path: str, problems: list[Problem]) -> str:
    """An id as typed, or the default when absent or empty. A non-text id is never coerced."""
    if value is None:
        return default
    if not isinstance(value, str):
        problems.append(Problem(path, "must be text"))
        return default
    return value.strip() or default


def _object(data: Any, allowed: set[str], problems: list[Problem]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise DraftInvalid([Problem("", "step data must be an object")])
    for key in sorted(set(data) - allowed):
        problems.append(Problem(key, "is not a field of this step"))
    return data


def normalize_step(step: int, data: Any, templates_dir: str | pathlib.Path) -> dict[str, Any]:
    """The step's content as the ledger stores it, or `DraftInvalid` naming every problem."""
    problems: list[Problem] = []
    if type(step) is not int:
        raise DraftInvalid([Problem("step", "steps are 1 to 3")])
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
        topic_id = _identifier(entry.get("id"), f"T{i + 1:02d}", f"{base}.id", problems)
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
        qid = _identifier(entry.get("id"), f"Q{i + 1:02d}", f"{base}.id", problems)
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
    try:
        floor_ok = not isinstance(floor, bool) and isinstance(floor, (int, float)) and 0 < float(floor) <= 1
    except (OverflowError, ValueError):
        floor_ok = False
    if not floor_ok:
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
    if not isinstance(notation, str):
        problems.append(Problem("notation", "must be text"))
        notation = ""
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


def _require_fresh_protocol(project: Any, today: str) -> None:
    def refuse(path: str, message: str) -> None:
        raise DraftInvalid([Problem(path, message)])

    if project.registry_version != 1:
        refuse("questions.yaml", "a new project is frozen at registry version 1; later versions "
                                 "are dated bumps of an existing registry")
    if project.frozen_at != today:
        refuse("questions.yaml", f"a new project is frozen today ({today}), so frozen_at must be "
                                 "today's date")
    if project.floor_version != 1:
        refuse("sources.yaml", "a new project's acquisition floor is at floor version 1; later "
                               "versions are dated changes of an existing floor")
    if project.floor_set_at != today:
        refuse("sources.yaml", f"the floor is set today ({today}), so floor_set_at must be today's date")
    if len(project.floor_rationale.strip()) < MIN_FLOOR_RATIONALE:
        refuse("sources.yaml", f"a floor needs a floor_rationale of at least {MIN_FLOOR_RATIONALE} "
                               "characters: a bar without a reason is arbitrary")
    if project.supplied_copies_declared is not True:
        refuse("sources.yaml", "supplied_copies must be declared (count or separate): it decides "
                               "whether copies an operator supplies count toward the floor")
    for question in project.questions:
        if question.kind not in QUESTION_KINDS:
            refuse("questions.yaml", f"question {question.id} needs a kind, one of "
                                     + ", ".join(QUESTION_KINDS) + ": the kind decides which rule judges it")


def _require_files(files: Any) -> None:
    if not isinstance(files, dict) or set(files) != set(FILES):
        raise DraftInvalid([Problem("files", "need exactly " + ", ".join(FILES))])
    for filename in FILES:
        if not isinstance(files[filename], str):
            raise DraftInvalid([Problem("files", f"{filename} must be text")])


def inspect(files: dict[str, str], *, name: str, templates_dir: str | pathlib.Path,
            template_id: str, today: str) -> dict[str, Any]:
    """Load the files with the real loader and derive the figures. Raises `DraftInvalid`.

    A new project is protocol v1, frozen `today`; an advanced override that says otherwise is refused."""
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise DraftInvalid([Problem("name", "not a valid project name")])
    _require_files(files)
    template = load_template(templates_dir, template_id)
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / name
        root.mkdir()
        for filename, text in files.items():
            (root / filename).write_text(text, encoding="utf-8")
        try:
            project = load_project(root)
            _require_fresh_protocol(project, today)
            lost = sorted(set(template["excluded_hosts"]) - set(project.excluded_hosts))
            if lost:
                raise DraftInvalid([Problem("sources.yaml", "the template's excluded hosts cannot "
                                            "be removed: " + ", ".join(lost))])
            return {"figures": figures(project), "protocol_sha256": flows.protocol_digest(project)}
        except ConfigError as exc:
            raise DraftInvalid([Problem(_file_of(str(exc)), str(exc))]) from exc
        except RecursionError as exc:
            raise DraftInvalid([Problem("files", "a file is nested too deeply to read")]) from exc


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
    _require_files(files)
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
            except RecursionError as exc:
                raise DraftInvalid([Problem("files", "a file is nested too deeply to read")]) from exc
            if loaded != expected_protocol_sha256:
                raise RoundTripMismatch(f"files carry {loaded}, the preview promised "
                                        f"{expected_protocol_sha256}")
            os.rename(staging, final)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    return {"project": name, "protocol_sha256": loaded,
            "files": {filename: sha256_text(files[filename]) for filename in FILES}}
