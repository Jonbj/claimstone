"""The portal API's JSON contract, hand-declared: one JSON Schema (draft 2020-12) per route
payload (spec §3.4).

`tools/build_portal_api_schema.py` renders this into `docs/contracts/portal-api.schema.json`,
and `tests/test_api_contract.py` re-renders it and compares, so the committed file can never
drift from the declaration. The declaration is deliberately hand-written rather than derived
from the payload constructors: it is the *promise* the API makes, and a promise derived from
the code it promises things about checks nothing. Where a field's value comes from a closed
vocabulary the engine owns — the five verdicts, the inbox categories, the binding states, the
§3.3 error codes — it is an `enum`, so an unknown word is a contract failure rather than a
silent rendering.

No `$ref` and no `$defs` anywhere: the validator the tests use is minimal by design
(`type`, `required`, `properties`, `enum`, `items`, `additionalProperties`), and an
unresolved reference would make part of the schema vacuously true. Every shared shape is
inlined instead. `additionalProperties: false` holds at the top level of every payload, and
nested wherever the constructor enumerates its keys exactly; pass-through ledger rows stay
open because their vocabulary is the ledger's, not this API's.
"""

from __future__ import annotations

from typing import Any

DRAFT = "https://json-schema.org/draft/2020-12/schema"

API_VERSION = 1

# The five verdicts of invariant 2 — never collapsed, never extended by the frontend.
VERDICTS = ("SUPPORTED", "CONTRADICTED", "CONTESTED_IN_LITERATURE",
            "UNANSWERED_IN_LITERATURE", "NEVER_ASKED")

# portal_state.CATEGORY_ORDER, the inbox card categories.
CATEGORIES = ("INTEGRITY", "PROTOCOL", "ACQUISITION", "CLASSIFICATION", "NORMALIZE",
              "EXTRACT", "REVIEW", "ADJUDICATION", "ADVISORY")

# flows.binding_state's states.
BINDING_STATES = ("CURRENT", "REGISTRY_DRIFTED", "PROTOCOL_DRIFTED", "POPULATION_DRIFTED")

# The §3.3 envelope codes.
ERROR_CODES = ("BAD_REQUEST", "NOT_FOUND", "CONFIG_ERROR", "REGISTRY_DRIFT", "LEDGER_CORRUPT",
               "MISDIRECTED", "CROSS_ORIGIN", "INTERNAL")

# portal_state.QUESTION_STATES, §8.3: the overview's DonutChart counts, decided server-side.
QUESTION_STATES = ("signed", "stale", "awaiting_a_person", "provisional", "no_verified_claim",
                   "not_applicable", "historical", "no_profile")

# portal_state.TRACKER_STATES, §8.3: one per scoped candidate on the overview's Tracker.
TRACKER_STATES = ("confirmed", "awaiting_normalize", "not_a_document", "not_obtained",
                  "not_attempted", "unclassified")

_STR = {"type": "string"}
_STR_OR_NULL = {"type": ["string", "null"]}
_INT = {"type": "integer"}
_INT_OR_NULL = {"type": ["integer", "null"]}
_BOOL = {"type": "boolean"}

_API_VERSION = {"type": "integer", "enum": [API_VERSION]}

_SELECTOR = {
    "type": "object",
    "required": ["round", "manifest_only"],
    "properties": {"round": _STR_OR_NULL, "manifest_only": _BOOL},
    "additionalProperties": False,
}

_CODE = {
    "type": "object",
    "required": ["revision", "dirty"],
    "properties": {"revision": _STR_OR_NULL,
                   "dirty": {"type": ["boolean", "null"]}},
    "additionalProperties": False,
}

_VERDICT_OR_NULL = {"enum": [None, *VERDICTS]}

# An attempt's failure class, display-ready (F19): a stored class name asserts an inference
# the UI must not repeat as a fact, so the server renders it once and the frontend shows it
# verbatim (§4.2 rule 5). `HTTP 403 (access refused) [PAYWALL_403]` and friends.
_FAILURE_DISPLAY = {"type": "string"}

_CARD = {
    "type": "object",
    "required": ["category", "scope", "subject", "cause", "command", "note"],
    "properties": {
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "scope": _STR,
        "subject": _STR,
        "cause": _STR,
        "command": _STR_OR_NULL,
        "note": _STR,
    },
    "additionalProperties": False,
}

_ACTIVITY_ROW = {
    "type": "object",
    "required": ["when", "stage", "ledger", "row"],
    "properties": {"when": _STR, "stage": _STR, "ledger": _STR,
                   "row": {"type": "object"}},
    "additionalProperties": False,
}

_COVERAGE = {
    "type": "object",
    "required": ["sources", "examined"],
    "properties": {"sources": _INT_OR_NULL, "examined": _INT_OR_NULL},
    "additionalProperties": False,
}

# One row of `question_matrix` (§4.9): registry order, per-class counts before the total.
_QUESTION_ROW = {
    "type": "object",
    "required": ["id", "kind", "text", "claims_by_class", "claims", "coverage",
                 "direction_count", "direction_count_note", "gate_rejected_total",
                 "gate_rejected", "awaiting_review", "state", "provisional", "blocking",
                 "verdict", "verdict_stale", "profile_sha256", "extraction", "unavailable",
                 "stored_profile_stale", "operational_not_applicable", "note", "display_state"],
    "properties": {
        # The row's one displayed state, the same word the overview's donut counts (§8.3).
        "display_state": {"type": "string", "enum": list(QUESTION_STATES)},
        "id": _STR,
        "kind": _STR,
        "text": _STR,
        "claims_by_class": {"type": "object", "additionalProperties": _INT},
        "claims": _INT_OR_NULL,
        "coverage": _COVERAGE,
        "direction_count": {"type": "object"},
        "direction_count_note": _STR,
        "gate_rejected_total": _INT,
        "gate_rejected": {"type": "object"},
        "awaiting_review": _INT,
        "state": _STR_OR_NULL,
        "provisional": _BOOL,
        "blocking": {"type": "array", "items": _STR},
        "verdict": _VERDICT_OR_NULL,
        "verdict_stale": _BOOL,
        "profile_sha256": _STR_OR_NULL,
        "extraction": {"type": ["object", "null"]},
        "unavailable": _STR,
        "stored_profile_stale": _BOOL,
        "operational_not_applicable": _BOOL,
        "note": _STR_OR_NULL,
    },
    "additionalProperties": False,
}

_VERDICT_COUNTS = {
    "type": ["object", "null"],
    "required": ["adjudicated", "stale", "awaiting_adjudication"],
    "properties": {"adjudicated": _INT, "stale": _INT,
                   "awaiting_adjudication": _INT},
    "additionalProperties": False,
}


def _payload(title: str, fields: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """One route's schema: `api_version` plus the payload's own fields, closed at the top
    level (`additionalProperties: false`) so an added key is a contract change, not a
    silent extra the frontend ignores."""
    return {
        "$schema": DRAFT,
        "title": title,
        "type": "object",
        "required": ["api_version", *required],
        "properties": {"api_version": _API_VERSION, **fields},
        "additionalProperties": False,
    }


META = _payload("meta", {
    "code": _CODE,
    "instruments": {"type": "object",
                    "additionalProperties": {"type": ["integer", "string"]}},
    "started_at": _STR,
}, ["code", "instruments", "started_at"])

ADMIN = _payload("admin", {
    "credentials": {"type": "object", "additionalProperties": _BOOL},
    "backends": {
        "type": "object",
        "required": ["configured", "available"],
        "properties": {
            "configured": {"type": "array", "items": _STR},
            "available": {"type": "array", "items": _STR},
        },
        "additionalProperties": False,
    },
    "backends_note": _STR,
    "instruments": {"type": "object",
                    "additionalProperties": {"type": ["integer", "string"]}},
    "key_rotation_note": _STR,
}, ["credentials", "backends", "backends_note", "instruments", "key_rotation_note"])

PROJECTS = _payload("projects", {
    "projects": {
        "type": "array",
        "items": {
            # A broken project stays in the list as data (config_error), so only the three
            # common keys are required; the rest belong to a loadable project.
            "type": "object",
            "required": ["name", "config", "config_error"],
            "properties": {
                "name": _STR,
                "config": {"type": "string", "enum": ["OK", "ConfigError"]},
                "config_error": _STR_OR_NULL,
                "registry_version": _INT,
                "registry_sha256": _STR,
                "registry_drift": _STR_OR_NULL,
                # A damaged ledger in this project, named here so the other projects still
                # list: one corrupt store must not empty the whole index.
                "integrity_error": _STR_OR_NULL,
                "flows": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["flow_id", "title", "selector", "selector_label",
                                     "binding_state", "bound_after_data"],
                        "properties": {
                            "flow_id": _STR,
                            "title": _STR_OR_NULL,
                            "selector": _SELECTOR,
                            "selector_label": _STR,
                            "binding_state": {"type": "string",
                                              "enum": list(BINDING_STATES)},
                            "bound_after_data": _BOOL,
                        },
                        "additionalProperties": False,
                    },
                },
                "unbound_selectors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["slug", "label", "selector"],
                        "properties": {"slug": _STR, "label": _STR, "selector": _SELECTOR},
                        "additionalProperties": False,
                    },
                },
            },
        },
    },
}, ["projects"])

INTEGRITY = _payload("integrity", {
    "project": _STR,
    "config": {
        "type": "object",
        "required": ["state", "error"],
        "properties": {"state": {"type": "string", "enum": ["OK", "ConfigError"]},
                       "error": _STR_OR_NULL},
        "additionalProperties": False,
    },
    "registry": {
        "type": "object",
        "required": ["state", "error"],
        "properties": {"state": {"type": "string", "enum": ["OK", "RegistryDrift"]},
                       "error": _STR_OR_NULL},
        "additionalProperties": False,
    },
    "ledgers": {
        "type": "object",
        "additionalProperties": {
            "type": "object",
            "required": ["rows", "torn_tail", "error"],
            "properties": {"rows": _INT, "torn_tail": _BOOL, "error": _STR_OR_NULL},
            "additionalProperties": False,
        },
    },
    "invalid_flows": {"type": "array", "items": _STR},
    "ledger_repairs": _INT,
    "orphans": _INT_OR_NULL,
    "instruments": {"type": "array", "items": _STR},
    "code": {
        "type": "object",
        "required": ["revision", "dirty", "grobid_image"],
        "properties": {"revision": _STR_OR_NULL,
                       "dirty": {"type": ["boolean", "null"]},
                       "grobid_image": _STR},
        "additionalProperties": False,
    },
}, ["project", "config", "registry", "ledgers", "invalid_flows", "ledger_repairs",
    "orphans", "instruments", "code"])

ACTIVITY = _payload("activity", {
    "project": _STR,
    "activity": {"type": "array", "items": _ACTIVITY_ROW},
}, ["project", "activity"])

POLL = _payload("poll", {
    "project": _STR,
    "ledgers": {
        "type": "object",
        "additionalProperties": {
            "type": "object",
            "required": ["mtime", "rows"],
            "properties": {"mtime": _STR_OR_NULL, "rows": _INT_OR_NULL},
            "additionalProperties": False,
        },
    },
    "running": {"type": "array", "items": _STR},
    "pid_note": _STR,
}, ["project", "ledgers", "running", "pid_note"])

SUMMARY = _payload("summary", {
    "project": _STR,
    "flow_id": _STR_OR_NULL,
    "selector": _SELECTOR,
    "selector_label": _STR,
    "floor_status": _STR_OR_NULL,
    "verdicts": _VERDICT_COUNTS,
    "inbox_counts": {"type": "object", "additionalProperties": _INT},
}, ["project", "flow_id", "selector", "selector_label", "floor_status", "verdicts",
    "inbox_counts"])

OVERVIEW = _payload("overview", {
    "project": _STR,
    "selector": _SELECTOR,
    "selector_label": _STR,
    "flow": {"type": ["object", "null"]},
    "legacy": _BOOL,
    "binding_state": {
        "type": ["object", "null"],
        "required": ["state", "differences", "bound_after_data"],
        "properties": {"state": {"type": "string", "enum": list(BINDING_STATES)},
                       "differences": {"type": "array", "items": _STR},
                       "bound_after_data": _BOOL},
        "additionalProperties": False,
    },
    "state": {
        # `round_state.RoundState.as_dict`, named keys only: the strip's numbers.
        "type": "object",
        "required": ["project", "round", "stages", "questions", "verdicts_recorded",
                     "verdicts_stale", "floor", "rejections_by_reason", "unavailable",
                     "errors"],
        "properties": {
            "project": _STR,
            "round": _STR_OR_NULL,
            "stages": {"type": "array", "items": {"type": "object"}},
            "questions": {"type": "array", "items": {"type": "object"}},
            "verdicts_recorded": _INT,
            "verdicts_stale": _INT,
            "floor": {"type": ["object", "null"]},
            "rejections_by_reason": {"type": "object"},
            "unavailable": _STR,
            "errors": {"type": "array", "items": _STR},
        },
        "additionalProperties": False,
    },
    "floor_panel": {
        "type": ["object", "null"],
        "required": ["overall", "by_class", "sentences", "disclosure"],
        "properties": {"overall": {"type": "object"}, "by_class": {"type": "object"},
                       "sentences": {"type": "array", "items": _STR},
                       "disclosure": _STR},
        "additionalProperties": False,
    },
    "questions": {
        "type": "object",
        "required": ["rows", "round", "project"],
        "properties": {"rows": {"type": "array", "items": _QUESTION_ROW},
                       "round": _STR_OR_NULL, "project": _STR},
        "additionalProperties": False,
    },
    # §8.3: both are decided server-side so the client never derives meaning (F11). A damaged
    # ledger fails the route with the LEDGER_CORRUPT envelope before either field is built.
    "question_state_counts": {
        "type": "object",
        "required": list(QUESTION_STATES),
        "properties": {state: _INT for state in QUESTION_STATES},
        "additionalProperties": False,
    },
    "source_tracker": {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["candidate_key", "source_id", "source_class", "state", "tooltip"],
            "properties": {
                "candidate_key": _STR,
                "source_id": _STR_OR_NULL,
                "source_class": _STR,
                "state": {"type": "string", "enum": list(TRACKER_STATES)},
                "tooltip": _STR,
            },
            "additionalProperties": False,
        },
    },
    "inbox": {"type": "array", "items": _CARD},
    "activity": {"type": "array", "items": _ACTIVITY_ROW},
    "unavailable": _STR,
    "errors": {"type": "array", "items": _STR},
}, ["project", "selector", "selector_label", "flow", "legacy", "binding_state", "state",
    "floor_panel", "questions", "question_state_counts", "source_tracker", "inbox", "activity",
    "unavailable", "errors"])

INBOX = _payload("inbox", {
    "cards": {"type": "array", "items": _CARD},
}, ["cards"])

QUESTION_DETAIL = _payload("question detail", {
    "project": _STR,
    "selector": _SELECTOR,
    "id": _STR,
    "kind": _STR,
    "text": _STR,
    "profile": {"type": "object"},
    "profile_fields": {
        "type": "object",
        "required": ["state", "provisional", "blocking", "coverage", "direction_count",
                     "direction_count_note", "gate_rejected", "reviewed_not_usable",
                     "awaiting_review", "linkage", "extraction", "profile_sha256",
                     "stored_profile_stale", "unavailable"],
        "properties": {
            "state": _STR_OR_NULL,
            "provisional": {"type": ["boolean", "null"]},
            "blocking": {"type": "array", "items": _STR},
            "coverage": {"type": "object"},
            "direction_count": {"type": "object"},
            "direction_count_note": _STR,
            "gate_rejected": {"type": "object"},
            "reviewed_not_usable": {"type": "object"},
            "awaiting_review": _INT,
            "linkage": {},
            "extraction": {"type": ["object", "null"]},
            "profile_sha256": _STR_OR_NULL,
            "stored_profile_stale": _BOOL,
            "unavailable": _STR,
        },
        "additionalProperties": False,
    },
    "results": {"type": "array", "items": {"type": "object"}},
    # The recorded adjudication row itself, or null: the UI renders the word, who signed and
    # when — `adjudicate` is the only verdict-producing call and its row is the evidence.
    "verdict": {
        "type": ["object", "null"],
        # Every field of an adjudications.jsonl row (docs/contracts/profiles.md). Measured: a real
        # signature carries all eleven, and listing six under additionalProperties: false made
        # the first signed verdict fail the contract.
        "required": ["question_id", "round", "manifest_only", "verdict", "rationale",
                     "profile_sha256", "decision_contract_version", "registry_version",
                     "registry_sha256", "adjudicated_by", "adjudicated_at"],
        "properties": {
            "question_id": _STR,
            "round": _STR_OR_NULL,
            "manifest_only": _BOOL,
            "verdict": {"type": "string", "enum": list(VERDICTS)},
            "rationale": _STR,
            "profile_sha256": _STR,
            "decision_contract_version": {"type": ["integer", "null"]},
            "registry_version": {"type": ["integer", "null"]},
            "registry_sha256": _STR_OR_NULL,
            "adjudicated_by": _STR,
            "adjudicated_at": _STR,
        },
        "additionalProperties": False,
    },
    "verdict_stale": _BOOL,
    # The next signing action, decided once on the server (the inbox's ADJUDICATION card), or
    # null when nothing can be signed. The page renders it verbatim and never builds one.
    "adjudication_card": {**_CARD, "type": ["object", "null"]},
    "operational_not_applicable": _BOOL,
    "not_applicable_state": _STR_OR_NULL,
}, ["project", "selector", "id", "kind", "text", "profile", "profile_fields", "results",
    "verdict", "verdict_stale", "operational_not_applicable", "not_applicable_state", "adjudication_card"])

# One side of the diff: the stored profile's identity and the instrument versions that
# decided its contents, so a re-extraction under a new gate never reads as the literature
# having moved.
_DIFF_SIDE = {
    "type": "object",
    "required": ["profile_sha256", "built_at", "claim_gate_version",
                 "decision_contract_version", "registry_version"],
    "properties": {
        "profile_sha256": _STR,
        "built_at": _STR,
        "claim_gate_version": _INT,
        "decision_contract_version": _INT,
        "registry_version": _INT,
    },
    "additionalProperties": False,
}

# The per-relation and per-direction counts of one stored profile, exactly as the ledger
# holds them: by_class values are per source class and the engine owns no closed list.
_DIFF_COUNTS = {
    "type": "object",
    "required": ["by_class", "direction_count"],
    "properties": {
        "by_class": {"type": "object"},
        "direction_count": {"type": "object", "additionalProperties": _INT},
    },
    "additionalProperties": False,
}

PROFILE_DIFF = _payload("profile diff", {
    "project": _STR,
    "selector": _SELECTOR,
    "id": _STR,
    "from": _DIFF_SIDE,
    "to": _DIFF_SIDE,
    # The reason the rows record, when they record one (a changed instrument version); no
    # invented narrative otherwise.
    "reason": _STR_OR_NULL,
    "summary": {
        "type": "object",
        "required": ["added", "removed", "changed"],
        "properties": {"added": _INT, "removed": _INT, "changed": _INT},
        "additionalProperties": False,
    },
    # Keyed by `result_id` (the claim id): pass-through profile result rows stay open,
    # like `results` above — their vocabulary is the kind's field list, not this API's.
    "added": {"type": "array", "items": {"type": "object"}},
    "removed": {"type": "array", "items": {"type": "object"}},
    "changed": {"type": "array", "items": {"type": "object"}},
    "counts": {
        "type": "object",
        "required": ["from", "to"],
        "properties": {"from": _DIFF_COUNTS, "to": _DIFF_COUNTS},
        "additionalProperties": False,
    },
}, ["project", "selector", "id", "from", "to", "reason", "summary", "added", "removed",
    "changed", "counts"])

LINEAGE = _payload("lineage", {
    "project": _STR,
    "selector": _SELECTOR,
    "claim_id": _STR,
    "source_id": _STR,
    "steps": {
        "type": "object",
        "required": ["claim", "review", "chunk", "document", "document_pdf_instrument",
                     "acquisition", "acquisition_candidate_key", "candidate"],
        "properties": {
            "claim": {"type": "object"},
            "review": {"type": ["object", "null"]},
            "chunk": {
                "type": ["object", "null"],
                "required": ["chunk_id", "generation_sha256", "text_sha256", "text",
                             "evidence_quote", "quote_found"],
                "properties": {
                    "chunk_id": _STR,
                    "generation_sha256": _STR_OR_NULL,
                    "text_sha256": _STR_OR_NULL,
                    "text": _STR_OR_NULL,
                    "evidence_quote": _STR,
                    "quote_found": _BOOL,
                },
                "additionalProperties": False,
            },
            "document": {"type": ["object", "null"]},
            "document_pdf_instrument": _STR_OR_NULL,
            # The collapsed acquisition, with every attempt's failure class rendered
            # display-ready (F19): `failure_display` is what the UI shows, verbatim.
            "acquisition": {
                "type": ["object", "null"],
                "required": ["attempts"],
                "properties": {
                    "attempts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["url", "http_status", "failure_display",
                                         "fetch_version"],
                            "properties": {
                                "url": _STR_OR_NULL,
                                "http_status": _INT_OR_NULL,
                                "failure_display": _FAILURE_DISPLAY,
                                "fetch_version": _INT,
                            },
                        },
                    },
                },
            },
            "acquisition_candidate_key": _STR_OR_NULL,
            "candidate": {"type": ["object", "null"]},
        },
        "additionalProperties": False,
    },
}, ["project", "selector", "claim_id", "source_id", "steps"])

SOURCE_DOSSIER = _payload("source dossier", {
    "project": _STR,
    "selector": _SELECTOR,
    "candidate_key": _STR,
    "source_id": _STR,
    "candidate": {"type": ["object", "null"]},
    # Every acquisition row in ledger order (§4.11), each attempt carrying its display-ready
    # failure class (F19) — the UI never re-derives it from `failure_class`.
    "acquisitions": {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["attempts"],
            "properties": {
                "attempts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["url", "http_status", "failure_display",
                                     "fetch_version"],
                        "properties": {
                            "url": _STR_OR_NULL,
                            "http_status": _INT_OR_NULL,
                            "failure_display": _FAILURE_DISPLAY,
                            "fetch_version": _INT,
                        },
                    },
                },
            },
        },
    },
    "counted_acquisition": {"type": ["object", "null"]},
    "document": {"type": ["object", "null"]},
    "active_chunks": _INT_OR_NULL,
    "advisory": {"type": "object",
                 "additionalProperties": {"type": "array", "items": {"type": "object"}}},
    "advisory_note": _STR,
    "claims_by_question": {"type": "object", "additionalProperties": _INT},
}, ["project", "selector", "candidate_key", "source_id", "candidate", "acquisitions",
    "counted_acquisition", "document", "active_chunks", "advisory", "advisory_note",
    "claims_by_question"])

ERROR = _payload("error", {
    "error": {
        "type": "object",
        "required": ["code", "message"],
        "properties": {"code": {"type": "string", "enum": list(ERROR_CODES)},
                       "message": _STR},
        "additionalProperties": False,
    },
}, ["error"])

# The §3.2 routes by name. `flows/{flow_id}` and `unbound/{slug}` serve the same payload
# shape per tail, so one schema covers both selector kinds.
ROUTES: dict[str, dict[str, Any]] = {
    "/meta": META,
    "/projects": PROJECTS,
    "/admin": ADMIN,
    "/projects/{p}/integrity": INTEGRITY,
    "/projects/{p}/activity": ACTIVITY,
    "/projects/{p}/poll": POLL,
    "/projects/{p}/{sel}/summary": SUMMARY,
    "/projects/{p}/{sel}/overview": OVERVIEW,
    "/projects/{p}/{sel}/inbox": INBOX,
    "/projects/{p}/{sel}/questions/{qid}": QUESTION_DETAIL,
    "/projects/{p}/{sel}/questions/{qid}/profile-diff": PROFILE_DIFF,
    "/projects/{p}/{sel}/claims/{claim_id}": LINEAGE,
    "/projects/{p}/{sel}/sources/{candidate_key}": SOURCE_DOSSIER,
    "/error": ERROR,
}


def document() -> dict[str, Any]:
    """The whole contract as one draft-2020-12 schema whose properties are the routes:
    `json-schema-to-typescript` (S4) reads it directly, and `additionalProperties: false`
    makes an undeclared route a build failure rather than a silent gap."""
    return {
        "$schema": DRAFT,
        "title": "Claimstone portal API v1",
        "type": "object",
        "required": sorted(ROUTES),
        "properties": {name: ROUTES[name] for name in sorted(ROUTES)},
        "additionalProperties": False,
    }
