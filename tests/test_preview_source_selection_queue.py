import hashlib
import json

from claimstone.store import Store
from tools.preview_source_selection_queue import build


def test_queue_reuses_abstract_and_preserves_missing_or_failed_outcomes(tmp_path):
    store = Store("fixture", base=tmp_path)
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps([
        {"candidate_key": key, "title": key} for key in ("held", "missing", "failed", "both")]))
    queue = tmp_path / "queue.json"
    queue.write_text(json.dumps({"inventory_sha256": hashlib.sha256(inventory.read_bytes()).hexdigest(),
                                 "records": []}))
    for row in [
        {"candidate_key": "held", "status": "ABSTRACT_AVAILABLE", "abstract": "Retained text"},
        {"candidate_key": "held", "status": "LOOKUP_FAILED"},
        {"candidate_key": "missing", "status": "NO_ABSTRACT"},
        {"candidate_key": "failed", "status": "LOOKUP_FAILED"},
        {"candidate_key": "both", "status": "NO_ABSTRACT", "provider": "openalex"},
        {"candidate_key": "both", "status": "NO_ABSTRACT", "provider": "crossref"},
    ]:
        store.append("screening_metadata.jsonl", row)
    before = store.path("screening_metadata.jsonl").read_bytes()
    report = build(store, inventory, queue, "scope", "Q01")
    reasons = {row["candidate_key"]: row["reason"] for row in report["tasks"]}
    assert reasons == {
        "held": "recorded_abstract_needs_validation",
        "missing": "missing_abstract_needs_alternative_authority",
        "failed": "metadata_outcome_needs_review",
        "both": "abstract_absent_from_checked_providers",
    }
    assert store.path("screening_metadata.jsonl").read_bytes() == before
