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
