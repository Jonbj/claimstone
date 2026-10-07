"""Operator-supplied material: a DOI, a link or a reference someone thinks belongs here (spec B7a).

`intake.jsonl` records what was proposed, where it was routed and why. A state change is a new row
with the same `intake_id`, never an edit. Nothing here counts toward any denominator, creates a
candidate, or runs a stage. Routing answers one question before anything is recorded as usable:
does this item add a work to the flow's population, or is it something the population already has?

The routing follows the engine's own notion of what is frozen (review F10). A round freezes its
population **predicate**, not its set: `discover` keeps adding candidates that match. Only the
curated manifest (`manifest_only`) has a fixed candidate set. So:

- an item matching a candidate already in the flow's scope by DOI or URL is a `DUPLICATE` of it;
- a match on folded title alone is a `POSSIBLE_VERSION` — the same work is likely, not established,
  and only a person decides identity (B8);
- an unmatched item in a manifest flow, or in a whole-store flow that names no round, cannot join:
  `NEEDS_NEW_ROUND`, listing the open flows it could go to;
- an unmatched item in an open round is `READY` for that round's next discover. Discover does not
  read `intake.jsonl` yet; until it does, `READY` means "recorded and routed", and the population
  predicate is applied by discover, never here.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import os
import pathlib
import secrets
import subprocess
import tempfile
import urllib.parse
from typing import Any, BinaryIO, Callable, Iterable

from claimstone import admissibility, flows, fulltext, ids, net, scope
from claimstone.store import Store

INTAKE_VERSION = 1

LEDGER = "intake.jsonl"

KINDS = ("doi", "url", "reference")

STATES = ("RECEIVED", "CHECKING", "DUPLICATE", "POSSIBLE_VERSION", "NEEDS_NEW_ROUND", "REJECTED",
          "READY", "COUNTED", "REPORTED_SEPARATELY")

MAX_VALUE_CHARS = 2_000
MAX_NOTE_CHARS = 2_000

MAX_FILE_BYTES = 50 * 1024 * 1024
QUARANTINE = "quarantine"
CAMPAIGN = "operator-intake"
TEXT_PAGES = 3          # identity is read from the first pages, where title and DOI are printed
TEXT_TIMEOUT_SECONDS = 60


class IntakeRefused(ValueError):
    """The item cannot be recorded at all: a malformed value or a forbidden destination."""


class TooLarge(IntakeRefused):
    """A file over MAX_FILE_BYTES: nothing is kept."""


class UnknownTarget(LookupError):
    """The candidate a file is for is not in the flow's scope."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def normalize(kind: str, value: str, *, excluded_hosts: Iterable[str] = (),
              resolver: Callable[..., Any] | None = None) -> str:
    """The comparison form of one proposed value, or IntakeRefused with the reason.

    A URL is checked before anything is recorded: http(s) only, not an excluded host, and every
    address it resolves to global (F15). Nothing is fetched here — a resolution is not a request
    to the host."""
    if kind not in KINDS:
        raise IntakeRefused(f"kind must be one of {', '.join(KINDS)}")
    text = (value or "").strip()
    if not text:
        raise IntakeRefused("value must be non-empty")
    if len(text) > MAX_VALUE_CHARS:
        raise IntakeRefused(f"value is over {MAX_VALUE_CHARS} characters")
    if kind == "doi":
        doi = ids.normalize_doi(text)
        if doi is None:
            raise IntakeRefused("not a DOI")
        return doi
    if kind == "url":
        parts = urllib.parse.urlsplit(text)
        if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
            raise IntakeRefused("a link must be an http or https URL with a host")
        host = parts.hostname.lower()
        excluded = {h.lower() for h in excluded_hosts}
        if host in excluded or any(host.endswith("." + h) for h in excluded):
            raise IntakeRefused(f"{host} is an excluded host for this project")
        if net.global_addresses(host, resolver) is None:
            raise IntakeRefused(f"{host} does not resolve only to public addresses")
        return ids.normalize_url(text)
    return text  # a reference is kept as written; its folded title is used only to compare


def _match(kind: str, normalized: str, candidates: dict[str, dict[str, Any]]
           ) -> tuple[str | None, str | None]:
    """(state, candidate_key) for an item against the scoped candidates, or (None, None)."""
    for key, row in candidates.items():
        if kind == "doi" and ids.normalize_doi(row.get("doi")) == normalized:
            return "DUPLICATE", key
        if kind == "url" and row.get("url") and ids.normalize_url(row.get("url")) == normalized:
            return "DUPLICATE", key
    if kind == "url":
        doi = ids.normalize_doi(normalized)  # a doi.org link names its DOI
        if doi:
            for key, row in candidates.items():
                if ids.normalize_doi(row.get("doi")) == doi:
                    return "DUPLICATE", key
    if kind == "reference":
        folded = ids.normalize_title(normalized)
        if folded:
            for key, row in candidates.items():
                title = ids.normalize_title(row.get("title"))
                if title and (title == folded or (len(title) > 20 and title in folded)):
                    return "POSSIBLE_VERSION", key
    return None, None


def latest(store: Store) -> dict[str, dict[str, Any]]:
    """intake_id -> the latest row for it, in first-recorded order."""
    out: dict[str, dict[str, Any]] = {}
    for row in store.read(LEDGER):
        out[str(row.get("intake_id"))] = dict(row)
    return out


def _open_flows(store: Store, project: Any, exclude: str) -> list[dict[str, Any]]:
    """Flows an unmatched item could start in: bound, current, and naming one round."""
    found = []
    for flow_id, row in flows.flows(store).items():
        if flow_id == exclude:
            continue
        selector = (row.get("binding") or {}).get("selector") or {}
        if selector.get("manifest_only") or not selector.get("round"):
            continue
        if flows.binding_state(project, store, row)["state"] != "CURRENT":
            continue
        found.append({"flow_id": flow_id, "round": selector.get("round"),
                      "title": row.get("title")})
    return found


def submit(store: Store, project: Any, flow_row: dict[str, Any], selector: scope.Selector, *,
           kind: str, value: str, note: str | None, actor: str, code_revision: str | None,
           resolver: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Route one proposed item and record it. Returns the row written."""
    if note is not None and len(note) > MAX_NOTE_CHARS:
        raise IntakeRefused(f"note is over {MAX_NOTE_CHARS} characters")
    normalized = normalize(kind, value, excluded_hosts=project.excluded_hosts, resolver=resolver)
    flow_id = str(flow_row["flow_id"])
    with store.writer_lock():
        held = [row for row in latest(store).values()
                if row.get("flow_id") == flow_id and row.get("kind") == kind
                and row.get("value") == normalized]
        state, key, reason, links = None, None, "", {}
        if held:
            state = "DUPLICATE"
            links = {"intake_id": held[0]["intake_id"]}
            reason = "the same item was already proposed for this flow; nothing added"
        else:
            state, key = _match(kind, normalized, scope.candidates(store, selector))
            if state == "DUPLICATE":
                links = {"candidate_key": key}
                reason = "already a candidate in this flow; it adds no new work"
            elif state == "POSSIBLE_VERSION":
                links = {"candidate_key": key}
                reason = ("the title matches a candidate in this flow; whether it is the same "
                          "work, a version of it or a different work is a person's decision")
            elif selector.manifest_only or not selector.round:
                state = "NEEDS_NEW_ROUND"
                links = {"open_flows": _open_flows(store, project, flow_id)}
                reason = ("this flow's candidate set is fixed: a new work cannot join it, and "
                          "can only start in an open round")
            else:
                state = "READY"
                reason = (f"routed to round {selector.round}'s next discover, which applies the "
                          "round's population predicate; nothing counts until then")
        row = {
            "intake_version": INTAKE_VERSION,
            "intake_id": secrets.token_hex(12),
            "flow_id": flow_id,
            "kind": kind,
            "value": normalized,
            "submitted": value.strip(),
            "note": note,
            "state": state,
            "stage": "routing",
            "reason": reason,
            "links": links,
            "actor": actor,
            "signer_auth": "portal-session",
            "code_revision": code_revision,
            "recorded_at": _now(),
        }
        store.append(LEDGER, row)
    return row


def for_flow(store: Store, flow_id: str) -> list[dict[str, Any]]:
    """Every item proposed for one flow with its latest state, newest first."""
    rows = [row for row in latest(store).values() if row.get("flow_id") == str(flow_id)]
    return list(reversed(rows))


# --- files (B7b) ------------------------------------------------------------------------------------


def quarantine_stream(store: Store, stream: BinaryIO, length: int) -> tuple[str, pathlib.Path, bool]:
    """(sha256, path, already_held) for `length` bytes read from `stream` into `quarantine/`.

    Hashed while streamed; never more than MAX_FILE_BYTES read. The bytes land under their own
    hash, so the same upload twice is one file. `already_held` is True when identical bytes were
    already in `quarantine/` or in `raw/` — the second upload adds nothing."""
    if length < 0 or length > MAX_FILE_BYTES:
        raise TooLarge(f"a file must be at most {MAX_FILE_BYTES} bytes")
    directory = store.root / QUARANTINE
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    remaining = length
    handle, temp_name = tempfile.mkstemp(dir=directory, suffix=".part")
    try:
        with os.fdopen(handle, "wb") as out:
            while remaining:
                chunk = stream.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise IntakeRefused("the upload ended before its declared length")
                digest.update(chunk)
                out.write(chunk)
                remaining -= len(chunk)
        sha = digest.hexdigest()
        target = directory / f"{sha}.pdf"
        held = target.exists() or any((store.root / "raw").glob(f"{sha}.*"))
        if held:
            os.unlink(temp_name)  # identical bytes are already kept; a second copy adds nothing
        else:
            os.replace(temp_name, target)
        return sha, target, held
    except BaseException:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        raise


def pdf_text(path: pathlib.Path) -> str:
    """The first pages' text, by `pdftotext -layout` — the extraction the L02 identity inspection
    used (D80). An unreadable PDF raises: identity cannot be read from what cannot be read."""
    completed = subprocess.run(
        ["pdftotext", "-layout", "-l", str(TEXT_PAGES), str(path), "-"],
        capture_output=True, check=True, timeout=TEXT_TIMEOUT_SECONDS)
    return completed.stdout.decode("utf-8", "replace")


def _row(flow_id: str, *, kind: str, value: str, submitted: str, state: str, stage: str,
         reason: str, links: dict[str, Any], actor: str, code_revision: str | None,
         intake_id: str | None = None) -> dict[str, Any]:
    return {
        "intake_version": INTAKE_VERSION, "intake_id": intake_id or secrets.token_hex(12),
        "flow_id": flow_id, "kind": kind, "value": value, "submitted": submitted, "note": None,
        "state": state, "stage": stage, "reason": reason, "links": links, "actor": actor,
        "signer_auth": "portal-session", "code_revision": code_revision, "recorded_at": _now(),
    }


def _holds_copy(store: Store, candidate: dict[str, Any]) -> str | None:
    """Why this candidate needs no supplied copy, or None when it does.

    A copy is not needed when Claimstone already holds one that is confirmed as a document, or
    one still awaiting that check. A copy the normalizer refuted (`fulltext_confirmed` false) is
    exactly what a supplied copy can replace."""
    held = admissibility.collapse(store).get(str(candidate["candidate_key"]))
    if not held or not held.get("acquired"):
        return None
    identifier = str(held.get("source_id") or candidate["candidate_key"])
    document = admissibility.confirmations(store).get(identifier)
    if document is None:
        return "this candidate already has a copy awaiting the document check"
    if document.get("fulltext_confirmed"):
        return "this candidate already has a copy confirmed as a document"
    return None


def receive_file(store: Store, project: Any, flow_row: dict[str, Any], selector: scope.Selector,
                 *, target: str, sha: str, path: pathlib.Path, already_held: bool, actor: str,
                 code_revision: str | None,
                 extract_text: Callable[[pathlib.Path], str] = pdf_text) -> dict[str, Any]:
    """Check one quarantined file against the candidate it is for, and record the outcome.

    The checks are the engine's own, in order: identical bytes already held; the content gate
    downloads pass (`fulltext.classify`, the candidate's class policy); identity read from the
    first pages against the candidate's title and DOI. Only a file that passes all three leaves
    quarantine, becomes an `operator-supplied` acquisition row, and is listed for the next scoped
    normalize. Whether it then counts toward the floor is the project's declared policy."""
    flow_id = str(flow_row["flow_id"])
    candidate = scope.candidates(store, selector).get(str(target))
    if candidate is None:
        raise UnknownTarget(f"no candidate {target} in this flow")
    common = {"kind": "file", "value": sha, "submitted": str(target), "actor": actor,
              "code_revision": code_revision}
    links: dict[str, Any] = {"candidate_key": str(target), "sha256": sha}

    def record(state: str, stage: str, reason: str, extra: dict[str, Any] | None = None):
        row = _row(flow_id, state=state, stage=stage, reason=reason,
                   links={**links, **(extra or {})}, **common)
        store.append(LEDGER, row)
        return row

    with store.writer_lock():
        earlier = [row for row in latest(store).values()
                   if row.get("kind") == "file" and row.get("value") == sha]
    if already_held or earlier:
        extra = {"intake_id": earlier[0]["intake_id"]} if earlier else {}
        return record("DUPLICATE", "file_checks",
                      "identical bytes are already held; nothing added, not a second study", extra)

    payload = path.read_bytes()
    thresholds = {**fulltext.DEFAULT_THRESHOLDS, **(project.gate_thresholds or {})}
    from claimstone.config import resolve_gate_policy
    policy = resolve_gate_policy(project.gate_policy or {}, project.classes,
                                 candidate.get("source_class"))
    judged = fulltext.classify(payload, "application/pdf", "upload.pdf", thresholds, policy=policy)
    if not judged.accepted:
        return record("REJECTED", "file_checks",
                      f"not a document by the content gate: {judged.kind} ({judged.reason})")

    try:
        text = extract_text(path)
    except (OSError, subprocess.SubprocessError) as exc:
        return record("REJECTED", "identity",
                      f"the PDF's text cannot be extracted ({type(exc).__name__}); identity "
                      "cannot be read from it")
    folded = ids.normalize_title(text)
    title = ids.normalize_title(candidate.get("title"))
    doi = ids.normalize_doi(candidate.get("doi"))
    title_found = bool(title) and title in folded
    doi_found = bool(doi) and doi in text.lower()
    evidence = {"title_found": title_found, "doi_found": doi_found,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    if not title_found:
        return record("POSSIBLE_VERSION", "identity",
                      "the candidate's title is not in the first pages"
                      + (" (its DOI is)" if doi_found else "")
                      + "; whether this is the same work, a version or another work is a "
                      "person's decision", {"identity": evidence})

    reason_held = _holds_copy(store, candidate)
    if reason_held:
        return record("DUPLICATE", "identity", reason_held + "; nothing added",
                      {"identity": evidence})

    _digest, stored = store.store_bytes(payload, ".pdf")
    counted = getattr(project, "supplied_copies", "separate") == "count"
    with store.writer_lock():
        held = store.latest_by("acquisitions.jsonl", "candidate_key").get(str(target))
        intake_row = _row(
            flow_id, state="COUNTED" if counted else "REPORTED_SEPARATELY", stage="accepted",
            reason=("accepted; counts toward the floor (declared policy: count)" if counted else
                    "accepted; reported separately from the floor (policy: separate)")
            + "; listed for the next scoped normalize",
            links={**links, "identity": evidence}, **common)
        store.append("acquisitions.jsonl", {
            "candidate_key": str(target), "source_id": candidate.get("source_id"),
            "source_class": candidate.get("source_class"), "campaign": CAMPAIGN,
            "attempt_no": int((held or {}).get("attempt_no") or 0) + 1,
            "acquired": True, "sha256": sha, "stored_path": str(stored),
            "url": str(candidate.get("url") or ""), "provenance": admissibility.OPERATOR_SUPPLIED,
            "version": "", "licence": None, "oa_status": None, "host_type": None,
            "content_type": "application/pdf", "bytes": len(payload),
            "gate": judged.as_row(thresholds, policy), "failure_class": None, "attempts": [],
            "fetched_at": None, "supplied_at": intake_row["recorded_at"], "supplied_by": actor,
            "intake_id": intake_row["intake_id"], "intake_version": INTAKE_VERSION,
        })
        store.append(LEDGER, intake_row)
    if path.exists():
        path.unlink()
    return intake_row
