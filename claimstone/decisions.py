"""Operator decisions the portal records: identity, retry campaigns, purchase offers (spec B8).

`decisions.jsonl` is append-only. A decision is one `decision_id` and its rows; the latest row is
its state. Nothing here executes work. A retry campaign approved here is a record of who approved
which candidates, hosts and limits. It becomes work only when an authorized operation (B12) or the
CLI names it. A purchase is completed outside Claimstone. Possession is established only by a file
that passes intake (B7b), never by a button.

Three rules keep the decisions honest:
- **No inference from status codes.** A 403 is an access refusal; an offer exists only when an
  operator records one they verified.
- **No ranking by findings (F13).** The open-decisions list is ordered by whether the decision is
  required, then by acquisition metadata, then by age. Nothing derived from claims, reviews or
  stances is read, so acquiring by expected outcome cannot happen here.
- **No silent merge.** An identity answer records a relation with a reason. `version_of` never makes
  two works one, and never makes a version's file the candidate's copy.
"""

from __future__ import annotations

import datetime as _dt
import re
import secrets
import urllib.parse
from decimal import Decimal, InvalidOperation
from typing import Any

from claimstone import admissibility, intake, net, scope
from claimstone.store import Store

DECISION_VERSION = 1

LEDGER = "decisions.jsonl"

IDENTITY_ANSWERS = ("same_work", "version_of", "different", "not_sure")
MIN_REASON_CHARS = 20

OFFER_STAGES_BY_HAND = ("approved", "bought_externally", "declined")
MAX_CAMPAIGN_REQUESTS = 50
CAMPAIGN_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


class DecisionRefused(ValueError):
    """A request the decision rules refuse; the message is the reason."""


class Conflict(DecisionRefused):
    """A request valid in form but not in the decision's current state."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _base(kind: str, flow_id: str, *, actor: str, code_revision: str | None,
          decision_id: str | None = None) -> dict[str, Any]:
    return {"decision_version": DECISION_VERSION,
            "decision_id": decision_id or secrets.token_hex(12),
            "kind": kind, "flow_id": str(flow_id), "actor": actor,
            "signer_auth": "portal-session", "code_revision": code_revision,
            "recorded_at": _now()}


def latest(store: Store) -> dict[str, dict[str, Any]]:
    """decision_id -> its latest row, in first-recorded order."""
    out: dict[str, dict[str, Any]] = {}
    for row in store.read(LEDGER):
        out[str(row.get("decision_id"))] = dict(row)
    return out


def _reason(text: Any, *, required: bool) -> str:
    if text is None and not required:
        return ""
    if not isinstance(text, str):
        raise DecisionRefused("reason must be text")
    trimmed = text.strip()
    if required and len(trimmed) < MIN_REASON_CHARS:
        raise DecisionRefused(
            f"a reason of {len(trimmed)} characters is below {MIN_REASON_CHARS}: a decision "
            "another person will read needs its grounds")
    return trimmed


# --- identity ---------------------------------------------------------------------------------------


def resolve_identity(store: Store, project: Any, flow_row: dict[str, Any], selector: scope.Selector,
                     *, intake_id: str, answer: str, reason: Any, actor: str,
                     code_revision: str | None) -> dict[str, Any]:
    """A person's answer to a POSSIBLE_VERSION intake item. Both records are kept either way.

    - `same_work`: a reference becomes a DUPLICATE of the candidate; a file becomes the candidate's
      copy through the same acceptance as a file whose title was found (identity now by a person);
    - `version_of`: the relation is recorded; a reference is not a new work, a file is not the
      candidate's copy; the count of independent studies does not change;
    - `different`: a reference is routed again as a new work; a file is rejected for this candidate;
    - `not_sure`: recorded, and the item stays POSSIBLE_VERSION.
    """
    if answer not in IDENTITY_ANSWERS:
        raise DecisionRefused(f"answer must be one of {', '.join(IDENTITY_ANSWERS)}")
    grounds = _reason(reason, required=answer != "not_sure")
    flow_id = str(flow_row["flow_id"])
    with store.writer_lock():
        item = intake.latest(store).get(str(intake_id))
        if item is None or item.get("flow_id") != flow_id:
            raise LookupError(f"no intake item {intake_id} in this flow")
        if item.get("state") != "POSSIBLE_VERSION":
            raise Conflict(f"intake item {intake_id} is {item.get('state')}, not POSSIBLE_VERSION")
        candidate_key = str((item.get("links") or {}).get("candidate_key"))
        decision = {**_base("identity", flow_id, actor=actor, code_revision=code_revision),
                    "state": "recorded", "intake_id": str(intake_id),
                    "candidate_key": candidate_key, "answer": answer, "reason": grounds}
        store.append(LEDGER, decision)
    if answer == "not_sure":
        return {"decision": decision, "intake": item}
    if item.get("kind") == "file":
        if answer == "same_work":
            updated = intake.accept_file(store, project, flow_row, selector, item=item,
                                         identity_by=decision["decision_id"])
        else:
            updated = intake.restate(store, item, state="REJECTED", stage="identity",
                                     reason=("a person answered: a version of the candidate, not "
                                             "its copy; recorded, not counted"
                                             if answer == "version_of" else
                                             "a person answered: a different work, not a copy of "
                                             "this candidate"),
                                     decision_id=decision["decision_id"])
    else:
        if answer == "same_work":
            updated = intake.restate(store, item, state="DUPLICATE", stage="identity",
                                     reason="a person answered: the same work as the candidate; "
                                            "it adds no new work",
                                     decision_id=decision["decision_id"])
        elif answer == "version_of":
            updated = intake.restate(store, item, state="DUPLICATE", stage="identity",
                                     reason="a person answered: a version of the candidate; the "
                                            "relation is recorded and the study count is unchanged",
                                     decision_id=decision["decision_id"])
        else:
            updated = intake.reroute(store, project, flow_row, selector, item=item,
                                     decision_id=decision["decision_id"])
    return {"decision": decision, "intake": updated}


# --- retry campaigns ---------------------------------------------------------------------------------


def retry_preview(store: Store, project: Any, selector: scope.Selector,
                  candidate_keys: list[str]) -> dict[str, Any]:
    """The exact plan a retry campaign over these candidates would approve, built from what was
    recorded: each candidate's last outcome and the hosts its attempts reached. A host that is
    excluded is never in a plan; a host whose failure budget is exhausted is listed as refused,
    because the next fetch would refuse it too (F6)."""
    if not candidate_keys:
        raise DecisionRefused("name at least one candidate")
    scoped = scope.candidates(store, selector)
    collapsed = admissibility.collapse(store)
    excluded = {h.lower() for h in project.excluded_hosts}
    budget = net.Fetcher.max_403_per_host
    items, hosts, refused = [], set(), {}
    for key in candidate_keys:
        candidate = scoped.get(str(key))
        if candidate is None:
            raise LookupError(f"no candidate {key} in this flow")
        row = collapsed.get(str(key))
        if row is not None and row.get("acquired"):
            raise Conflict(f"candidate {key} already has a copy; there is nothing to retry")
        reached = sorted({net.host_of(str(a.get("url") or "")) for a in (row or {}).get("attempts") or []}
                         - {""})
        if not reached and candidate.get("url"):
            reached = [net.host_of(str(candidate["url"]))]
        usable = []
        for host in reached:
            if host in excluded or any(host.endswith("." + e) for e in excluded):
                refused[host] = "excluded host for this project: never contacted"
            elif net.recorded_host_failures(store, host) >= budget:
                refused[host] = (f"failure budget exhausted ({budget} recorded failures in 48 h): "
                                 "the next fetch would refuse it")
            else:
                usable.append(host)
        hosts.update(usable)
        items.append({"candidate_key": str(key), "source_id": candidate.get("source_id"),
                      "source_class": candidate.get("source_class"),
                      "last_failure": (row or {}).get("failure_class") or "NOT_ATTEMPTED",
                      "hosts": usable})
    return {"candidates": items, "hosts": sorted(hosts), "refused_hosts": refused,
            "robots": "honoured", "max_requests_cap": MAX_CAMPAIGN_REQUESTS,
            "executes": "nothing: an approval is a record until an authorized operation names it"}


def approve_retry(store: Store, project: Any, flow_row: dict[str, Any], selector: scope.Selector,
                  *, candidate_keys: list[str], campaign: Any, max_requests: Any, actor: str,
                  code_revision: str | None) -> dict[str, Any]:
    if not isinstance(campaign, str) or not CAMPAIGN_NAME.match(campaign) or campaign == "routine":
        raise DecisionRefused("campaign must be a new name: 3-64 of a-z 0-9 . _ -, not 'routine'")
    if type(max_requests) is not int or not 1 <= max_requests <= MAX_CAMPAIGN_REQUESTS:
        raise DecisionRefused(f"max_requests must be an integer from 1 to {MAX_CAMPAIGN_REQUESTS}")
    with store.writer_lock():
        plan = retry_preview(store, project, selector, candidate_keys)
        if not plan["hosts"]:
            raise Conflict("no host in this plan may be contacted; nothing to approve")
        taken = {row.get("campaign") for row in latest(store).values()
                 if row.get("kind") == "retry_campaign"}
        if campaign in taken:
            raise Conflict(f"campaign {campaign} is already recorded")
        row = {**_base("retry_campaign", str(flow_row["flow_id"]), actor=actor,
                       code_revision=code_revision),
               "state": "approved", "campaign": campaign, "max_requests": max_requests,
               "plan": plan}
        store.append(LEDGER, row)
    return row


# --- purchase offers ---------------------------------------------------------------------------------


def _offer_fields(body: dict[str, Any]) -> dict[str, Any]:
    vendor = body.get("vendor")
    if not isinstance(vendor, str) or not vendor.strip():
        raise DecisionRefused("vendor must be named")
    try:
        price = Decimal(str(body.get("price")))
    except (InvalidOperation, ValueError):
        raise DecisionRefused("price must be a decimal number") from None
    if not price.is_finite() or price <= 0:
        raise DecisionRefused("price must be positive")
    currency = body.get("currency")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise DecisionRefused("currency must be a three-letter ISO code, e.g. EUR")
    terms = body.get("terms_url")
    parts = urllib.parse.urlsplit(terms) if isinstance(terms, str) else None
    if parts is None or parts.scheme not in ("http", "https") or not parts.hostname:
        raise DecisionRefused("terms_url must be the http(s) page of the offer's terms")
    try:
        verified = _dt.datetime.fromisoformat(str(body.get("verified_at")))
    except ValueError:
        raise DecisionRefused("verified_at must be an ISO date-time") from None
    if verified.tzinfo is None:
        raise DecisionRefused("verified_at must carry a time zone")
    if verified > _dt.datetime.now(_dt.timezone.utc):
        raise DecisionRefused("verified_at cannot be in the future")
    work_version = body.get("work_version")
    if not isinstance(work_version, str) or not work_version.strip():
        raise DecisionRefused("work_version must say which version is offered")
    resolves = body.get("resolves")
    if not isinstance(resolves, str) or not resolves.strip():
        raise DecisionRefused("resolves must say what the copy might help resolve")
    tax = body.get("tax_status")
    if tax is not None and not isinstance(tax, str):
        raise DecisionRefused("tax_status must be text when given")
    return {"vendor": vendor.strip(), "price": str(price), "currency": currency,
            "tax_status": tax, "terms_url": terms, "verified_at": verified.isoformat(),
            "work_version": work_version.strip(), "resolves": resolves.strip()}


OFFER_TERMS = ("vendor", "price", "currency", "tax_status", "terms_url", "work_version")


def record_offer(store: Store, flow_row: dict[str, Any], selector: scope.Selector, *,
                 body: dict[str, Any], actor: str, code_revision: str | None) -> dict[str, Any]:
    """Record an offer the operator verified. A changed offer for the same candidate is a new
    offer; the old one becomes `obsolete`, linked, and any approval it had does not carry over."""
    candidate_key = body.get("candidate_id")
    fields = _offer_fields(body)
    flow_id = str(flow_row["flow_id"])
    with store.writer_lock():
        if str(candidate_key) not in scope.candidates(store, selector):
            raise LookupError(f"no candidate {candidate_key} in this flow")
        held = admissibility.collapse(store).get(str(candidate_key))
        if held is not None and held.get("acquired"):
            raise Conflict(f"candidate {candidate_key} already has a copy; no purchase is needed")
        row = {**_base("purchase_offer", flow_id, actor=actor, code_revision=code_revision),
               "state": "proposed", "candidate_key": str(candidate_key), **fields}
        for previous in latest(store).values():
            if (previous.get("kind") == "purchase_offer"
                    and previous.get("candidate_key") == str(candidate_key)
                    and previous.get("state") not in ("obsolete", "declined")):
                if all(previous.get(k) == row.get(k) for k in OFFER_TERMS):
                    raise Conflict(f"this offer is already recorded as {previous['decision_id']}")
                store.append(LEDGER, {**previous, "state": "obsolete", "recorded_at": _now(),
                                      "actor": actor, "superseded_by": row["decision_id"]})
                row["supersedes"] = previous["decision_id"]
        store.append(LEDGER, row)
    return row


_NEXT_BY_HAND = {"proposed": {"approved", "declined"},
                 "approved": {"bought_externally", "declined"},
                 "bought_externally": set()}


def offer_stage(store: Store, flow_row: dict[str, Any], *, offer_id: str, stage: Any,
                actor: str, code_revision: str | None) -> dict[str, Any]:
    """Move an offer by hand: approve, record the purchase made outside, or decline. Possession
    is never set here."""
    if stage not in OFFER_STAGES_BY_HAND:
        raise DecisionRefused(
            f"stage must be one of {', '.join(OFFER_STAGES_BY_HAND)}; copy_provided and "
            "copy_verified come only from a file that passes intake")
    with store.writer_lock():
        offer = latest(store).get(str(offer_id))
        if (offer is None or offer.get("kind") != "purchase_offer"
                or offer.get("flow_id") != str(flow_row["flow_id"])):
            raise LookupError(f"no purchase offer {offer_id} in this flow")
        allowed = _NEXT_BY_HAND.get(str(offer.get("state")), set())
        if stage not in allowed:
            raise Conflict(f"an offer in state {offer.get('state')} cannot move to {stage}")
        row = {**offer, "state": stage, "actor": actor, "signer_auth": "portal-session",
               "code_revision": code_revision, "recorded_at": _now()}
        store.append(LEDGER, row)
    return row


def possession(store: Store, offer: dict[str, Any]) -> str | None:
    """`copy_verified`, `copy_provided` or None, derived from intake alone: a file for the offer's
    candidate recorded after the purchase was, accepted or not."""
    if offer.get("state") != "bought_externally":
        return None
    after = str(offer.get("recorded_at"))
    files = [row for row in intake.latest(store).values()
             if row.get("kind") == "file"
             and (row.get("links") or {}).get("candidate_key") == offer.get("candidate_key")
             and str(row.get("recorded_at")) >= after]
    if any(row.get("state") in ("COUNTED", "REPORTED_SEPARATELY") for row in files):
        return "copy_verified"
    return "copy_provided" if files else None


# --- defer, decline, and the open list ---------------------------------------------------------------


_CONSEQUENCE = {
    "retry_campaign": "these candidates stay not obtained; no request is made to their hosts",
    "purchase_offer": "the candidate stays not obtained; nothing is bought",
}


def set_state(store: Store, flow_row: dict[str, Any], *, decision_id: str, state: Any,
              until: Any, reason: Any, actor: str, code_revision: str | None) -> dict[str, Any]:
    """Defer or decline an open decision. The consequence is stated on the row; declined work is
    never executed by anything that reads this ledger."""
    if state not in ("deferred", "declined"):
        raise DecisionRefused("state must be deferred or declined")
    grounds = _reason(reason, required=True)
    if state == "deferred":
        try:
            day = _dt.date.fromisoformat(str(until))
        except ValueError:
            raise DecisionRefused("a deferral needs until: an ISO date") from None
        if day <= _dt.datetime.now(_dt.timezone.utc).date():
            raise DecisionRefused("until must be a future date")
    with store.writer_lock():
        held = latest(store).get(str(decision_id))
        if held is None or held.get("flow_id") != str(flow_row["flow_id"]):
            raise LookupError(f"no decision {decision_id} in this flow")
        if held.get("kind") not in _CONSEQUENCE:
            raise Conflict(f"a {held.get('kind')} decision is answered, not deferred or declined")
        if held.get("state") in ("declined", "obsolete", "bought_externally"):
            raise Conflict(f"a decision in state {held.get('state')} cannot be {state}")
        row = {**held, "state": state, "until": str(until) if state == "deferred" else None,
               "reason": grounds, "consequence": _CONSEQUENCE[held["kind"]], "actor": actor,
               "signer_auth": "portal-session", "code_revision": code_revision,
               "recorded_at": _now()}
        store.append(LEDGER, row)
    return row


def open_items(store: Store, selector: scope.Selector, flow_id: str) -> list[dict[str, Any]]:
    """Everything waiting for a person in this flow, in the F13 order: required before optional,
    then source class and candidate key (acquisition metadata), then age. Nothing derived from
    claims, reviews or stances is read."""
    candidates = scope.candidates(store, selector)
    today = _dt.datetime.now(_dt.timezone.utc).date().isoformat()
    items = []
    for row in intake.latest(store).values():
        if row.get("flow_id") == str(flow_id) and row.get("state") == "POSSIBLE_VERSION":
            key = str((row.get("links") or {}).get("candidate_key"))
            items.append({"type": "identity", "required": True, "id": row["intake_id"],
                          "candidate_key": key, "recorded_at": row.get("recorded_at"),
                          "item": row})
    for row in latest(store).values():
        if row.get("flow_id") != str(flow_id) or row.get("kind") == "identity":
            continue
        state = row.get("state")
        if state in ("declined", "obsolete"):
            continue
        if state == "deferred" and str(row.get("until") or "") > today:
            continue
        if row.get("kind") == "purchase_offer" and state == "bought_externally" \
                and possession(store, row) == "copy_verified":
            continue
        if row.get("kind") == "retry_campaign" and state == "approved":
            continue  # approved: waiting for an operation, not for a person
        key = str(row.get("candidate_key") or "")
        items.append({"type": row["kind"], "required": False, "id": row["decision_id"],
                      "candidate_key": key, "recorded_at": row.get("recorded_at"),
                      "item": {**row, "possession": possession(store, row)}})

    def order(item: dict[str, Any]) -> tuple[Any, ...]:
        candidate = candidates.get(item["candidate_key"]) or {}
        return (not item["required"], str(candidate.get("source_class") or "~"),
                item["candidate_key"], str(item["recorded_at"]))
    return sorted(items, key=order)
