"""Routing and HTML rendering for the read-only, multi-project research portal (spec §4).

The wire rules — GET only, the security headers, the Host/Origin defences with `--allow-host`
and lookup-never-path parameters — live in `claimstone.transport.BaseHandler`, shared with
`claimstone.api` (2026-10-06 design §3.1). One server serves every project under
`--projects-dir` with stores under `--store`; each request reloads the project (F9 — a
long-running server must not serve a stale registry) and rechecks registry drift without
recording, rendering `ConfigError` and `RegistryDrift` as named states.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
from http.server import ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from claimstone import dashboard, flows, portal_state, round_state, scope
from claimstone.config import (ConfigError, check_registry_drift, discover_projects,
                               load_project)
from claimstone.store import Store
from claimstone.transport import LOOPBACK_HOSTS, BaseHandler

from claimstone.dashboard import _STYLE, _chip, _esc, _frac

CSP = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
       "connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; "
       "frame-ancestors 'none'")

BOUND_AFTER_DATA = ("bound after data existed: rows written before binding are not verified "
                    "against this protocol")

_SCRIPT = """
const root=document.documentElement;
const saved=(()=>{try{return localStorage.getItem('cs-theme')}catch(e){return null}})();
const mq=matchMedia('(prefers-color-scheme: light)');
root.dataset.theme=saved||(mq.matches?'light':'dark');
document.getElementById('tgl').onclick=()=>{const t=root.dataset.theme==='dark'?'light':'dark';
root.dataset.theme=t;try{localStorage.setItem('cs-theme',t)}catch(e){}};
"""


def _poll_script(project_name: str) -> str:
    """The dashboard's polling approach at the portal's 3 s cadence: reload when the ledger
    signature moved and the page is visible. No SSE, no WebSocket (spec §4.12)."""
    return (
        f"const POLL='{_esc('/api/poll?project=' + project_name)}';\n"
        "let last=null;\n"
        "async function poll(){try{const r=await fetch(POLL);const j=await r.json();"
        "const sig=JSON.stringify(j.ledgers);"
        "if(last!==null&&sig!==last&&document.visibilityState==='visible'){location.reload();return}"
        "last=sig;}catch(e){}}\n"
        "setInterval(poll,3000);poll();\n"
    )


def _page(title: str, breadcrumb: list[tuple[str, str]], body: str,
          revision: str | None, dirty: bool | None,
          poll_project: str | None = None) -> str:
    crumbs = ' <span class="frac">/</span> '.join(
        f'<a href="{_esc(href)}">{_esc(label)}</a>' if href else _esc(label)
        for label, href in breadcrumb)
    code = f"{revision[:12]}" if revision else "unknown"
    dirt = " · dirty tree" if dirty else ""
    script = _SCRIPT + (_poll_script(poll_project) if poll_project else "")
    return f"""<!doctype html>
<html lang="en" data-theme="dark">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>claimstone · {_esc(title)}</title><style>{_STYLE}</style></head>
<body>
<header>
  <h1>{crumbs}</h1>
  <span class="meta">read-only derived view · re-read from disk on every request</span>
  <span class="meta">code {_esc(code)}{_esc(dirt)} · at server start</span>
  <button id="tgl" title="light/dark">◐</button>
</header>
<main>
{body}
</main>
<script>{script}</script>
</body></html>"""


def _stage_node(data: dict[str, Any]) -> str:
    """The dashboard's stage node, over the JSON-shaped dict the overview returns."""
    progress = ""
    prog = data.get("progress")
    if prog:
        total = prog.get("total") or 0
        pct = 100.0 * prog.get("done", 0) / total if total else 0
        progress = (f'<div class="meter"><i style="width:{pct:.1f}%"></i></div>'
                    f"{_frac(prog.get('done'), prog.get('total') or None, prog.get('label'))}")
    rejected = (f" · {_esc(data['rejected'])} rejected"
                if data.get("rejected") is not None else "")
    detail = (f'<div class="m" style="color:var(--faint)">{_esc(data.get("detail"))}</div>'
              if data.get("detail") else "")
    outputs = data.get("outputs")
    shown = _esc(outputs if outputs is not None else "—")
    return (f'<div class="node"><div class="n">{_esc(data["name"])}</div>'
            f'<div class="m"><b>{shown}</b> out{rejected}</div>{progress}{detail}</div>')


def _render_overview(page: dict[str, Any]) -> str:
    """The shared body of a flow page and a legacy page."""
    sections: list[str] = []
    flow = page.get("flow")
    state = page.get("state") or {}

    if page.get("legacy"):
        sections.append(
            '<section><h2>binding</h2>'
            '<div class="chip bad"><span class="dot"></span>legacy: protocol not verified</div>'
            f'<p class="note">{_esc(page.get("selector_label") or "")} has data and no flow: '
            "nothing binds it to the protocol it ran under. `claimstone flow create` binds one; "
            "until then its figures are shown, not certified.</p></section>")
    else:
        binding = page.get("binding_state") or {}
        chip = _chip(binding.get("state", "?"),
                     "ok" if binding.get("state") == "CURRENT" else "bad")
        diffs = (", ".join(binding.get("differences") or [])) or "no differences"
        warning = (f'<p class="note">{_esc(BOUND_AFTER_DATA)}</p>'
                   if (flow or {}).get("bound_after_data") else "")
        sections.append(
            f'<section><h2>binding</h2>{chip}'
            f'<p class="note">differs in: {_esc(diffs)}. The binding is compared against the '
            "live project and never supplies a value to a computation (review F4).</p>"
            f"{warning}</section>")

    for error in state.get("errors") or []:
        sections.append(
            '<section><h2>ledger integrity</h2>'
            f'{_chip(error, "bad")}'
            "<p class=\"note\">Figures that depend on a damaged ledger are withheld, not "
            "zero.</p></section>")
    if page.get("unavailable"):
        sections.append(
            '<section><h2>corpus</h2><div class="chip bad"><span class="dot"></span>'
            f"{_esc(page['unavailable'])}</div></section>")

    strip = "".join(_stage_node(stage) for stage in state.get("stages") or [])
    floor_html = _render_floor_panel(page.get("floor_panel"))
    sections.append(
        '<section><h2>the pipeline</h2><div class="strip">' + strip + "</div>"
        '<p class="note">A fraction always shows its denominator; a dash means not knowable in '
        "principle, never zero.</p></section>")
    if floor_html:
        sections.append(floor_html)

    sections.append(_render_matrix(page.get("questions") or {}))
    sections.append(_render_cards(page.get("inbox") or []))

    rows = page.get("activity") or []
    log = "".join(
        f'<div class="r"><span class="w mono">{_esc(row["when"])}</span>'
        f'<span class="s" style="color:var(--teal)">{_esc(row["stage"])}</span>'
        f'<span class="m">{_esc(json.dumps(row["row"], ensure_ascii=False)[:220])}</span></div>'
        for row in rows) or '<div class="note">no rows in this scope</div>'
    sections.append(
        '<section><h2>activity — this scope only</h2><div class="log">' + log + "</div>"
        "<p class=\"note\">Scoped rows carry their own timestamps; rows without one have no "
        "trustworthy time and are not shown.</p></section>")
    return "".join(sections)


def _render_floor_panel(panel: dict[str, Any] | None) -> str:
    if not panel:
        return ""
    overall = panel.get("overall") or {}
    rate = overall.get("rate")
    rate_text = f"{rate:.2f}" if isinstance(rate, (int, float)) else "—"
    status = _chip(str(overall.get("status")), "ok" if overall.get("status") == "OK" else "bad")
    classes = "".join(
        f'<tr><td class="mono">{_esc(name)}</td>'
        f'<td class="num">{_esc(bucket["basis_count"])} / {_esc(bucket["found"])}</td>'
        f'<td class="num">{_esc(bucket["needed"])}</td>'
        f'<td class="num">{_esc(bucket["floor"])}</td>'
        f'<td>{_chip("meets" if bucket.get("meets_floor") else "below", "ok" if bucket.get("meets_floor") else "bad")}</td></tr>'
        for name, bucket in (panel.get("by_class") or {}).items())
    sentences = "".join(f'<p class="note">{_esc(s)}</p>' for s in panel.get("sentences") or [])
    return (
        '<section><h2>floor and deficit</h2>'
        f'<p class="note">{_esc(overall.get("basis"))} {_esc(overall.get("basis_count"))} / '
        f"{_esc(overall.get('found'))} = <b>{_esc(rate_text)}</b> · floor "
        f"{_esc(overall.get('floor'))} · v{_esc(overall.get('floor_version'))} · "
        f"{_esc(overall.get('floor_set_at'))} · {status}"
        + (f"<br>not final: {_esc(', '.join(overall.get('blocking') or []))}"
           if overall.get("blocking") else "")
        + "</p>"
        "<table><thead><tr><th>class</th><th class=\"num\">basis / found</th>"
        "<th class=\"num\">needed</th><th class=\"num\">floor</th><th></th></tr></thead>"
        f"<tbody>{classes}</tbody></table>{sentences}"
        f'<p class="note">{_esc(panel.get("disclosure"))}</p></section>')


def _render_matrix(matrix: dict[str, Any]) -> str:
    rows = []
    for row in matrix.get("rows") or []:
        by_class = " · ".join(f"{_esc(k)} {_esc(v)}" for k, v in
                              (row.get("claims_by_class") or {}).items()) or "—"
        coverage = "— / —" if row["coverage"].get("sources") is None else \
            f"{row['coverage'].get('sources')} / {row['coverage'].get('examined')}"
        counts = row.get("direction_count") or {}
        direction = (" ".join(f"{_esc(k)} {_esc(v)}" for k, v in counts.items())
                     + ' <span class="frac">(a count, not a strength)</span>') if counts else "—"
        if row.get("operational_not_applicable"):
            verdict = ('<span class="chip dashed">LITERATURE_VERDICT_NOT_APPLICABLE</span>'
                       "<br><span class=\"frac\">kind operational: no verdict</span>")
        elif row.get("verdict"):
            verdict = _chip(row["verdict"], dashboard.VERDICT_STYLES.get(row["verdict"], ""))
            if row.get("verdict_stale"):
                verdict += ' <span class="chip bad"><span class="dot"></span>stale</span>'
        elif row.get("state") == "NO_VERIFIED_CLAIM":
            verdict = _chip("NO_VERIFIED_CLAIM", "v-nvc", dashed=True)
        elif row.get("state"):
            verdict = _chip(row["state"], "")
        else:
            verdict = '<span class="chip dashed">— no verdict</span>'
        if row.get("unavailable"):
            verdict += f'<br><span class="frac">historical — {_esc(row["unavailable"])}</span>'
        provisional = ""
        if row.get("provisional"):
            provisional = f'<br><span class="chip warn"><span class="dot"></span>' \
                          f"{_esc(', '.join(row.get('blocking') or []) or 'provisional')}</span>"
        rows.append(
            "<tr>"
            f'<td class="mono">{_esc(row["id"])}</td>'
            f"<td>{_esc(row['text'])}</td><td>{_esc(row['kind'])}</td>"
            f"<td>{_esc(by_class)} <span class=\"frac\">→ {_esc(row.get('claims'))} total</span></td>"
            f'<td class="num">{_esc(coverage)}</td>'
            f"<td>{direction}</td>"
            f'<td class="num">{_esc(row.get("gate_rejected_total"))}</td>'
            f'<td class="num">{_esc(row.get("awaiting_review"))}</td>'
            f"<td>{verdict}{provisional}</td></tr>")
    body = "".join(rows)
    return (
        '<section><h2>the questions — registry order</h2>'
        "<table><thead><tr><th>id</th><th>question</th><th>kind</th>"
        "<th>claims per class</th><th class=\"num\">coverage<br>speaking / examined</th>"
        "<th>direction count</th><th class=\"num\">gate rejected</th>"
        "<th class=\"num\">awaiting review</th><th>verdict</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
        "<p class=\"note\">Claims are counted per class before they are pooled (invariant 6). "
        "NO_VERIFIED_CLAIM is the engine's categorical outcome and never a verdict: only a "
        "person can say <q>never asked</q>. No pooling, no R: a person reads the profile and "
        "signs.</p></section>")


def _render_cards(cards: list[dict[str, Any]]) -> str:
    rows = "".join(
        f'<div class="r"><span class="s" style="color:var(--teal)">{_esc(card["category"])}</span>'
        f'<span class="w mono">{_esc(card["scope"])}</span>'
        f'<span class="m"><b>{_esc(card["subject"])}</b> — {_esc(card["cause"])}'
        + (f'<br><code>{_esc(card["command"])}</code>' if card.get("command") else "")
        + (f'<br><span class="frac">{_esc(card["note"])}</span>' if card.get("note") else "")
        + "</span></div>"
        for card in cards) or '<div class="note">nothing open in this scope</div>'
    return ('<section><h2>inbox — what a person can do next</h2><div class="log">' + rows
            + "</div><p class=\"note\">Commands are text to copy, never buttons: no route here "
              "starts work. Cards sort by category then subject, never by expected result "
              "(review F13).</p></section>")


def _render_index(data: dict[str, Any]) -> str:
    cards = []
    for project in data.get("projects") or []:
        if project.get("config") != "OK":
            cards.append(
                f'<div class="node"><div class="n">{_esc(project["name"])}</div>'
                f'<div class="m"><span class="chip bad"><span class="dot"></span>'
                f"ConfigError</span><br>{_esc(project.get('config_error'))}</div></div>")
            continue
        def verdict_text(entry: dict[str, Any]) -> str:
            counts = entry.get("verdicts")
            if not counts:
                return ""
            return (f" · {counts['awaiting_adjudication']} awaiting a person"
                    f" · {counts['adjudicated']} signed"
                    + (f" · {counts['stale']} stale" if counts.get("stale") else ""))

        name = project["name"]
        flows_html = "".join(
            f'<div class="m">flow <a class="mono" href="/p/{_esc(name)}/f/{_esc(entry["flow_id"])}/">'
            f'{_esc(entry["flow_id"][:12])}</a>'
            f" · {_esc(entry.get('selector_label') or entry['selector'].get('round'))}"
            + f" · {_esc(entry['binding_state'])}"
            + (f" · floor {_esc(entry['floor_status'])}" if entry.get("floor_status") else "")
            + _esc(verdict_text(entry))
            + (f" · {_esc(entry['title'])}" if entry.get("title") else "")
            + "</div>"
            for entry in project.get("flows") or []) or '<div class="m">no flows</div>'
        legacy = "".join(
            f'<div class="m">legacy <a class="mono" href="/p/{_esc(name)}/legacy/'
            f'{_esc(entry["slug"])}/">{_esc(entry["label"])}</a>'
            + (f" · floor {_esc(entry['floor_status'])}" if entry.get("floor_status") else "")
            + _esc(verdict_text(entry))
            + " · <span class=\"chip warn\"><span class=\"dot\"></span>protocol not verified"
            "</span></div>"
            for entry in project.get("legacy_selectors") or [])
        drift = (f'<div class="m"><span class="chip bad"><span class="dot"></span>'
                 f"registry drift</span> {_esc(project['registry_drift'])}</div>"
                 if project.get("registry_drift") else "")
        inbox = (" · ".join(f"{_esc(k)} {_esc(v)}" for k, v in
                            (project.get("inbox_counts") or {}).items())) or "nothing open"
        cards.append(
            f'<div class="node" style="flex-basis:340px"><div class="n">'
            f'<a href="/p/{_esc(project["name"])}/">{_esc(project["name"])}</a></div>'
            f'<div class="m">registry v{_esc(project.get("registry_version"))}'
            f" · {_esc(project.get('registry_sha256'))}</div>{drift}{flows_html}{legacy}"
            f'<div class="m">inbox: {_esc(inbox)}</div></div>')
    body = ('<section><h2>projects</h2><div class="strip">' + "".join(cards) + "</div>"
            '<p class="note">One server, every project, all of it read-only. A round with '
            "candidates and no flow is legacy: protocol not verified.</p></section>")
    return body


def _render_inbox(data: dict[str, Any]) -> str:
    sections = []
    for project in data.get("projects") or []:
        cards = project.get("cards") or []
        rendered = "".join(
            f'<div class="r"><span class="s" style="color:var(--teal)">{_esc(card["category"])}</span>'
            f'<span class="w mono">{_esc(card["scope"])}</span>'
            f'<span class="m"><b>{_esc(card["subject"])}</b> — {_esc(card["cause"])}'
            + (f'<br><code>{_esc(card["command"])}</code>' if card.get("command") else "")
            + (f'<br><span class="frac">{_esc(card["note"])}</span>' if card.get("note") else "")
            + "</span></div>"
            for card in cards) or '<div class="note">nothing open</div>'
        sections.append(
            f'<section><h2>{_esc(project["name"])}</h2><div class="log">{rendered}</div></section>')
    return "".join(sections) or '<section><h2>inbox</h2><div class="note">no projects</div></section>'


def _render_admin(data: dict[str, Any]) -> str:
    credentials = " · ".join(
        f"{_esc(name)}: {'set' if value else 'not set'}"
        for name, value in (data.get("credentials") or {}).items())
    backends = data.get("backends") or {}
    instruments = " · ".join(
        f"{_esc(name)} {_esc(value)}" for name, value in
        sorted((data.get("instruments") or {}).items()))
    return (
        '<section><h2>credentials — presence only</h2>'
        f'<div class="m">{credentials}</div>'
        f'<p class="note">{_esc(data.get("key_rotation_note"))}</p></section>'
        '<section><h2>model backends</h2>'
        f'<div class="m">configured: {_esc(", ".join(backends.get("configured") or []))}</div>'
        f'<div class="m">available: {_esc(", ".join(backends.get("available") or []))}</div>'
        f'<p class="note">{_esc(data.get("backends_note"))}</p></section>'
        '<section><h2>instrument versions</h2>'
        f'<div class="m">{instruments}</div>'
        "<p class=\"note\">Every version the design record must acknowledge; the integrity panel "
        "reports whether it does.</p></section>")


def _render_integrity(data: dict[str, Any]) -> str:
    config = data.get("config") or {}
    registry = data.get("registry") or {}
    code = data.get("code") or {}

    def _state(label: str, entry: dict[str, Any]) -> str:
        chip = _chip(entry.get("state", "?"), "ok" if entry.get("state") == "OK" else "bad")
        error = f'<br><span class="frac">{_esc(entry.get("error"))}</span>' if entry.get("error") else ""
        return f'<div class="m"><b>{_esc(label)}</b> {chip}{error}</div>'

    ledgers = "".join(
        f'<div class="m"><span class="mono">{_esc(name)}</span> · '
        f"{_esc(entry.get('rows'))} rows"
        + (' · <span class="chip warn"><span class="dot"></span>torn tail</span>'
           if entry.get("torn_tail") else "")
        + (f' · <span class="chip bad"><span class="dot"></span>{_esc(entry["error"])}</span>'
           if entry.get("error") else "")
        + "</div>"
        for name, entry in sorted((data.get("ledgers") or {}).items()))
    problems = data.get("instruments") or []
    instrument_chip = _chip("acknowledged" if not problems else "NOT acknowledged",
                            "ok" if not problems else "bad")
    orphans = data.get("orphans")
    orphans_text = "not knowable" if orphans is None else str(orphans)
    return (
        '<section><h2>integrity — can these numbers be trusted now</h2>'
        f"{_state('config', config)}{_state('registry', registry)}"
        f'<div class="m"><b>ledger repairs</b> {_esc(data.get("ledger_repairs"))}</div>'
        f'<div class="m"><b>orphans</b> {_esc(orphans_text)}</div>'
        + "".join(f'<div class="m"><b>invalid flow row</b> <span class="chip bad"><span '
                  f'class="dot"></span>id is not the hash of its binding</span> '
                  f'<span class="mono">{_esc(fid[:16])}</span></div>'
                  for fid in data.get("invalid_flows") or [])
        + f'<div class="m"><b>instruments</b> {instrument_chip}'
        + ("".join(f'<br><span class="frac">{_esc(p)}</span>' for p in problems)) + "</div>"
        f'<div class="m"><b>code</b> {_esc((code.get("revision") or "unknown")[:12])}'
        f"{' · dirty' if code.get('dirty') else ''}"
        f" · grobid {_esc((code.get('grobid_image') or '')[:40])}</div>"
        f"{ledgers}</section>")


def _render_question(page: dict[str, Any], *, base_url: str) -> str:
    fields = page.get("profile_fields") or {}
    coverage = fields.get("coverage") or {}
    direction = fields.get("direction_count") or {}
    results = "".join(
        "<tr>"
        f'<td class="mono"><a href="{base_url}/claim/{_esc(row.get("claim_id"))}">'
        f"{_esc(str(row.get('claim_id'))[:16])}</a></td>"
        f'<td class="mono">{_esc(row.get("source_id"))}</td>'
        f"<td>{_esc(row.get('stance'))}</td>"
        f"<td>{_esc(row.get('estimate_as_written') or row.get('contrast_as_written') or '')}</td>"
        f"<td>{_esc(row.get('sample') or '')}</td></tr>"
        for row in page.get("results") or [])
    verdict = '<span class="chip dashed">— no verdict recorded</span>'
    if page.get("verdict"):
        verdict = (_chip(page["verdict"].get("verdict"),
                         dashboard.VERDICT_STYLES.get(page["verdict"].get("verdict"), ""))
                   + f" · by {_esc(page['verdict'].get('adjudicated_by'))}"
                   + f" · {_esc(page['verdict'].get('adjudicated_at'))}")
        if page.get("verdict_stale"):
            verdict += ' <span class="chip bad"><span class="dot"></span>stale</span>'
    if page.get("operational_not_applicable"):
        verdict = '<span class="chip dashed">LITERATURE_VERDICT_NOT_APPLICABLE</span>'
    sha = fields.get("profile_sha256")
    direction_text = (" ".join(f"{_esc(k)} {_esc(v)}" for k, v in direction.items())
                      or "—")
    profile_bits = [
        f'<div class="m">state {_esc(fields.get("state") or "—")}'
        + (" · provisional" if fields.get("provisional") else "") + "</div>"]
    if fields.get("blocking"):
        profile_bits.append(f'<div class="m">blocking: '
                            f"{_esc(', '.join(fields.get('blocking') or []))}</div>")
    profile_bits.append(
        f'<div class="m">coverage {_esc(coverage.get("sources"))} / '
        f"{_esc(coverage.get('examined'))} examined · direction count {direction_text}"
        ' <span class="frac">(a count, not a strength)</span></div>')
    profile_bits.append(
        f'<div class="m">gate rejected {_esc(fields.get("gate_rejected"))}'
        f" · reviewed, not used {_esc(fields.get('reviewed_not_usable'))}"
        f" · awaiting review {_esc(fields.get('awaiting_review'))}"
        f" · linkage {_esc(fields.get('linkage'))}</div>")
    profile_bits.append(f'<div class="m">extraction {_esc(fields.get("extraction"))}</div>')
    profile_bits.append(f'<div class="m mono">profile {_esc(sha)}</div>')
    if fields.get("stored_profile_stale"):
        profile_bits.append('<div class="m"><span class="chip warn"><span class="dot"></span>'
                            "stored profile differs; showing current evidence, run synthesize "
                            "before signing</span></div>")
    if fields.get("unavailable"):
        profile_bits.append('<div class="m"><span class="chip bad"><span class="dot"></span>'
                            f"{_esc(fields.get('unavailable'))}</span> — profiles shown are "
                            "historical</div>")
    return (
        f'<section><h2>{_esc(page.get("id"))}: {_esc(page.get("text"))}</h2></section>'
        '<section><h2>profile</h2>' + "".join(profile_bits) + "</section>"
        '<section><h2>results</h2>'
        "<table><thead><tr><th>claim</th><th>source</th><th>stance</th><th>as written</th>"
        "<th>sample</th></tr></thead><tbody>" + results + "</tbody></table></section>"
        f'<section><h2>verdict</h2><div class="m">{verdict}</div>'
        '<p class="note">A person reads the profile and signs; an agent does not.</p></section>')


def _mark_quote(text: str, quote: str) -> str:
    """Escape first, then wrap the first occurrence of the (escaped) quote in <mark>."""
    etext, equote = _esc(text), _esc(quote)
    if equote and equote in etext:
        return etext.replace(equote, f"<mark>{equote}</mark>", 1)
    return etext


def _render_lineage(page: dict[str, Any]) -> str:
    steps = page.get("steps") or {}
    claim = steps.get("claim") or {}
    out = ['<section><h2>the claim</h2><div class="log">']
    out.append(f'<div class="r"><span class="s">claim</span><span class="m">'
               f"{_esc(claim.get('claim'))}"
               f"<br>stance {_esc(claim.get('stance'))} · question "
               f"{_esc(claim.get('question_id'))} · class {_esc(claim.get('source_class'))}"
               f"<br>gate v{_esc(claim.get('claim_gate_version'))} rev "
               f"{_esc(claim.get('gate_revision'))} · {_esc(claim.get('backend'))}"
               f"/{_esc(claim.get('model'))} ({_esc(claim.get('harness_version'))})"
               "</span></div>")
    out.append(f'<blockquote><q>{_esc(claim.get("evidence_quote"))}</q></blockquote>')

    review_row = steps.get("review")
    if review_row is None:
        out.append('<div class="r"><span class="s">review</span><span class="m">awaiting '
                   "review</span></div>")
    else:
        out.append(f'<div class="r"><span class="s">review</span><span class="m">'
                   f"{_esc(review_row.get('verdict'))} — {_esc(review_row.get('reason'))}"
                   f"<br>review v{_esc(review_row.get('review_version'))} · "
                   f"{_esc(review_row.get('reviewed_by') or '')}</span></div>")

    chunk = steps.get("chunk")
    if chunk is None:
        out.append('<div class="r"><span class="s">chunk</span><span class="m">not found in '
                   "current ledgers</span></div>")
    else:
        banner = ""
        if chunk.get("quote_found") is False:
            banner = ('<br><span class="chip bad"><span class="dot"></span>invariant 1 check '
                      "fails on current data</span>")
        out.append(f'<div class="r"><span class="s">chunk</span><span class="m">'
                   f"<span class=\"mono\">{_esc(chunk.get('chunk_id'))}</span>"
                   f" · generation {_esc(str(chunk.get('generation_sha256') or '')[:12])}"
                   f" · text {_esc(str(chunk.get('text_sha256') or '')[:12])}{banner}"
                   f'<br><code>{_mark_quote(str(chunk.get("text") or ""), str(chunk.get("evidence_quote") or ""))}'
                   "</code></span></div>")

    document = steps.get("document")
    if document is None:
        out.append('<div class="r"><span class="s">document</span><span class="m">not found in '
                   "current ledgers</span></div>")
    else:
        pdf = (f" · grobid {_esc(str(steps.get('document_pdf_instrument') or '')[:40])}"
               if steps.get("document_pdf_instrument") else "")
        out.append(f'<div class="r"><span class="s">document</span><span class="m">'
                   f"<span class=\"mono\">{_esc(page.get('source_id'))}</span>"
                   f" · confirmed {_esc(document.get('fulltext_confirmed'))}"
                   f" · html v{_esc(document.get('html_parser_version'))}"
                   f" · jats v{_esc(document.get('jats_parser_version'))}{pdf}"
                   f" · {_esc(document.get('chunks'))} chunks"
                   f" · {_esc(document.get('references'))} refs"
                   f" · {_esc(document.get('body_chars'))} chars"
                   f" · generation {_esc(str(document.get('generation_sha256') or '')[:12])}"
                   "</span></div>")

    acquisition = steps.get("acquisition")
    if acquisition is None:
        out.append('<div class="r"><span class="s">acquisition</span><span class="m">not found '
                   "in current ledgers</span></div>")
    else:
        attempts = acquisition.get("attempts") or []
        table = "".join(
            f"<tr><td>{_esc(attempt.get('url'))}</td>"
            f"<td class='num'>{_esc(attempt.get('http_status'))}</td>"
            f"<td>{_esc(_failure_display(attempt.get('failure_class')))}</td>"
            f"<td>{_esc(attempt.get('fetch_version'))}</td></tr>"
            for attempt in attempts)
        out.append(f'<div class="r"><span class="s">acquisition</span><span class="m">'
                   f"<span class=\"mono\">{_esc(str(acquisition.get('sha256') or '')[:16])}</span>"
                   f" · {_esc(acquisition.get('provenance'))}"
                   f" · licence {_esc(acquisition.get('licence'))}"
                   f" · oa {_esc(acquisition.get('oa_status'))}"
                   f" · {_esc(acquisition.get('campaign'))}"
                   f" · {_esc(acquisition.get('fetched_at'))}<br>"
                   f"stored at {_esc(acquisition.get('stored_path'))} (text only; raw bytes are "
                   "never served)<table><thead><tr><th>attempt</th><th>status</th>"
                   "<th>class</th><th>fetch v</th></tr></thead><tbody>"
                   + table + "</tbody></table></span></div>")

    candidate = steps.get("candidate")
    if candidate is None:
        out.append('<div class="r"><span class="s">candidate</span><span class="m">not found in '
                   "current ledgers</span></div>")
    else:
        out.append(f'<div class="r"><span class="s">candidate</span><span class="m">'
                   f"class {_esc(candidate.get('source_class'))}"
                   f" · round {_esc(candidate.get('round'))}"
                   f" · channel {_esc(candidate.get('channel'))}"
                   f" · {_esc(candidate.get('title') or '')}</span></div>")
    out.append("</div></section>")
    return "".join(out)


def _failure_display(failure_class: Any) -> str:
    """F19: a stored class name asserts an inference the UI must not repeat as a fact."""
    text = str(failure_class or "")
    if text == "PAYWALL_403":
        return "HTTP 403 (access refused) [PAYWALL_403]"
    return text


def _render_dossier(page: dict[str, Any]) -> str:
    counted = page.get("counted_acquisition")
    rows = "".join(
        f'<tr><td class="num">{_esc(index)}</td>'
        f"<td>{_esc(row.get('provenance'))}</td>"
        f"<td>{_esc(_failure_display(row.get('failure_class')) if not row.get('acquired') else 'acquired')}</td>"
        f"<td>{_esc(row.get('licence'))}</td>"
        f"<td>{_esc(row.get('fetched_at'))}</td></tr>"
        for index, row in enumerate(page.get("acquisitions") or [], start=1))
    advisory = "".join(
        f'<div class="r"><span class="s">{_esc(ledger)}</span><span class="m">'
        + "".join(f'<br>{_esc(row.get("assessment_status"))} · {_esc(row.get("role") or row.get("related_kind") or "")}'
                  for row in rows_) + "</span></div>"
        for ledger, rows_ in (page.get("advisory") or {}).items() if rows_)
    claims = " · ".join(f"{_esc(q)} {_esc(n)}" for q, n in
                        (page.get("claims_by_question") or {}).items()) or "none"
    chunks = page.get("active_chunks")
    document = page.get("document")
    return (
        '<section><h2>candidate</h2><div class="m">'
        f"<span class=\"mono\">{_esc(page.get('candidate_key'))}</span>"
        f" · source {_esc(page.get('source_id'))}"
        f" · class {_esc((page.get('candidate') or {}).get('source_class'))}"
        f" · round {_esc((page.get('candidate') or {}).get('round'))}</div></section>"
        '<section><h2>acquisitions — every row, ledger order</h2>'
        "<table><thead><tr><th>#</th><th>provenance</th><th>outcome</th><th>licence</th>"
        "<th>fetched</th></tr></thead><tbody>" + rows + "</tbody></table>"
        + (f'<p class="note">counted (collapsed) row: {_esc(str((counted or {}).get("fetched_at")))}'
           f" · {_esc((counted or {}).get('provenance'))}</p>" if counted else
           '<p class="note">no counted acquisition row</p>') + "</section>"
        '<section><h2>document and chunks</h2><div class="m">'
        + (f"confirmed {_esc(document.get('fulltext_confirmed'))}"
           f" · {_esc(document.get('chunks'))} chunks declared"
           if document else "no document row")
        + f" · active chunks: {_esc(chunks if chunks is not None else 'not knowable')}"
        + "</div></section>"
        '<section><h2>advisory — AI provisional</h2><div class="log">' + (advisory or
            '<div class="note">no advisory rows</div>') + "</div>"
        f'<p class="note">{_esc(page.get("advisory_note"))}</p></section>'
        f'<section><h2>claims by question</h2><div class="m">{claims}</div></section>')


class _Handler(BaseHandler):
    """The portal's HTML routing and rendering on the shared transport base (spec §3.1)."""

    csp = CSP

    # --- routing ----------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - http.server's naming
        try:
            route = urlparse(self.path)
            query = parse_qs(route.query)
            if not self._host_ok():
                self._plain(421, "421: misdirected request")
                return
            if not self._origin_ok():
                self._plain(403, "403: cross-origin request refused")
                return
            segments = [unquote(part) for part in route.path.split("/") if part]
            self._route(segments, query)
        except BrokenPipeError:
            pass
        except ConfigError as exc:
            # ConfigError and its RegistryDrift subclass are named states, never crashes (F9).
            self._named_config_error(str(exc))
        except portal_state.NotFound:
            self._plain(404, "404: not found")
        except Exception as exc:  # noqa: BLE001 - a named refusal, never a page of zeros
            self._plain(500, f"500: {type(exc).__name__}")

    def _named_config_error(self, text: str) -> None:
        body = ('<section><h2>project configuration</h2>'
                f'<p class="note">{_esc(text)}</p>'
                "<p class=\"note\">The project's input files did not satisfy their contract; "
                "nothing is rendered over them.</p></section>")
        self._html(self._shell("configuration", [("portal", "/")], body))

    def _route(self, segments: list[str], query: dict[str, list[str]]) -> None:
        if not segments:
            data = portal_state.index(self.projects_dir, self.store_dir)
            self._html(self._shell("portal", [("portal", "/")],
                                   _render_index(data)))
            return
        if segments == ["inbox"]:
            self._html(self._shell("inbox", [("portal", "/"), ("inbox", "")],
                                   _render_inbox(self._inbox_data())))
            return
        if segments == ["admin"]:
            data = portal_state.admin_state(pathlib.Path(self.projects_dir).resolve().parent)
            self._html(self._shell("admin", [("portal", "/"), ("admin", "")],
                                   _render_admin(data)))
            return
        if segments == ["api", "index"]:
            self._json(portal_state.index(self.projects_dir, self.store_dir))
            return
        if segments == ["api", "inbox"]:
            self._json(self._inbox_data())
            return
        if segments == ["api", "poll"]:
            name = (query.get("project") or [""])[0]
            root = self._project_root(name)
            self._json(round_state.cheap_state(Store(root.name, base=self.store_dir)))
            return
        if len(segments) >= 5 and segments[0] == "api" and segments[1] == "p" and segments[3] == "f":
            name = segments[2]
            project, store, _root = self._loaded(name)
            flow_row = self._flow(store, segments[4])
            selector = portal_state._selector_of(flow_row, scope.Selector(None))
            if len(segments) == 5:
                self._json(portal_state.flow_overview(project, store, selector, flow_row))
            elif len(segments) == 7 and segments[5] == "q":
                self._json(portal_state.question_detail(project, store, selector, segments[6]))
            else:
                raise portal_state.NotFound("no such api route")
            return

        if len(segments) >= 2 and segments[0] == "p":
            name = segments[1]
            if len(segments) == 2:
                self._project_page(name)
                return
            kind = segments[2]
            if kind == "f" and len(segments) >= 4:
                project, store, _root = self._loaded(name)
                flow_row = self._flow(store, segments[3])
                selector = portal_state._selector_of(flow_row, scope.Selector(None))
                base = f"/p/{name}/f/{segments[3]}"
                if len(segments) == 4:
                    self._flow_page(project, store, selector, flow_row, base)
                elif len(segments) == 6 and segments[4] == "q":
                    self._question_page(project, store, selector, segments[5], base,
                                        flow_row=flow_row)
                elif len(segments) == 6 and segments[4] == "claim":
                    self._lineage_page(project, store, selector, segments[5], base)
                elif len(segments) == 6 and segments[4] == "source":
                    self._dossier_page(project, store, selector, segments[5], base)
                else:
                    raise portal_state.NotFound("no such route")
                return
            if kind == "legacy" and len(segments) >= 4:
                project, store, _root = self._loaded(name)
                # Looked up among the selectors that exist: an invented round is a 404, not an
                # empty page that reads as "this round found nothing".
                selector = portal_state.selector_from_slug(
                    store, flows.flows(store).values(), segments[3])
                base = f"/p/{name}/legacy/{segments[3]}"
                if len(segments) == 4:
                    self._flow_page(project, store, selector, None, base)
                elif len(segments) == 6 and segments[4] == "q":
                    self._question_page(project, store, selector, segments[5], base)
                elif len(segments) == 6 and segments[4] == "claim":
                    self._lineage_page(project, store, selector, segments[5], base)
                elif len(segments) == 6 and segments[4] == "source":
                    self._dossier_page(project, store, selector, segments[5], base)
                else:
                    raise portal_state.NotFound("no such route")
                return
        raise portal_state.NotFound("no such route")

    def _shell(self, title: str, breadcrumb: list[tuple[str, str]], body: str,
               poll_project: str | None = None) -> str:
        return _page(title, breadcrumb, body, self.code_revision, self.code_dirty,
                     poll_project)

    def _inbox_data(self) -> dict[str, Any]:
        projects = []
        for root in discover_projects(self.projects_dir):
            try:
                project = load_project(root)
                store = Store(root.name, base=self.store_dir)
                check_registry_drift(project, store, record=False)
            except ConfigError as exc:
                # A project whose inputs fail their contract is an open item, not an absence:
                # dropping it from the inbox would hide exactly the project that needs a person.
                card = portal_state.Card("INTEGRITY", "project", type(exc).__name__, str(exc),
                                         f"claimstone validate {root}", "")
                projects.append({"name": root.name, "cards": [dataclasses.asdict(card)]})
                continue
            flow_rows = flows.flows(store)
            selectors = [(portal_state._selector_of(row, scope.Selector(None)), row)
                         for row in flow_rows.values()]
            selectors += [(selector, None) for selector in
                          portal_state.unbound_selectors(store, flow_rows.values())]
            cards = [dataclasses.asdict(card)
                     for selector, row in selectors
                     for card in portal_state.inbox_cards(project, store, selector, row)]
            projects.append({"name": root.name, "cards": cards})
        return {"projects": projects}

    def _project_page(self, name: str) -> None:
        try:
            project, store, root = self._loaded(name)
        except ConfigError as exc:
            self._html(self._shell(name, [("portal", "/"), (name, "")],
                                   f'<section><h2>config</h2><div class="chip bad">'
                                   f'<span class="dot"></span>ConfigError</div>'
                                   f'<p class="note">{_esc(str(exc))}</p></section>'))
            return
        integrity = portal_state.integrity(root, store, code_revision=self.code_revision,
                                           code_dirty=self.code_dirty)
        flow_rows = flows.flows(store)
        legacy = "".join(
            f'<div class="r"><span class="w mono">legacy</span>'
            f'<span class="s">{_esc(portal_state.selector_label(selector))}</span>'
            f'<span class="m"><a href="/p/{_esc(project.name)}/legacy/'
            f'{_esc(portal_state.selector_slug(selector))}/">'
            "open</a> · protocol not verified</span></div>"
            for selector in portal_state.unbound_selectors(store, flow_rows.values()))
        rows = "".join(
            f'<div class="r"><span class="w mono"><a href="/p/{_esc(project.name)}/f/'
            f'{_esc(flow_id)}/">flow {_esc(flow_id[:12])}</a></span>'
            f'<span class="s">{_esc(portal_state.selector_label(portal_state._selector_of(row, scope.Selector(None))))}</span>'
            f'<span class="m">{_esc(row.get("title") or "")} · bound '
            f"{_esc(row.get('created_at'))} · {_esc(row.get('created_by'))}"
            + (" · bound after data existed" if row.get("bound_after_data") else "")
            + "</span></div>"
            for flow_id, row in sorted(flow_rows.items()))
        activity = "".join(
            f'<div class="r"><span class="w mono">{_esc(row["when"])}</span>'
            f'<span class="s" style="color:var(--teal)">{_esc(row["stage"])}</span>'
            f'<span class="m">{_esc(json.dumps(row["row"], ensure_ascii=False)[:220])}</span></div>'
            for row in round_state.activity(store, 50)) or '<div class="note">no rows yet</div>'
        body = (
            _render_integrity(integrity)
            + '<section><h2>flows</h2><div class="log">' + (rows or
              '<div class="note">no flows; rounds with candidates are legacy</div>') + "</div></section>"
            + '<section><h2>legacy rounds</h2><div class="log">' + (legacy or
              '<div class="note">none</div>') + "</div></section>"
            + '<section><h2>activity — whole project</h2><div class="log">' + activity
            + "</div></section>")
        self._html(self._shell(name, [("portal", "/"), (name, "")], body,
                               poll_project=project.name))

    def _flow_page(self, project: Any, store: Store, selector: scope.Selector,
                   flow_row: dict[str, Any] | None, base: str) -> None:
        page = portal_state.flow_overview(project, store, selector, flow_row)
        label = (f"flow {(flow_row or {}).get('flow_id', '')[:12]}" if flow_row
                 else f"legacy {selector.round}")
        crumbs = [("portal", "/"), (project.name, f"/p/{project.name}/"), (label, "")]
        self._html(self._shell(f"{project.name} · {label}", crumbs,
                               _render_overview(page),
                               poll_project=project.name))

    def _question_page(self, project: Any, store: Store, selector: scope.Selector,
                       question_id: str, base: str, flow_row: dict[str, Any] | None = None) -> None:
        page = portal_state.question_detail(project, store, selector, question_id)
        crumbs = [("portal", "/"), (project.name, f"/p/{project.name}/"), (question_id, "")]
        self._html(self._shell(f"{project.name} · {question_id}", crumbs,
                               _render_question(page, base_url=base),
                               poll_project=project.name))

    def _lineage_page(self, project: Any, store: Store, selector: scope.Selector,
                      claim_id: str, base: str) -> None:
        page = portal_state.lineage(project, store, selector, claim_id)
        crumbs = [("portal", "/"), (project.name, f"/p/{project.name}/"),
                  (f"claim {claim_id}", "")]
        self._html(self._shell(f"{project.name} · lineage", crumbs, _render_lineage(page),
                               poll_project=project.name))

    def _dossier_page(self, project: Any, store: Store, selector: scope.Selector,
                      candidate_key: str, base: str) -> None:
        page = portal_state.source_dossier(project, store, selector, candidate_key)
        crumbs = [("portal", "/"), (project.name, f"/p/{project.name}/"),
                  (f"source {candidate_key}", "")]
        self._html(self._shell(f"{project.name} · source", crumbs, _render_dossier(page),
                               poll_project=project.name))


def make_server(projects_dir: str | pathlib.Path = "projects",
                store_dir: str | pathlib.Path = "store", *, host: str = "127.0.0.1",
                port: int = 8788, allow_hosts: tuple[str, ...] = ()) -> ThreadingHTTPServer:
    revision, dirty = flows._code_identity(pathlib.Path(projects_dir))
    # Inside a container git is absent; the image may carry the revision it was built from.
    if revision is None and os.environ.get("CLAIMSTONE_CODE_REVISION"):
        revision = os.environ["CLAIMSTONE_CODE_REVISION"]
    names = set(LOOPBACK_HOSTS)
    if host not in ("0.0.0.0", "::"):
        # A wildcard bind is not a name anyone should send as Host; it widens nothing.
        names.add(host)
    handler = type("PortalHandler", (_Handler,), {
        "projects_dir": pathlib.Path(projects_dir),
        "store_dir": pathlib.Path(store_dir),
        "allowed_hosts": frozenset(n.lower() for n in names),
        "allowed_authorities": frozenset(a.lower() for a in allow_hosts),
        "bind_port": int(port),
        "code_revision": revision,
        "code_dirty": dirty,
    })
    httpd = ThreadingHTTPServer((host, port), handler)
    # With port 0 the real port exists only after the bind; the Host allowlist must know it.
    handler.bind_port = int(httpd.server_address[1])
    return httpd


def serve(projects_dir: str | pathlib.Path = "projects", store_dir: str | pathlib.Path = "store",
          *, host: str = "127.0.0.1", port: int = 8788, allow_hosts: tuple[str, ...] = ()) -> None:
    """Block and serve every project, read-only."""
    print(f"claimstone portal — http://{host}:{port}/  (read-only; Ctrl-C to stop)")
    httpd = make_server(projects_dir, store_dir, host=host, port=port, allow_hosts=allow_hosts)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
