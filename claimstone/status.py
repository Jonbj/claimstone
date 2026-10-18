"""What Crossref says about a work after it was published: notices, licences, text-mining links (D142).

A quote that survives the gate can come from a paper that was later retracted or corrected. The quote is
still an exact substring of the text we read, so nothing in the pipeline notices. This module records,
append-only, what Crossref reported at a moment, so the portal can show it and a person can decide.

What it never does:

* It does not delete, reject or down-weight a claim. A notice is shown beside the evidence; a person reads it.
* It does not treat silence as a clean bill. `NO_NOTICE_RECORDED` means *Crossref had no notice when asked*,
  and the portal says exactly that — not "not retracted". `LOOKUP_FAILED` is a third thing and is never
  folded into either (the same discipline as the five verdict states).
* It does not infer permission. A `licence` or a TDM `link` is the publisher's metadata; whether text-mining
  is permitted is a separate decision (issue #9, the PMC route, is the same lesson).

Two requests per DOI, one host (`api.crossref.org`): the work record, and the records that *update* it
(`filter=updates:<doi>`), because a retraction is a separate record pointing at the original and the original's
own record may not carry it. The shape of both answers is parsed defensively and the raw bytes are kept by the
recording fetcher, so a field Crossref renames shows up as a notice-less row we can re-parse, not as a crash.
"""

from __future__ import annotations

import datetime as _dt
import urllib.parse
from typing import Any, Iterable

STATUS_VERSION = 1
LEDGER = "status_observations.jsonl"

NOTICE_RECORDED = "NOTICE_RECORDED"
NO_NOTICE_RECORDED = "NO_NOTICE_RECORDED"
LOOKUP_FAILED = "LOOKUP_FAILED"
STATES = (NOTICE_RECORDED, NO_NOTICE_RECORDED, LOOKUP_FAILED)

# Update types that withdraw or question the work, as against ones that fix it. The vocabulary is
# Crossmark's; an unrecognised type is kept verbatim and treated as `other`, never dropped.
WITHDRAWING = frozenset({"retraction", "withdrawal", "removal", "expression_of_concern"})
CORRECTING = frozenset({"correction", "corrigendum", "erratum", "addendum", "clarification",
                        "new_edition", "new_version", "updated_version"})


def kind_of(update_type: str) -> str:
    text = (update_type or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in WITHDRAWING:
        return "withdrawing"
    if text in CORRECTING:
        return "correcting"
    return "other"


def work_url(doi: str) -> str:
    from claimstone import net

    return (f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='/')}?"
            + urllib.parse.urlencode({"mailto": net.contact_email()}))


def updates_url(doi: str) -> str:
    from claimstone import net

    return "https://api.crossref.org/works?" + urllib.parse.urlencode({
        "filter": f"updates:{doi}", "rows": 20, "mailto": net.contact_email(),
        "select": "DOI,type,update-to,title,issued"})


def _date(value: Any) -> str | None:
    parts = ((value or {}).get("date-parts") or [[None]])[0] if isinstance(value, dict) else None
    if not parts or parts[0] is None:
        return None
    return "-".join(f"{int(p):02d}" if i else str(int(p)) for i, p in enumerate(parts))


def parse_work(payload: Any) -> dict[str, Any]:
    """Licences, text-mining links and any `updated-by` entries of one work record."""
    message = (payload or {}).get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        return {"licences": [], "tdm_links": [], "notices": []}
    licences = [{"url": item.get("URL"), "content_version": item.get("content-version"),
                 "start": _date(item.get("start"))}
                for item in message.get("license") or [] if isinstance(item, dict)]
    tdm = [{"url": item.get("URL"), "content_type": item.get("content-type"),
            "intended_application": item.get("intended-application")}
           for item in message.get("link") or []
           if isinstance(item, dict) and item.get("intended-application") == "text-mining"]
    notices = [{"type": item.get("type"), "label": item.get("label"), "doi": item.get("DOI"),
                "source": item.get("source"), "updated": _date(item.get("updated")), "via": "updated-by"}
               for item in message.get("updated-by") or [] if isinstance(item, dict)]
    return {"licences": licences, "tdm_links": tdm, "notices": notices}


def parse_updates(payload: Any, doi: str) -> list[dict[str, Any]]:
    """Notice records that name `doi` in their own `update-to`; each is one notice about it."""
    message = (payload or {}).get("message") if isinstance(payload, dict) else None
    items = (message or {}).get("items") if isinstance(message, dict) else None
    out: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        for target in item.get("update-to") or []:
            if isinstance(target, dict) and str(target.get("DOI") or "").lower() == doi.lower():
                out.append({"type": target.get("type"), "label": target.get("label"),
                            "doi": item.get("DOI"), "source": target.get("source"),
                            "updated": _date(target.get("updated")), "via": "updates-filter"})
    return out


def merge_notices(*groups: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple] = set()
    merged = []
    for group in groups:
        for notice in group:
            key = (str(notice.get("type") or "").lower(), str(notice.get("doi") or "").lower())
            if key in seen:
                continue
            seen.add(key)
            merged.append({**notice, "kind": kind_of(str(notice.get("type") or ""))})
    return merged


def observation(candidate_key: str, doi: str, *, work: Any, updates: Any, work_ok: bool, updates_ok: bool,
                campaign: str | None = None, observed_at: str | None = None) -> dict[str, Any]:
    """One ledger row. A lookup that did not complete is `LOOKUP_FAILED`, never a quiet `NO_NOTICE_RECORDED`."""
    parsed = parse_work(work) if work_ok else {"licences": [], "tdm_links": [], "notices": []}
    notices = merge_notices(parsed["notices"], parse_updates(updates, doi) if updates_ok else [])
    if not (work_ok and updates_ok) and not notices:
        state = LOOKUP_FAILED
    else:
        state = NOTICE_RECORDED if notices else NO_NOTICE_RECORDED
    return {
        "status_version": STATUS_VERSION, "candidate_key": candidate_key, "doi": doi, "state": state,
        "notices": notices, "withdrawing": any(n["kind"] == "withdrawing" for n in notices),
        "licences": parsed["licences"], "tdm_links": parsed["tdm_links"],
        "work_ok": work_ok, "updates_ok": updates_ok, "campaign": campaign,
        "observed_at": observed_at or _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }


def latest(store) -> dict[str, dict[str, Any]]:
    """The newest observation per candidate; an absent ledger is an empty answer, not an error."""
    try:
        return store.latest_by(LEDGER, "candidate_key")
    except FileNotFoundError:
        return {}
