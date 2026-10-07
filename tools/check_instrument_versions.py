#!/usr/bin/env python
"""Refuse a gate or chunk version bump that no recorded measurement acknowledges.

Every rate this project publishes was produced by an instrument: the content gate at some
`GATE_VERSION` under some thresholds, and the chunker at some `CHUNK_VERSION`. Two figures are
comparable only if they came from the same instrument, and a version can be bumped in one commit
while `docs/DESIGN_DECISIONS.md` still quotes figures from the previous one — at which point a
trend is two different measurements wearing the same label.

So: if a version constant has a value, the design record must mention that value. This is a
reminder to write down what changed, not a proof that anything is correct.

Exit 0 when satisfied, 1 with an explanation otherwise.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECORD = ROOT / "docs" / "DESIGN_DECISIONS.md"

# Each instrument: the module holding its version, the constant, and the phrase the record must
# use so the mention is deliberate rather than accidental.
INSTRUMENTS = (
    ("tools/run_source_screening.py", "SCREENING_VERSION", "screening_version"),
    ("claimstone/review.py", "REVIEW_VERSION", "review_version"),
    ("claimstone/net.py", "FETCH_VERSION", "fetch_version"),
    ("claimstone/admissibility.py", "ADMISSION_VERSION", "admission_version"),
    ("claimstone/gate_audit.py", "AUDIT_VERSION", "audit_version"),
    ("claimstone/model_report.py", "MODEL_REPORT_VERSION", "model_report_version"),
    ("claimstone/searchers.py", "DISCOVERY_VERSION", "discovery_version"),
    ("claimstone/model_call.py", "RESULT_JUDGE_VERSION", "result_judge_version"),
    ("claimstone/claim_records.py", "ANNOTATION_VERSION", "annotation_version"),
    ("claimstone/synthesize.py", "PROFILE_VERSION", "profile_version"),
    ("claimstone/fulltext.py", "GATE_VERSION", "gate_version"),
    # The claim gate is the executable form of invariant 1, and went unversioned through the first full
    # round. Two claims admitted under different rule sets are not the same kind of row.
    ("claimstone/claimgate.py", "CLAIM_GATE_VERSION", "claim_gate_version"),
    ("claimstone/chunk.py", "CHUNK_VERSION", "chunk_version"),
    # The HTML parser is an instrument too: what it extracts decides body_chars and references, and those
    # decide fulltext_confirmed. The PDF parser is pinned by digest in compose.yaml; this one is code.
    ("claimstone/html_doc.py", "HTML_PARSER_VERSION", "html_parser_version"),
    ("claimstone/jats.py", "JATS_PARSER_VERSION", "jats_parser_version"),
    ("claimstone/source_selection.py", "SOURCE_SELECTION_VERSION", "source_selection_version"),
    ("claimstone/source_selection.py", "IDENTITY_RELATION_VERSION", "identity_relation_version"),
    ("tools/import_source_selection.py", "SOURCE_SELECTION_IMPORT_VERSION", "source_selection_import_version"),
    ("claimstone/population.py", "POPULATION_VERSION", "population_version"),
    # The portal API's payload shape is what the operator reads: versioned like an instrument (D84).
    ("claimstone/api.py", "API_VERSION", "portal_api_version"),
    ("claimstone/acquire.py", "REUSE_VERSION", "reuse_version"),
    ("claimstone/ids.py", "CANDIDATE_KEY_VERSION", "candidate_key_version"),
    # The portal's own instruments: the selector predicate every scoped read shares, the flow
    # ledger's shape, and the export's. Each is registered so a bump is recorded, not silent.
    ("claimstone/scope.py", "SCOPE_VERSION", "scope_version"),
    ("claimstone/flows.py", "FLOW_VERSION", "flow_version"),
    ("claimstone/export.py", "EXPORT_VERSION", "export_version"),
    ("claimstone/scheduler_preview.py", "SCHEDULER_PREVIEW_VERSION", "scheduler_preview_version"),
    ("claimstone/operations.py", "OPERATIONS_VERSION", "operations_version"),
    # The verdict's provenance is part of what was signed: two rows that differ only in signer
    # class are not the same kind of record, so the adjudication row is versioned like the rest.
    ("claimstone/synthesize.py", "ADJUDICATION_VERSION", "adjudication_version"),
    # The operator ledger decides who may write through the control API: a row shape change
    # is a change in who can authenticate, so it is versioned like any instrument (D99).
    ("claimstone/operators.py", "OPERATOR_VERSION", "operator_version"),
    # A draft is never evidence, but its row shape is what the reading desk restores after a
    # profile change: a change to it is a change to what a person gets back (D100).
    ("claimstone/drafts.py", "DRAFT_VERSION", "draft_version"),
    # Where a proposed item was routed decides whether it can ever join a population (D101).
    ("claimstone/intake.py", "INTAKE_VERSION", "intake_version"),
    # A decision row is what lets a later reader see who approved which plan or offer (D103).
    ("claimstone/decisions.py", "DECISION_VERSION", "decision_version"),
    # What counts as "since your last visit" is the marker row (D104).
    ("claimstone/today.py", "SEEN_VERSION", "seen_version"),
    # Who checked which service, or replaced which credential, and when (D106).
    ("claimstone/admin.py", "ADMIN_CHECK_VERSION", "admin_check_version"),
)

# The parser is an instrument too, and a string rather than a number. Measured: lfoppiano/grobid
# latest-crf produced 508 KB of TEI against 0.8.1's 91 KB on the same PDF, so a switch would change
# every body-character, section and reference count without touching a version number.
PARSERS = (("claimstone/grobid.py", "IMAGE"),)

# And the digest, where a compose file pins one. A tag can be re-pushed under the same name, so the tag
# being recorded is not the same as the build being recorded — see D29.
DIGEST = re.compile(r"^\s+image:\s*\S+@(sha256:[0-9a-f]{64})\s*$", re.M)


def declared(path: pathlib.Path, constant: str) -> int | None:
    if not path.exists():
        return None
    found = re.search(rf"^{constant}\s*=\s*(\d+)", path.read_text(encoding="utf-8"), re.M)
    return int(found.group(1)) if found else None


def declared_string(path: pathlib.Path, constant: str) -> str | None:
    if not path.exists():
        return None
    found = re.search(
        rf'^{constant}\s*=\s*["\']([^"\']+)["\']', path.read_text(encoding="utf-8"), re.M
    )
    return found.group(1) if found else None


def check() -> list[str]:
    """Every acknowledgement problem, as lines. An empty list means the record is current.

    Split out of `main` so the portal's integrity panel can run the same check read-only;
    `main` keeps its exit codes and output exactly as before.
    """
    if not RECORD.exists():
        return [f"missing {RECORD.relative_to(ROOT)}"]
    record = RECORD.read_text(encoding="utf-8")

    problems: list[str] = []
    for relative, constant, phrase in INSTRUMENTS:
        version = declared(ROOT / relative, constant)
        if version is None:
            # The module does not exist yet, or does not declare it. Both are fine; this script
            # reminds, it does not require a stage to be built.
            continue
        if not re.search(rf"{phrase}\D{{0,40}}{version}\b", record, re.I):
            problems.append(
                f"{relative} declares {constant} = {version}, and "
                f"docs/DESIGN_DECISIONS.md never mentions {phrase} {version}. "
                f"A figure measured under a different instrument is not comparable to one "
                f"measured under this; record what changed and which figures it supersedes."
            )

    for relative, constant in PARSERS:
        image = declared_string(ROOT / relative, constant)
        if image is None:
            continue
        if image not in record:
            problems.append(
                f"{relative} declares {constant} = {image!r}, and "
                f"docs/DESIGN_DECISIONS.md never names it. Figures measured with a different "
                f"parser build are not comparable to figures measured with this one."
            )

    compose = ROOT / "compose.yaml"
    if compose.exists():
        found = DIGEST.search(compose.read_text(encoding="utf-8"))
        if found is None:
            problems.append(
                "compose.yaml pins no image digest. A tag can be re-pushed under the same name, so a "
                "figure measured with one build is not comparable to one measured with another."
            )
        elif found.group(1) not in record:
            problems.append(
                f"compose.yaml pins {found.group(1)} and docs/DESIGN_DECISIONS.md never names it. "
                f"An instrument the record does not name is one nobody can tell you changed."
            )
    return problems


def main() -> int:
    problems = check()
    if problems:
        for problem in problems:
            print(f"error: {problem}")
        return 1
    checked = 0
    for relative, constant, phrase in INSTRUMENTS:
        if declared(ROOT / relative, constant) is not None:
            checked += 1
    for _relative, _constant in PARSERS:
        checked += 1
    compose = ROOT / "compose.yaml"
    if compose.exists() and DIGEST.search(compose.read_text(encoding="utf-8")):
        checked += 1
    print(f"{checked} instrument version(s) acknowledged in the design record")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
