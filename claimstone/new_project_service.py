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
    store = _store(store_dir)
    with store.writer_lock():
        normalized = pb.normalize_step(step, data, _templates_dir(projects_dir))
        if step == 1 and (pathlib.Path(projects_dir) / normalized["name"]).exists():
            raise pb.DraftInvalid([pb.Problem("name", "a project with this name already exists")])
        if step == 1 and (pathlib.Path(store_dir) / normalized["name"]).exists():
            raise pb.DraftInvalid([pb.Problem("name", "a project with this name already has stored data")])
        row = wd.save_step(store, actor=actor, draft_id=draft_id, step=step,
                           base_revision=base_revision, data=normalized, code_revision=code_revision)
    return {"revision": row["revision"], "data": normalized,
            "figures": _step_figures(step, normalized)}, 200


def _files_and_info(projects_dir, current: dict[str, Any]):
    state = {int(n): v["data"] for n, v in current["steps"].items()}
    missing = [n for n in (1, 2, 3) if n not in state]
    if missing:
        raise ServiceError(409, "INCOMPLETE", "steps not saved yet: " + ", ".join(map(str, missing)))
    today = _today()
    files = pb.render(state, _templates_dir(projects_dir), today=today,
                      overrides=current["advanced"] or None)
    # `today` is required: inspect refuses an override that breaks "registry v1, floor v1, frozen today".
    info = pb.inspect(files, name=state[1]["name"], templates_dir=_templates_dir(projects_dir),
                      template_id=state[3]["template"], today=today)
    return state, files, info


@_guard
def save_advanced(projects_dir, store_dir, actor, code_revision, draft_id, base_revision, files):
    store = _store(store_dir)
    with store.writer_lock():
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
def create(projects_dir, store_dir, actor, code_revision, draft_id, confirm, shown_sha256):
    """Create the project the operator reviewed. `shown_sha256` is the protocol digest the review page
    displayed; if the draft now renders to a different protocol (another tab, a changed step) the
    request is refused, so what is created is always what was seen."""
    if confirm is not True:
        raise ServiceError(422, "VALIDATION", "confirm must be the literal true")
    store = _store(store_dir)
    with store.writer_lock():
        current = wd.state(store, draft_id, actor)
        if current["status"] != "open":
            raise ServiceError(409, "DRAFT_CLOSED", f"this draft is {current['status']}")
        state, files, info = _files_and_info(projects_dir, current)
        if shown_sha256 != info["protocol_sha256"]:
            raise ServiceError(409, "PREVIEW_CHANGED",
                               "the project changed since you reviewed it; review it again before creating")
        name = state[1]["name"]
        if (pathlib.Path(store_dir) / name).exists():
            reason = f"a project named {name} already has stored data"
            wd.mark_failed(store, actor=actor, draft_id=draft_id, reason=reason,
                           code_revision=code_revision)
            raise ServiceError(409, "NAME_TAKEN", reason)
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
