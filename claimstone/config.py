"""Loading and validating a project's three input files.

A project is defined by data, never by code: `topics.yaml` says what to look for,
`questions.yaml` says what counts as a result, `sources.yaml` says what is admissible.
This module is the only place that knows their shape, and it fails loudly — a malformed
registry that loads anyway would silently invalidate every coverage figure downstream.
"""

from __future__ import annotations

import datetime as _dt
import pathlib
from dataclasses import dataclass, field
from typing import Any

import yaml

VERDICTS = ("SUPPORTED", "CONTRADICTED", "UNANSWERED_IN_LITERATURE", "NEVER_ASKED")
STANCES = ("SUPPORTS", "CONTRADICTS", "QUALIFIES", "METHOD_ONLY")
REVIEW_VERDICTS = ("SUPPORTED", "OVERSTATED", "AMBIGUOUS", "NOT_APPLICABLE")


class ConfigError(Exception):
    """A project's input files do not satisfy the contract."""


@dataclass(frozen=True)
class SourceClass:
    id: str
    name: str
    weight_hint: str
    notes: str = ""
    # What a manifest written elsewhere may call this class. Declared, never inferred: the
    # engine guessing that "academic" means ACA would misclassify a source the moment the two
    # stop lining up, and invariant 6 exists to prevent exactly that.
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Topic:
    id: str
    label: str
    terms: tuple[str, ...]


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    added: str | None = None


@dataclass(frozen=True)
class ManifestEntry:
    source_id: str
    source_class: str
    declared_format: str
    url: str
    title: str


@dataclass(frozen=True)
class Project:
    name: str
    root: pathlib.Path
    classes: tuple[SourceClass, ...]
    acquisition_floor: float
    excluded_hosts: tuple[str, ...]
    topics: tuple[Topic, ...]
    questions: tuple[Question, ...]
    registry_version: int
    frozen_at: str
    manifest: tuple[ManifestEntry, ...] = ()
    gate_thresholds: dict[str, int] = field(default_factory=dict)

    @property
    def question_ids(self) -> frozenset[str]:
        return frozenset(q.id for q in self.questions)

    @property
    def class_ids(self) -> frozenset[str]:
        return frozenset(c.id for c in self.classes)


def _read_yaml(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"missing required file: {path}")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path.name}: not valid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ConfigError(f"{path.name}: expected a mapping at the top level")
    return loaded


def _require_unique(ids: list[str], *, what: str, where: str) -> None:
    seen: set[str] = set()
    duplicates = sorted({i for i in ids if i in seen or seen.add(i)})  # type: ignore[func-returns-value]
    if duplicates:
        raise ConfigError(f"{where}: duplicate {what} id(s): {', '.join(duplicates)}")


def _require_str(value: Any, *, field: str, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: '{field}' must be a non-empty string")
    return value.strip()


def load_sources(root: pathlib.Path) -> tuple[tuple[SourceClass, ...], float, tuple[str, ...]]:
    raw = _read_yaml(root / "sources.yaml")
    entries = raw.get("classes")
    if not isinstance(entries, list) or not entries:
        raise ConfigError("sources.yaml: 'classes' must be a non-empty list")

    classes = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ConfigError("sources.yaml: each class must be a mapping")
        classes.append(
            SourceClass(
                id=_require_str(entry.get("id"), field="id", where="sources.yaml"),
                name=_require_str(entry.get("name"), field="name", where="sources.yaml"),
                weight_hint=_require_str(
                    entry.get("weight_hint"), field="weight_hint", where="sources.yaml"
                ),
                notes=str(entry.get("notes") or ""),
                aliases=tuple(
                    str(a).strip() for a in (entry.get("aliases") or []) if str(a).strip()
                ),
            )
        )
    _require_unique([c.id for c in classes], what="source class", where="sources.yaml")
    _require_unique(
        [a for c in classes for a in c.aliases], what="class alias", where="sources.yaml"
    )

    floor = raw.get("acquisition_floor")
    if not isinstance(floor, (int, float)) or isinstance(floor, bool) or not 0 < float(floor) <= 1:
        raise ConfigError(
            "sources.yaml: 'acquisition_floor' must be a number in (0, 1] — it gates whether "
            "a round may produce verdicts at all"
        )

    hosts = raw.get("excluded_hosts") or []
    if not isinstance(hosts, list) or any(not isinstance(h, str) for h in hosts):
        raise ConfigError("sources.yaml: 'excluded_hosts' must be a list of hostnames")

    return tuple(classes), float(floor), tuple(hosts)


def load_topics(root: pathlib.Path) -> tuple[Topic, ...]:
    raw = _read_yaml(root / "topics.yaml")
    entries = raw.get("topics")
    if not isinstance(entries, list) or not entries:
        raise ConfigError("topics.yaml: 'topics' must be a non-empty list")

    topics = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ConfigError("topics.yaml: each topic must be a mapping")
        terms = entry.get("terms")
        if not isinstance(terms, list) or not terms or any(not str(t).strip() for t in terms):
            raise ConfigError(
                f"topics.yaml: topic {entry.get('id')!r} needs a non-empty 'terms' list"
            )
        topics.append(
            Topic(
                id=_require_str(entry.get("id"), field="id", where="topics.yaml"),
                label=_require_str(entry.get("label"), field="label", where="topics.yaml"),
                terms=tuple(str(t).strip() for t in terms),
            )
        )
    _require_unique([t.id for t in topics], what="topic", where="topics.yaml")
    return tuple(topics)


def load_questions(root: pathlib.Path) -> tuple[tuple[Question, ...], int, str]:
    raw = _read_yaml(root / "questions.yaml")

    version = raw.get("registry_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ConfigError("questions.yaml: 'registry_version' must be an integer >= 1")

    frozen_at = raw.get("frozen_at")
    if isinstance(frozen_at, (_dt.date, _dt.datetime)):
        frozen_at = frozen_at.isoformat()[:10]
    else:
        frozen_at = _require_str(frozen_at, field="frozen_at", where="questions.yaml")
        try:
            _dt.date.fromisoformat(frozen_at)
        except ValueError as exc:
            raise ConfigError("questions.yaml: 'frozen_at' must be an ISO date") from exc

    entries = raw.get("questions")
    if not isinstance(entries, list) or not entries:
        raise ConfigError("questions.yaml: 'questions' must be a non-empty list")

    questions = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ConfigError("questions.yaml: each question must be a mapping")
        added = entry.get("added")
        if isinstance(added, (_dt.date, _dt.datetime)):
            added = added.isoformat()[:10]
        questions.append(
            Question(
                id=_require_str(entry.get("id"), field="id", where="questions.yaml"),
                text=_require_str(entry.get("text"), field="text", where="questions.yaml"),
                added=str(added) if added else None,
            )
        )
    _require_unique([q.id for q in questions], what="question", where="questions.yaml")
    return tuple(questions), version, frozen_at


MANIFEST_COLUMNS = ("source_id", "class", "format", "url", "title")
GATE_THRESHOLD_NAMES = ("min_pdf_bytes", "min_text_chars", "paywall_doubt_chars", "fulltext_chars")


def load_manifest(
    root: pathlib.Path, class_ids: frozenset[str], aliases: dict[str, str] | None = None
) -> tuple[ManifestEntry, ...]:
    """Load the optional curated source list. Absent is fine; malformed is not.

    Its purpose is to hold the source list constant across rounds: the milestone asks whether
    the acquisition rate moved on the manifest that produced 0.42, not whether a fresh search
    found easier papers.
    """
    import csv

    path = pathlib.Path(root) / "manifest.tsv"
    if not path.exists():
        return ()

    resolve_class = dict(aliases or {})
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
            if not any((source_id, klass, url, title)):
                # A trailing blank line is how a text file ends, not a row.
                continue
            if not source_id:
                raise ConfigError(f"manifest.tsv line {line_no}: 'source_id' is required")
            klass = resolve_class.get(klass, klass)
            if klass not in class_ids:
                known = sorted(class_ids | set(resolve_class))
                raise ConfigError(
                    f"manifest.tsv line {line_no}: class {klass!r} is not declared in "
                    f"sources.yaml, either as a class id or as an alias "
                    f"(known: {', '.join(known)})"
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


def load_gate_thresholds(root: pathlib.Path) -> dict[str, int]:
    """Per-project overrides for the content gate. Absent means the engine defaults.

    A misspelt key is an error rather than a silent no-op: a threshold the operator believed
    they had raised, and had not, produces a rate they would trust wrongly.
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


def load_project(root: str | pathlib.Path) -> Project:
    """Load and validate one project directory. Raises ConfigError on any violation."""
    path = pathlib.Path(root)
    if not path.is_dir():
        raise ConfigError(f"not a project directory: {path}")

    classes, floor, excluded = load_sources(path)
    topics = load_topics(path)
    questions, version, frozen_at = load_questions(path)
    manifest = load_manifest(
        path,
        frozenset(c.id for c in classes),
        {alias: c.id for c in classes for alias in c.aliases},
    )
    gate_thresholds = load_gate_thresholds(path)

    return Project(
        name=path.name,
        root=path,
        classes=classes,
        acquisition_floor=floor,
        excluded_hosts=excluded,
        topics=topics,
        questions=questions,
        registry_version=version,
        frozen_at=frozen_at,
        manifest=manifest,
        gate_thresholds=gate_thresholds,
    )


def discover_projects(projects_dir: str | pathlib.Path = "projects") -> list[pathlib.Path]:
    base = pathlib.Path(projects_dir)
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and (p / "questions.yaml").exists())
