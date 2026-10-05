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

VERDICTS = (
    "SUPPORTED",
    "CONTRADICTED",
    # Added 2026-09-25. With the effect rule, a question where the bar is cleared in both
    # directions is none of the other four, and calling it UNANSWERED would report silence while
    # the literature is speaking and disagreeing.
    "CONTESTED_IN_LITERATURE",
    "UNANSWERED_IN_LITERATURE",
    "NEVER_ASKED",
)

# What kind of thing a question asks, which decides the rule that judges it. `operational` asks
# about the consuming system's own architecture and receives no verdict: no paper can confirm that
# a versioned lane is the right design, and filing it under UNANSWERED_IN_LITERATURE would assert
# that the literature is silent on a question it was never asked.
QUESTION_KINDS = ("effect", "heterogeneity", "method", "premise", "operational")
STANCES = ("SUPPORTS", "CONTRADICTS", "QUALIFIES", "METHOD_ONLY")
REVIEW_VERDICTS = ("SUPPORTED", "OVERSTATED", "AMBIGUOUS", "NOT_APPLICABLE")


class ConfigError(Exception):
    """A project's input files do not satisfy the contract."""


class RegistryDrift(ConfigError):
    """The question registry changed without its version being bumped (invariant 5)."""


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
    # This class's role in synthesis. Declared, never read off the id: the method verdict rule
    # needs to know which sources are methodological, and inferring that from "MET" would put
    # domain knowledge back in the package (invariant 4).
    role: str = ""
    # The content gate's policy for sources of this class, overriding the project's. A corpus of
    # papers and regulatory filings cannot use one rule for both, and flipping the project-wide
    # switch to `structural_signal: none` was measured admitting four of six known summaries.
    gate_policy: dict[str, Any] = field(default_factory=dict)
    normalize_thresholds: dict[str, int] = field(default_factory=dict)
    # Conditions that assign a candidate to this class. Declared by the project, applied by the
    # engine: invariant 4 says the engine holds no domain knowledge, and "a journal is refereed"
    # is domain knowledge.
    assign_when: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # This class's own acquisition floor, which is an **additional** constraint and never a shortcut: the
    # project floor still applies to the whole, so a declared class floor can make admission harder or leave
    # it unchanged and can never let a round pass that the project floor refused.
    #
    # Measured, on alembic-s4: MET 0.83, ACA 0.70, IND 0.33 — because IND is commercial vendor research with
    # no open copy in existence. Obtainability is a property of the genre, and one floor over a manifest that
    # mixes refereed papers with vendor product research measures the proportions of the manifest.
    #
    # A rationale is required, on the same terms as the project floor: a bar without a reason is a bar
    # somebody moved.
    acquisition_floor: float | None = None
    floor_set_at: str = ""
    floor_rationale: str = ""


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
    kind: str = ""


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
    registry_sha256: str = ""
    manifest: tuple[ManifestEntry, ...] = ()
    gate_thresholds: dict[str, int] = field(default_factory=dict)
    gate_policy: dict[str, Any] = field(default_factory=dict)
    normalize_thresholds: dict[str, int] = field(default_factory=dict)
    # Vocabularies, not thresholds: which labels a figure may carry and which phrases compare. Empty means
    # the engine's generic defaults, and a project in another field declares its own (invariant 4).
    extraction: dict[str, Any] = field(default_factory=dict)
    citation_channel: dict[str, int] = field(default_factory=dict)
    floor_version: int = 1
    floor_set_at: str = ""
    floor_rationale: str = ""

    @property
    def question_ids(self) -> frozenset[str]:
        return frozenset(q.id for q in self.questions)

    @property
    def class_ids(self) -> frozenset[str]:
        return frozenset(c.id for c in self.classes)

    @property
    def population(self) -> dict[str, Any]:
        from claimstone import population
        try:
            return population.validate(_read_yaml(self.root / "sources.yaml").get("population"))
        except ValueError as exc:
            raise ConfigError(f"sources.yaml: {exc}") from exc


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

        class_floor = entry.get("acquisition_floor")
        if class_floor is not None:
            if (not isinstance(class_floor, (int, float)) or isinstance(class_floor, bool)
                    or not 0 < float(class_floor) <= 1):
                raise ConfigError(
                    f"sources.yaml class {entry.get('id')!r}: acquisition_floor must be a number in (0, 1]"
                )
            if not str(entry.get("floor_rationale") or "").strip():
                raise ConfigError(
                    f"sources.yaml class {entry.get('id')!r} declares acquisition_floor "
                    f"{class_floor} and no floor_rationale. A bar without a reason is a bar somebody "
                    f"moved; say why this genre's obtainability differs."
                )

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
                role=str(entry.get("role") or "").strip(),
                gate_policy=_gate_policy_fields(
                    entry.get("gate_policy") or {}, where=f"sources.yaml class {entry.get('id')!r}"
                ),
                assign_when=rules,
                acquisition_floor=None if class_floor is None else float(class_floor),
                floor_set_at=str(entry.get("floor_set_at") or ""),
                floor_rationale=str(entry.get("floor_rationale") or "").strip(),
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
        kind = str(entry.get("kind") or "").strip()
        if kind and kind not in QUESTION_KINDS:
            raise ConfigError(
                f"questions.yaml: {entry.get('id')!r} has kind {kind!r}; "
                f"known kinds are {', '.join(QUESTION_KINDS)}"
            )
        questions.append(
            Question(
                id=_require_str(entry.get("id"), field="id", where="questions.yaml"),
                text=_require_str(entry.get("text"), field="text", where="questions.yaml"),
                added=str(added) if added else None,
                kind=kind,
            )
        )
    _require_unique([q.id for q in questions], what="question", where="questions.yaml")
    return tuple(questions), version, frozen_at


def registry_digest(questions: tuple[Question, ...]) -> str:
    """A hash of the questions themselves — ids and texts, in order.

    It covers the questions and not the file, so a cosmetic edit does not read as drift. A check
    that fires on every whitespace change stops being believed, and then it protects nothing.
    """
    import hashlib
    import json as _json

    # `kind` is in the digest because it decides which rule judges the question, and therefore
    # its answer. A question silently moved from `method` to `effect` would be judged by a
    # different standard with no trace — which is what invariant 5 exists to prevent.
    payload = _json.dumps(
        [[q.id, q.text, q.kind] for q in questions], ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def check_registry_drift(project: Project, store: Any, *, record: bool = True) -> None:
    """Refuse a registry whose text changed while its version did not (invariant 5).

    Every round-over-round figure and every multiplicity correction is stated against a registry.
    If a question's wording can change under an unchanged version, those figures compare two
    different questions and say nothing — and the change leaves no trace, which is worse than a
    wrong answer because nobody knows to distrust it.

    The first sighting of a version is recorded, not refused. A bump is recorded too. Only a
    changed hash under an unchanged version raises. Previously recorded older versions are refused
    too. `record=False` checks without appending, for read-only evidence previews.
    """
    seen: dict[int, dict[str, str]] = {}
    for row in store.read("registry.jsonl"):
        if row.get("registry_version") is None:
            continue
        seen[int(row["registry_version"])] = {
            "sha256": str(row.get("registry_sha256") or ""),
            "frozen_at": str(row.get("frozen_at") or ""),
        }

    if seen and project.registry_version < max(seen):
        raise RegistryDrift(
            f"{project.name}: registry_version {project.registry_version} is below "
            f"{max(seen)}, which this store has already recorded (invariant 5).")

    held_row = seen.get(project.registry_version)
    held = held_row["sha256"] if held_row else None
    if held == project.registry_sha256:
        return

    if held is None and seen:
        # A bump must move forward in both the version and the date. A version below one already
        # recorded is a rollback presented as a bump; an unchanged date on a higher version makes
        # the bump cosmetic, and "dated" is half of what invariant 5 asks for.
        highest = max(seen)
        latest_date = seen[highest]["frozen_at"]
        if latest_date and project.frozen_at <= latest_date:
            raise RegistryDrift(
                f"{project.name}: registry_version {project.registry_version} carries "
                f"frozen_at {project.frozen_at}, which is not later than {latest_date} recorded "
                f"for v{highest}. A registry change is dated as well as versioned (invariant 5)."
            )

    if held is not None:
        raise RegistryDrift(
            f"{project.name}: the question registry changed under registry_version "
            f"{project.registry_version}. Recorded {held[:12]}, now {project.registry_sha256[:12]}. "
            "Adding or changing a question is a dated version bump, never a silent edit — "
            "otherwise every round-over-round figure compares two different registries "
            "(invariant 5)."
        )
    if not record:
        return
    store.append("registry.jsonl", {
        "registry_version": project.registry_version,
        "registry_sha256": project.registry_sha256,
        "frozen_at": project.frozen_at,
        "questions": len(project.questions),
        "seen_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    })


MANIFEST_COLUMNS = ("source_id", "class", "format", "url", "title")
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


ASSIGN_PREDICATES = ("source_api", "openalex_source_type", "crossref_type", "host")

GATE_THRESHOLD_NAMES = ("min_pdf_bytes", "min_text_chars", "paywall_doubt_chars", "fulltext_chars")
NORMALIZE_THRESHOLD_NAMES = (
    "min_section_chars", "merge_below", "max_chunk_chars",
    "min_references", "confirm_chars",
)


GATE_POLICY_NAMES = ("paywall_phrases", "reference_headings", "structural_signal")


def _gate_policy_fields(raw: Any, *, where: str) -> dict[str, Any]:
    """Validate one gate-policy mapping, wherever it was declared."""
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: 'gate_policy' must be a mapping")
    unknown = sorted(set(raw) - set(GATE_POLICY_NAMES))
    if unknown:
        raise ConfigError(
            f"{where}: unknown gate_policy key(s): {', '.join(unknown)} "
            f"(known: {', '.join(GATE_POLICY_NAMES)})"
        )
    policy: dict[str, Any] = {}
    for name in ("paywall_phrases", "reference_headings"):
        if name in raw:
            values = raw[name]
            if not isinstance(values, list) or not values:
                raise ConfigError(f"{where}: gate_policy.{name} must be a non-empty list")
            policy[name] = tuple(str(v).strip().lower() for v in values)
    if "structural_signal" in raw:
        signal = str(raw["structural_signal"]).strip()
        if signal not in ("reference_list", "none"):
            raise ConfigError(
                f"{where}: gate_policy.structural_signal must be 'reference_list' or 'none'"
            )
        policy["structural_signal"] = signal
    return policy


def resolve_gate_policy(
    project_policy: dict[str, Any], classes: Any, source_class: str | None
) -> dict[str, Any]:
    """The policy for one candidate: the project's, overlaid by its class's.

    The class carries the override because genre is a property of the source rather than of the
    project. A corpus of papers and filings needs a reference list required for the first and not
    for the second, and one project-wide switch admitted four of six known summaries when flipped.
    """
    for klass in classes or ():
        if klass.id == source_class and klass.gate_policy:
            return {**project_policy, **klass.gate_policy}
    return dict(project_policy)


def load_gate_policy(root: pathlib.Path) -> dict[str, Any]:
    """The gate's language and genre assumptions, declared per project.

    "A bibliography is headed References" and "a paywall says purchase pdf" are knowledge about a
    language and a genre, not about the engine's job (invariant 4). The defaults in `fulltext` are
    English scholarly prose; a project in another language, or one reading regulatory filings that
    cite nothing, states its own here instead of editing the package.
    """
    return _gate_policy_fields(
        _read_yaml(pathlib.Path(root) / "sources.yaml").get("gate_policy") or {},
        where="sources.yaml",
    )


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
    if not path.exists() and path.is_symlink():
        # `Path.exists()` follows a link, so a broken one looks exactly like no link at all. Found by
        # moving to a container: this project's manifest is a symlink into another repository, the bind
        # mount carried the link and not its target, and `validate` printed OK with no manifest rows —
        # silently dropping 25 sources out of a round. A project that declares no manifest and a project
        # whose manifest points nowhere are different facts.
        raise ConfigError(
            f"manifest.tsv is a symlink that points nowhere: {path} -> "
            f"{pathlib.Path(path).readlink()}. A manifest that cannot be read is not the same as a "
            f"project without one; copy the file in, or mount its target."
        )
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


def load_normalize_thresholds(root: pathlib.Path) -> dict[str, int]:
    """Per-project overrides for chunking and confirmation. Absent means engine defaults.

    A misspelt key is an error rather than a silent no-op, for the same reason as the gate's: a
    threshold the operator believed they had changed produces a figure they would trust wrongly.
    """
    raw = _read_yaml(pathlib.Path(root) / "sources.yaml").get("normalize") or {}
    if not isinstance(raw, dict):
        raise ConfigError("sources.yaml: 'normalize' must be a mapping")
    unknown = sorted(set(raw) - set(NORMALIZE_THRESHOLD_NAMES))
    if unknown:
        raise ConfigError(
            f"sources.yaml: unknown normalize threshold(s): {', '.join(unknown)} "
            f"(known: {', '.join(NORMALIZE_THRESHOLD_NAMES)})"
        )
    for name, value in raw.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ConfigError(f"sources.yaml: normalize.{name} must be a non-negative integer")
    return {str(k): int(v) for k, v in raw.items()}


# What a project may declare about extraction. Both are vocabularies rather than thresholds, and both were
# engine constants until a corpus in another field proved they were domain knowledge: the value-label list
# shipped with `sharpe` and without `OR`, so the finance corpus parsed and the epidemiology corpus refused
# 63 estimates over `AOR=1.66` and `ß = -.22`. Invariant 4 says the engine holds none of that.
EXTRACTION_KEYS = ("comparatives", "value_labels")


def load_extraction(root: pathlib.Path) -> dict[str, Any]:
    """A project's extraction vocabulary. Absent means the engine's generic defaults.

    A misspelt key is an error rather than a silent no-op, on the same grounds as the thresholds': a
    vocabulary the operator believed they had declared produces a rejection they would misread as a fact
    about the literature.
    """
    raw = _read_yaml(pathlib.Path(root) / "sources.yaml").get("extraction") or {}
    if not isinstance(raw, dict):
        raise ConfigError("sources.yaml: 'extraction' must be a mapping")
    unknown = sorted(set(raw) - set(EXTRACTION_KEYS))
    if unknown:
        raise ConfigError(
            f"sources.yaml: unknown extraction key(s): {', '.join(unknown)} "
            f"(known: {', '.join(EXTRACTION_KEYS)})"
        )

    out: dict[str, Any] = {}
    labels = raw.get("value_labels")
    if labels is not None:
        if not isinstance(labels, list) or not all(isinstance(x, str) and x.strip() for x in labels):
            raise ConfigError("sources.yaml: extraction.value_labels must be a list of non-empty strings")
        # Exactly what the project declared. The engine merges its own generic set in at use — `t` and
        # `se` are not finance, and a project declaring `OR` has not stopped writing standard errors — and
        # keeping that merge out of here leaves this module validating data rather than holding defaults.
        out["value_labels"] = tuple(x.strip() for x in labels)

    comparatives = raw.get("comparatives")
    if comparatives is not None:
        if not isinstance(comparatives, dict) or not all(
            isinstance(v, list) and all(isinstance(x, str) for x in v) for v in comparatives.values()
        ):
            raise ConfigError(
                "sources.yaml: extraction.comparatives must map a class to a list of phrases")
        # Replaced, not extended: a project declaring these is saying which comparisons its field makes,
        # and quietly keeping the engine's would put back the stems it chose to leave out.
        out["comparatives"] = {str(k): tuple(v) for k, v in comparatives.items()}
    return out


def load_floor_provenance(root: pathlib.Path) -> tuple[int, str, str]:
    """Where the floor came from. A bump without a reason is refused.

    Invariant 3 forbids a flag that waives the floor. Without this, the door beside it is open:
    the floor is a number in an editable file, and lowering it after seeing an awkward result is
    the post-hoc move the frozen question registry exists to prevent. So a floor change is the
    same class of event as a registry bump — dated, versioned, motivated.
    """
    raw = _read_yaml(pathlib.Path(root) / "sources.yaml")
    version = raw.get("floor_version", 1)
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ConfigError("sources.yaml: 'floor_version' must be an integer >= 1")

    set_at = raw.get("floor_set_at")
    if isinstance(set_at, (_dt.date, _dt.datetime)):
        set_at = set_at.isoformat()[:10]
    set_at = str(set_at or "")
    rationale = str(raw.get("floor_rationale") or "").strip()

    if version > 1:
        if not set_at:
            raise ConfigError(
                "sources.yaml: 'floor_set_at' is required once floor_version > 1 — a floor "
                "change is dated, like a question-registry bump"
            )
        try:
            _dt.date.fromisoformat(set_at)
        except ValueError as exc:
            raise ConfigError("sources.yaml: 'floor_set_at' must be an ISO date") from exc
        if len(rationale) < 20:
            raise ConfigError(
                "sources.yaml: 'floor_rationale' is required once floor_version > 1, and must "
                "state which class of sources is structurally unobtainable — not that the "
                "measured rate was inconvenient"
            )
    return version, set_at, rationale


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
    gate_policy = load_gate_policy(path)
    normalize_thresholds = load_normalize_thresholds(path)
    citation_channel = load_citation_channel(path)
    floor_version, floor_set_at, floor_rationale = load_floor_provenance(path)

    project = Project(
        name=path.name,
        root=path,
        classes=classes,
        acquisition_floor=floor,
        excluded_hosts=excluded,
        topics=topics,
        questions=questions,
        registry_version=version,
        frozen_at=frozen_at,
        registry_sha256=registry_digest(questions),
        manifest=manifest,
        gate_thresholds=gate_thresholds,
        gate_policy=gate_policy,
        normalize_thresholds=normalize_thresholds,
        extraction=load_extraction(root),
        citation_channel=citation_channel,
        floor_version=floor_version,
        floor_set_at=floor_set_at,
        floor_rationale=floor_rationale,
    )
    project.population  # Validate the optional metadata selector before any requests.
    return project


def discover_projects(projects_dir: str | pathlib.Path = "projects") -> list[pathlib.Path]:
    base = pathlib.Path(projects_dir)
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and (p / "questions.yaml").exists())
