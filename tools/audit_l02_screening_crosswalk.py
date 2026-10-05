"""Reproduce the offline L02 v1/v2 screening crosswalk without changing ledgers."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def _read(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(v1_path: Path, scope_path: Path, packet_path: Path, ai_path: Path) -> dict:
    v1 = _read(v1_path)
    scope = _read(scope_path)
    packet = _read(packet_path)
    ai = _read(ai_path)
    assert isinstance(v1, list) and isinstance(scope, dict)
    assert isinstance(packet, dict) and isinstance(ai, dict)
    assert scope["question_id"] == packet["question_id"] == ai["question_id"] == "L02"
    assert scope["registry_sha256"] == packet["registry_sha256"]
    assert ai["label"] == "AI_PROVISIONAL"
    assert packet["reference_status"] != "HUMAN_REFERENCE"
    assert packet["scope_sha256"] == _sha(scope_path)
    assert ai["input_packet"]["sha256"] == _sha(packet_path)

    v1_by_key = {row["candidate_key"]: row for row in v1}
    packet_by_key = {row["candidate_key"]: row for row in packet["cases"]}
    ai_by_key = {row["candidate_key"]: row for row in ai["cases"]}
    assert len(v1_by_key) == len(v1)
    assert len(packet_by_key) == len(packet["cases"])
    assert len(ai_by_key) == len(ai["cases"])
    assert packet_by_key.keys() == ai_by_key.keys()
    for key, row in ai_by_key.items():
        assert row["decision"] in {"INCLUDE", "EXCLUDE", "UNCERTAIN"}
        for quote in row["quotes"]:
            assert quote["text"] in packet_by_key[key]["source_text"]

    return {
        "input_sha256": {
            "v1_decisions": _sha(v1_path),
            "v2_scope": _sha(scope_path),
            "v2_packet": _sha(packet_path),
            "ai_screening": _sha(ai_path),
        },
        "v1_count": len(v1),
        "v1_decisions": dict(sorted(Counter(row["decision"] for row in v1).items())),
        "v2_packet_count": len(packet_by_key),
        "ai_decisions": dict(sorted(Counter(row["decision"] for row in ai_by_key.values()).items())),
        "v1_v2_overlap_keys": sorted(v1_by_key.keys() & packet_by_key.keys()),
        "v1_include_keys": sorted(key for key, row in v1_by_key.items() if row["decision"] == "INCLUDE"),
        "v1_uncertain_keys": sorted(key for key, row in v1_by_key.items() if row["decision"] == "UNCERTAIN"),
        "ai_exclude_keys": sorted(key for key, row in ai_by_key.items() if row["decision"] == "EXCLUDE"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-decisions", type=Path, required=True)
    parser.add_argument("--v2-scope", type=Path, required=True)
    parser.add_argument("--v2-packet", type=Path, required=True)
    parser.add_argument("--ai-screening", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.v1_decisions, args.v2_scope, args.v2_packet, args.ai_screening), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
