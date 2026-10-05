"""Transport only: routing, template, polling — the `dashboard.py` of the spec (§3, §9).

Every request re-reads the ledgers from disk and recomputes through `round_state` (§9 "stateless
per request"): no cache and no in-memory model, which is what makes this safe to run while a
stage is writing. The writer appends, the reader re-reads, and append-only removes the lock.

Read-only is structural, not a promise: no route here has any code path that writes, and the
page carries no control of any kind — "no button starts a fetch" is honesty rule 7 and §13.

The page is **one self-contained HTML document** (§11): inline CSS, inline JS, no CDN, no web
font, no chart library — it works offline and discloses nothing to a third party, which matters
given what the data is. Colour never carries meaning alone: every state also carries its word.
"""

from __future__ import annotations

import html
import ipaddress
import json
import textwrap
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from claimstone import round_state
from claimstone.config import Project
from claimstone.store import Store

LOOPBACK = ("127.0.0.1", "::1", "localhost")
PRIVACY_NOTE = (
    "non-loopback bind: the ledgers carry the consuming system's reading list, which is why "
    "projects/ and store/ are gitignored (dashboard spec §10). Binding anyway because --host "
    "was passed explicitly."
)

# The five human verdicts plus the engine's one categorical outcome, each with its colour class
# and its word — the word is the meaning, the colour only repeats it (§8.5).
VERDICT_STYLES = {
    "SUPPORTED": "v-sup",
    "CONTRADICTED": "v-con",
    "CONTESTED_IN_LITERATURE": "v-conte",
    "UNANSWERED_IN_LITERATURE": "v-unans",
    "NEVER_ASKED": "v-never",
    "NO_VERIFIED_CLAIM": "v-nvc",
}

_STYLE = """
:root{--bg:#071019;--surface:#0a1622;--card:#0e1e31;--border:#1c3450;--border-soft:#14283e;
--text:#e9f1fa;--muted:#9db5ce;--faint:#829db8;--teal:#14b8a6;--mint:#5eead4;--emerald:#34d399;
--sky:#38bdf8;--amber:#fbbf24;--red:#f87171;--violet:#a78bfa;--slate:#94a3b8}
:root[data-theme=light]{--bg:#eef4f9;--surface:#fff;--card:#fff;--border:#d7e3ee;
--border-soft:#e3edf5;--text:#0e2236;--muted:#4e6b85;--faint:#5b7186;--teal:#0d9488;--mint:#0f766e;
--emerald:#059669;--sky:#0284c7;--amber:#b45309;--red:#dc2626;--violet:#7c3aed;--slate:#64748b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:14px/1.5 ui-sans-serif,system-ui,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
.mono{font-family:ui-monospace,"JetBrains Mono",Consolas,Menlo,monospace}
header{display:flex;gap:10px;align-items:baseline;padding:14px 20px 8px;flex-wrap:wrap}
h1{font-size:17px;margin:0}header .meta{color:var(--faint);font-size:12px}
header button{margin-left:auto;background:var(--surface);color:var(--muted);border:1px solid var(--border);
border-radius:8px;padding:4px 10px;cursor:pointer;font-size:12px}
main{padding:6px 20px 40px;max-width:1180px;margin:0 auto}
section{margin:18px 0}h2{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;margin:0 0 10px}
.strip{display:flex;gap:8px;flex-wrap:wrap}
.node{flex:1;min-width:150px;background:var(--card);border:1px solid var(--border);border-radius:11px;padding:10px 12px}
.node.blocked{border-color:color-mix(in srgb,var(--red) 45%,transparent)}
.node .n{font-weight:700;font-size:12.5px}.node .m{font-size:11.5px;color:var(--muted);margin-top:5px}
.node .m b{color:var(--text)}
.meter{height:8px;border-radius:6px;background:color-mix(in srgb,var(--surface) 60%,transparent);
border:1px solid var(--border-soft);position:relative;margin:6px 0 2px}
.meter>i{display:block;height:100%;border-radius:6px;background:linear-gradient(90deg,var(--teal),var(--sky))}
.meter.bad>i{background:linear-gradient(90deg,#b91c1c,var(--red))}
.meter .floor{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--text);opacity:.7}
.frac{font-size:11px;color:var(--faint)}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{font-size:10.5px;text-transform:uppercase;letter-spacing:.5px;color:var(--faint);text-align:left;
padding:7px 8px;border-bottom:1px solid var(--border)}
td{padding:8px;border-bottom:1px solid var(--border-soft);vertical-align:top}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.chip{display:inline-block;border-radius:999px;padding:1px 9px;font-size:10.5px;font-weight:600;
border:1px solid var(--border);color:var(--muted);white-space:nowrap}
.chip .dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:5px;vertical-align:1px}
.v-sup{color:var(--emerald);border-color:color-mix(in srgb,var(--emerald) 35%,transparent)}.v-sup .dot{background:var(--emerald)}
.v-con{color:var(--sky);border-color:color-mix(in srgb,var(--sky) 35%,transparent)}.v-con .dot{background:var(--sky)}
.v-conte{color:var(--violet);border-color:color-mix(in srgb,var(--violet) 40%,transparent)}.v-conte .dot{background:var(--violet)}
.v-unans{color:var(--slate);border-color:color-mix(in srgb,var(--slate) 40%,transparent)}.v-unans .dot{background:var(--slate)}
.v-never{color:var(--faint);border-style:dashed}.v-never .dot{background:var(--faint)}
.v-nvc{color:var(--amber);border-style:dashed}.v-nvc .dot{background:var(--amber)}
.chip.warn{color:var(--amber);border-color:color-mix(in srgb,var(--amber) 40%,transparent)}.chip.warn .dot{background:var(--amber)}
.chip.bad{color:var(--red);border-color:color-mix(in srgb,var(--red) 40%,transparent)}.chip.bad .dot{background:var(--red)}
.chip.ok{color:var(--emerald);border-color:color-mix(in srgb,var(--emerald) 35%,transparent)}.chip.ok .dot{background:var(--emerald)}
.chip.dashed{border-style:dashed;color:var(--faint)}
.bars{display:flex;flex-direction:column;gap:6px}
.bar{display:grid;grid-template-columns:220px 1fr 60px;gap:10px;align-items:center;font-size:12px}
.bar .track{height:14px;background:color-mix(in srgb,var(--surface) 60%,transparent);border-radius:5px;
border:1px solid var(--border-soft);overflow:hidden}
.bar .fill{height:100%;background:linear-gradient(90deg,var(--teal),var(--sky))}
.bar .fill.rej{background:linear-gradient(90deg,color-mix(in srgb,var(--red) 70%,transparent),var(--amber))}
.bar .v{text-align:right;color:var(--muted);font-variant-numeric:tabular-nums}
.log{font-size:12px;max-height:340px;overflow:auto;background:var(--card);border:1px solid var(--border-soft);
border-radius:10px;padding:8px 10px}
.log .r{display:grid;grid-template-columns:150px 80px 1fr;gap:10px;padding:4px 0;
border-bottom:1px dashed var(--border-soft)}
.log .w{color:var(--faint)}.log .s{font-weight:700;font-size:10.5px}.log .m{color:var(--muted);word-break:break-word}
.note{font-size:11.5px;color:var(--faint);margin-top:8px}
.two{display:grid;grid-template-columns:1.6fr 1fr;gap:14px}
@media(max-width:950px){.two{grid-template-columns:1fr}}
q{color:var(--muted)}
"""

_SCRIPT = """
const root=document.documentElement;
const saved=(()=>{try{return localStorage.getItem('cs-theme')}catch(e){return null}})();
const mq=matchMedia('(prefers-color-scheme: light)');
root.dataset.theme=saved||(mq.matches?'light':'dark');
document.getElementById('tgl').onclick=()=>{const t=root.dataset.theme==='dark'?'light':'dark';
root.dataset.theme=t;try{localStorage.setItem('cs-theme',t)}catch(e){}};
let last=null;
async function poll(){try{const r=await fetch('/api/state');const j=await r.json();
const sig=JSON.stringify(j.ledgers);
if(last!==null&&sig!==last&&document.visibilityState==='visible'){location.reload();return}
last=sig;const el=document.getElementById('running');
el.textContent=j.running.length?j.running.join(' · '):'no ledger written in the last 30s';}
catch(e){}}
setInterval(poll,2000);poll();
"""


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _chip(label: str, style: str, dashed: bool = False) -> str:
    cls = f"chip {style}" + (" dashed" if dashed and not style.startswith("v-") else "")
    return f'<span class="{cls}"><span class="dot"></span>{_esc(label)}</span>'


def _frac(done: int | None, total: int | None, label: str | None = None) -> str:
    """A fraction always written with its denominator beside it, never a bare percentage."""
    if done is None or total in (None, 0):
        return '<span class="frac">— not knowable</span>' if total is None else ""
    text = f"{done} / {total}"
    if label:
        text += f" · {_esc(label)}"
    return f'<span class="frac">{_esc(text)}</span>'


def _stage_node(stage: round_state.StageState) -> str:
    progress = ""
    if stage.progress is not None:
        pct = 100.0 * stage.progress.done / stage.progress.total if stage.progress.total else 0
        progress = (
            f'<div class="meter"><i style="width:{pct:.1f}%"></i></div>'
            f"{_frac(stage.progress.done, stage.progress.total, stage.progress.label)}"
        )
    lines = [
        '<div class="m">',
        f"<b>{_esc(stage.outputs if stage.outputs is not None else '—')}</b> out"
        if stage.implemented
        else '<div class="m">— not implemented, and saying so',
    ]
    if stage.rejected is not None:
        lines.append(f" · {_esc(stage.rejected)} rejected")
    lines.append("</div>")
    detail = f'<div class="m" style="color:var(--faint)">{_esc(stage.detail)}</div>' if stage.detail else ""
    return (
        f'<div class="node" id="stage-{_esc(stage.name)}">'
        f'<div class="n">{_esc(stage.name)}</div>{"".join(lines)}{progress}{detail}</div>'
    )


def _spine_row(q: round_state.QuestionRow) -> str:
    if q.verdict:
        verdict = _chip(q.verdict, VERDICT_STYLES.get(q.verdict, ""), dashed=False)
        if q.verdict_stale:
            verdict += ' <span class="chip bad"><span class="dot"></span>stale — evidence moved</span>'
    elif q.state:
        verdict = _chip(q.state, VERDICT_STYLES.get(q.state, ""), dashed=True)
    else:
        verdict = '<span class="chip dashed">— no verdict</span>'
    state_chip = ""
    if q.provisional:
        blocking = ", ".join(q.blocking) or "provisional"
        state_chip = f'<br><span class="chip warn"><span class="dot"></span>{_esc(blocking)}</span>'
    coverage = "— / —" if q.coverage_sources is None else f"{q.coverage_sources} / {q.coverage_examined}"
    claims = "0" if q.claims == 0 else _esc(q.claims if q.claims is not None else "—")
    by_class = " · ".join(f"{_esc(k)} {_esc(v)}" for k, v in q.claims_by_class.items()) or "—"
    sha = f'<span class="mono" style="color:var(--faint)">{_esc(str(q.profile_sha256)[:12])}</span>' \
        if q.profile_sha256 else ""
    return (
        "<tr>"
        f'<td class="mono">{_esc(q.id)}</td>'
        f"<td>{_esc(q.text)}<br>{sha}</td>"
        f"<td>{_esc(q.kind)}</td>"
        f'<td class="num">{claims}</td>'
        f"<td>" + _esc(by_class) + "</td>"
        f'<td class="num">{_esc(coverage)}</td>'
        f"<td>{verdict}{state_chip}</td>"
        "</tr>"
    )


def render_page(state: round_state.RoundState, cheap: dict[str, Any],
                activity_rows: list[dict[str, Any]] | None = None) -> str:
    """One self-contained HTML document. Values are escaped; fractions carry denominators."""
    floor = state.floor or {}
    floor_line = ""
    if floor:
        status = str(floor.get("status"))
        chip = _chip(status, "ok" if status == "OK" else "bad")
        found = floor.get("found")
        confirmed = floor.get("confirmed")
        basis = floor.get("basis")
        rate = floor.get("rate")
        rate_text = f"{rate:.2f}" if isinstance(rate, (int, float)) else "—"
        pct = (100.0 * rate) if isinstance(rate, (int, float)) else 0
        floor_line = (
            f'<div class="node"><div class="n">acquisition floor</div>'
            f'<div class="meter{" bad" if status != "OK" else ""}"><i style="width:{pct:.1f}%"></i>'
            f'<span class="floor" style="left:{floor.get("floor", 0) * 100:.0f}%"></span></div>'
            f'<div class="m">{_esc(basis)} {_esc(confirmed)} / {_esc(found)} = <b>{_esc(rate_text)}</b> '
            f"· floor {_esc(floor.get('floor'))} · v{_esc(floor.get('floor_version'))} "
            f"· {_esc(floor.get('floor_set_at'))}<br>{chip}</div></div>"
        )
    strip = "".join(_stage_node(s) for s in state.stages)
    spine = "".join(_spine_row(q) for q in state.questions)
    rej_rows = "".join(
        f'<div class="bar"><span class="mono">{_esc(reason)}</span>'
        f'<div class="track"><div class="fill rej" style="width:{100 * n / max(total, 1):.1f}%"></div></div>'
        f'<span class="v">{_esc(n)}</span></div>'
        for reason, n in state.rejections_by_reason.items()
        if (total := sum(state.rejections_by_reason.values()))
    ) or '<div class="note">no current rejections — the denominator is honest either way</div>'
    activity_rows = "".join(
        f'<div class="r"><span class="w mono">{_esc(row["when"])}</span>'
        f'<span class="s" style="color:var(--teal)">{_esc(row["stage"])}</span>'
        f'<span class="m">{_esc(json.dumps(row["row"], ensure_ascii=False)[:220])}</span></div>'
        for row in (activity_rows or [])
    ) or '<div class="note">no rows yet</div>'
    unavailable = (
        f'<section><h2>corpus</h2><div class="chip bad"><span class="dot"></span>'
        f"{_esc(state.unavailable)}</div></section>"
        if state.unavailable else ""
    )
    verdicts_line = (
        f"{state.verdicts_recorded} recorded"
        + (f" · {state.verdicts_stale} stale" if state.verdicts_stale else "")
        + " — adjudicate is the only command that writes one, and it takes a person"
    )
    legend_chips = "".join(_chip(name, style) for name, style in VERDICT_STYLES.items())
    return textwrap.dedent(f"""<!doctype html>
    <html lang="en" data-theme="dark">
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>claimstone · {_esc(state.project)}</title><style>{_STYLE}</style></head>
    <body>
    <header>
      <h1>claimstone · {_esc(state.project)}{f" · round {_esc(state.round)}" if state.round else ""}</h1>
      <span class="meta">read-only derived view · re-read from disk on every request</span>
      <button id="tgl" title="light/dark (legible in both, spec §11)">◐</button>
    </header>
    <main>
    {unavailable}
    <section><h2>the pipeline</h2><div class="strip">{strip}{floor_line}</div>
    <p class="note">discover never carries a percentage: how much relevant work exists is unknown.
    A fraction always shows its denominator; a dash means <q>not knowable in principle</q>, never zero.</p></section>

    <section><h2>the questions — registry order</h2>
    <table><thead><tr><th>id</th><th>question (frozen)</th><th>kind</th><th class="num">claims</th>
    <th>per class</th><th class="num">coverage<br>speaking / examined</th><th>verdict</th></tr></thead>
    <tbody>{spine}</tbody></table>
    <p class="note">Coverage is post-review: sources that speak to a question, over sources examined.
    NO_VERIFIED_CLAIM is the engine's categorical outcome and is not a verdict: nothing survived,
    and only screening by a person can say <q>never asked</q>. Verdicts: {verdicts_line}.</p>

    <section><h2>the vocabulary — five verdicts, and the engine's one outcome</h2>
    <div class="strip">{legend_chips}</div>
    <p class="note">The first five are a person's, recorded by <q>adjudicate</q> against a profile
    hash. The sixth, dashed, is the engine's own categorical outcome: it is not a verdict, and it
    never collapses into <q>never asked</q>. CONTRADICTED is blue, not red — concluding against a
    question is a successful outcome, not a failure.</p></section>

    <section><h2>what the gate rejected — the denominator</h2>
    <div class="bars">{rej_rows}</div>
    <p class="note">Current outcomes per claim under one counting rule: last result per claim id,
    with supersede across both ledgers (D46). A page showing only what passed tells half the story.</p></section>

    <section><h2>activity — newest rows, and what "running" is</h2>
    <div class="log">{activity_rows}</div>
    <p class="note" id="running">checking…</p>
    <p class="note"><q>Running</q> is inferred from a ledger mtime within the last 30 seconds and is
    labelled as an inference — never a claim that a process is alive. The page polls /api/state
    every 2 s and reloads only when an mtime moved.</p></section>
    </main>
    <script>{_SCRIPT}</script>
    </body></html>""")



class _Handler(BaseHTTPRequestHandler):
    """GET only. Anything that is not a routed GET answers 405 (§9)."""

    project: Project
    store: Store
    round_name: str | None
    manifest_only: bool

    def log_message(self, fmt: str, *args: Any) -> None:  # quiet by default
        pass

    def _json(self, payload: Any, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=1, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _refuse(self) -> None:
        body = b"405: not a routed GET\n"
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        # RFC 9110 §9.3.2: a HEAD response is the GET headers and nothing else — writing the
        # body here made every keep-alive framing after a probe ambiguous.
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server's naming
        route = urlparse(self.path)
        query = parse_qs(route.query)
        try:
            if route.path == "/":
                rs = round_state.state(self.project, self.store, round_name=self.round_name,
                                       manifest_only=self.manifest_only)
                self._html(render_page(rs, round_state.cheap_state(self.store),
                                       round_state.activity(self.store, 50)))
            elif route.path == "/api/state":
                self._json(round_state.cheap_state(self.store))
            elif route.path == "/api/round":
                rs = round_state.state(self.project, self.store, round_name=self.round_name,
                                       manifest_only=self.manifest_only)
                self._json(rs.as_dict())
            elif route.path == "/api/questions":
                rs = round_state.state(self.project, self.store, round_name=self.round_name,
                                       manifest_only=self.manifest_only)
                self._json({"unavailable": rs.unavailable, "floor": rs.floor,
                            "questions": [q.__dict__ | {"blocking": list(q.blocking)}
                                          for q in rs.questions]})
            elif route.path == "/api/activity":
                try:
                    limit = int(query.get("limit", ["50"])[0])
                except ValueError:
                    limit = 50
                self._json({"rows": round_state.activity(self.store, limit)})
            else:
                self._refuse()
        except BrokenPipeError:
            pass

    def do_POST(self) -> None:  # noqa: N802
        self._refuse()

    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_POST  # every non-GET: the same refusal

    def __getattr__(self, name: str) -> Any:
        # §9 is *every* verb, including ones http.server dispatches by name and would otherwise
        # answer 501. The dispatch probes `do_<VERB>`, so any missing handler is the same refusal.
        if name.startswith("do_"):
            return self._refuse
        raise AttributeError(name)


def make_server(project: Project, store: Store, *, round_name: str | None = None,
                manifest_only: bool = False, host: str = LOOPBACK[0],
                port: int = 8787) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (_Handler,), {
        "project": project, "store": store,
        "round_name": round_name, "manifest_only": manifest_only,
    })
    return ThreadingHTTPServer((host, port), handler)


def host_warning(host: str) -> str | None:
    """The §10 rule, as a sentence the CLI can print when the bind is not loopback."""
    if host in LOOPBACK:
        return None
    # "127.0.0.1" is not the whole loopback range: 127.0.0.0/8 is. Warning on 127.0.0.2 would
    # print a false "non-loopback bind" — §10 says the warning fires exactly when it is not.
    try:
        if ipaddress.ip_address(host).is_loopback:
            return None
    except ValueError:
        pass
    return PRIVACY_NOTE


def serve(project: Project, store: Store, *, round_name: str | None = None,
          manifest_only: bool = False, host: str = LOOPBACK[0], port: int = 8787) -> None:
    """Block and serve. One project per serve (§13: no multi-project view)."""
    httpd = make_server(project, store, round_name=round_name, manifest_only=manifest_only,
                        host=host, port=port)
    print(f"claimstone serve · {project.name}"
          f"{f' · round {round_name}' if round_name else ''}"
          f" — http://{host}:{port}/  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
