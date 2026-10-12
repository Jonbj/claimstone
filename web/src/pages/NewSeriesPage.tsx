import { useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import ProjectTabs from "@/components/ProjectTabs";
import FiguresPanel from "@/components/scheduler/FiguresPanel";
import RoundsEditor from "@/components/scheduler/RoundsEditor";
import { areaClass, cardClass, inputClass, primaryClass, quietClass } from "@/components/wizard/stepTypes";
import { useLeaveWarning } from "@/components/wizard/useLeaveWarning";
import { useApi } from "@/hooks/useApi";
import { useNow } from "@/hooks/useSchedulerRefresh";
import { api } from "@/lib/api";
import { checkRounds, generateRounds } from "@/lib/cadence";
import type { Cadence, RoundDraft } from "@/lib/cadence";
import { ControlError, control } from "@/lib/control";
import { figures, hostsFor, SOURCES } from "@/lib/figures";
import { useLocale } from "@/lib/i18n";
import { useSession } from "@/lib/session";

const DEFAULT_PER_QUERY = "25";
const DEFAULT_REQUESTS_EACH = "3";

interface Inputs { kind: "monthly" | "weekly" | "days"; start: string; every: string; count: string; prefix: string }

/** The first day of the next month, UTC, as YYYY-MM-DD. */
function nextMonthStart(now: Date): string {
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1)).toISOString().slice(0, 10);
}

/** The cadence the inputs describe, or null while a number is not yet a usable one. */
function cadenceOf(i: Inputs): Cadence | null {
  const count = Number(i.count);
  if (!Number.isInteger(count) || count < 1 || count > 32 || !/^\d{4}-\d{2}-\d{2}$/.test(i.start)) return null;
  if (i.kind !== "days") return { kind: i.kind, start: i.start, count };
  const every = Number(i.every);
  return Number.isInteger(every) && every >= 1 ? { kind: "days", start: i.start, every, count } : null;
}

const wholeNumber = (text: string): number | null => {
  const n = Number(text);
  return text.trim() !== "" && Number.isInteger(n) && n >= 1 ? n : null;
};

function Labeled({ label, help, children }: { label: string; help?: string; children: (id: string) => ReactNode }) {
  const id = `ns-${label.replace(/\W+/g, "-")}`;
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium">{label}</label>
      {children(id)}
      {help ? <p className="text-xs text-muted-foreground">{help}</p> : null}
    </div>
  );
}

function Body({ project }: { project: string }) {
  const { t } = useLocale();
  const navigate = useNavigate();
  const now = useNow(60_000);
  const projects = useApi(() => api.projects(), []);
  const card = projects.data?.projects.find((p) => p.name === project) ?? null;
  const flows = (card?.flows ?? []).filter((f) => !f.selector.manifest_only);
  const [chosen, setChosen] = useState<string | null>(null);
  // Several flows: the last CURRENT one, else the last one listed.
  const fallback = [...flows].reverse().find((f) => f.binding_state === "CURRENT") ?? flows[flows.length - 1];
  const flowId = chosen ?? fallback?.flow_id ?? "";
  const overview = useApi(() => (flowId ? api.overview(project, "f", flowId) : Promise.resolve(null)), [project, flowId]);
  const topics = overview.data?.journey.topics ?? null;
  // Rounds with candidates (unbound selectors) are refused early. A round that is only the name of a
  // bound flow may be an exact retry of an earlier save, so it gets a note and the server decides.
  const known = useMemo(() => new Set<string>(
    (card?.unbound_selectors ?? []).map((u) => u.selector.round).filter((r): r is string => typeof r === "string")), [card]);
  const flowRounds = useMemo(() => new Set<string>(
    (card?.flows ?? []).map((f) => f.selector.round).filter((r): r is string => typeof r === "string")), [card]);

  const initial: Inputs = { kind: "monthly", start: nextMonthStart(new Date(now)), every: "7", count: "3", prefix: "Update" };
  const [inputs, setInputs] = useState<Inputs>(initial);
  const [pending, setPending] = useState<Inputs | null>(null);
  const [rounds, setRounds] = useState<RoundDraft[]>(() => generateRounds(cadenceOf(initial)!, initial.prefix));
  const [edited, setEdited] = useState(false);
  const shown = pending ?? inputs;

  const [apis, setApis] = useState<string[]>([]);
  const [hostsText, setHostsText] = useState<string | null>(null);   // null: follow the sources
  const [perQuery, setPerQuery] = useState(DEFAULT_PER_QUERY);
  const [requestsEach, setRequestsEach] = useState(DEFAULT_REQUESTS_EACH);
  const [unitsText, setUnitsText] = useState<string | null>(null);   // null: the number of searches

  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const [refusal, setRefusal] = useState<Error | null>(null);

  const hostsShown = hostsText ?? hostsFor(apis).join("\n");
  const hosts = [...new Set(hostsShown.split(/[\n,]/).map((h) => h.trim().toLowerCase()).filter(Boolean))];
  const requestsNumber = wholeNumber(requestsEach);
  const searches = topics ? figures({ topics, apis, maxRequestsEach: requestsNumber ?? 0, rounds: rounds.length }).searchesPerRound : 0;
  const unitsShown = unitsText ?? (searches ? String(searches) : "");
  const unitsNumber = wholeNumber(unitsShown);
  const perQueryNumber = wholeNumber(perQuery);
  const preview = topics && searches
    ? figures({ topics, apis, maxRequestsEach: requestsNumber ?? 0, rounds: rounds.length }) : null;
  const problems = checkRounds(rounds, known, new Date(now));
  const flowNotes = [...new Set(rounds.map((r) => r.round))].filter((name) => flowRounds.has(name) && !known.has(name));
  // The hosts must cover every ticked source (the server does not check this): a search to a host that
  // is not permitted would fail. Hosts nobody ticked are allowed but noted.
  const wanted = hostsFor(apis);
  const missingSource = apis.map((a) => ({ source: a, host: hostsFor([a])[0] })).find((x) => x.host && !hosts.includes(x.host));
  const extraHosts = hosts.filter((h) => !wanted.includes(h));

  // What stops the save, in the order a person would fix it. The first unmet condition is named.
  let reason: string | null = null;
  const first = problems[0];
  if (!flowId) reason = t("sched.new.reason.flow");
  else if (overview.error) reason = t("sched.new.reason.topicsFailed");
  else if (!topics) reason = t("sched.new.reason.topicsLoading");
  else if (apis.length === 0) reason = t("sched.new.reason.noSource");
  else if (!cadenceOf(shown) && !pending) reason = t("sched.new.reason.count");
  else if (first) {
    const sentence = t(`sched.new.problem.${first.code}`);
    reason = first.index >= 0 ? t("sched.new.reason.round", { n: first.index + 1, problem: sentence }) : sentence;
  } else if (hosts.length === 0) reason = t("sched.new.reason.hosts");
  else if (missingSource) reason = t("sched.new.reason.missingHost", { source: t(`sched.new.sources.${missingSource.source}`), host: missingSource.host });
  else if (requestsNumber === null || perQueryNumber === null || unitsNumber === null) reason = t("sched.new.reason.numbers");
  else if (unitsNumber < searches) reason = t("sched.new.reason.units", { n: searches });
  else if (pending) reason = t("sched.new.reason.pending");

  // What the person has typed or chosen; a reload or a closed tab with this changed asks first.
  const snapshot = JSON.stringify({ chosen, inputs, rounds, apis, hostsText, perQuery, requestsEach, unitsText });
  const markSaved = useLeaveWarning(snapshot);

  function change(partial: Partial<Inputs>) {
    const next = { ...shown, ...partial };
    if (edited) { setPending(next); return; }
    setInputs(next);
    const cadence = cadenceOf(next);
    if (cadence) setRounds(generateRounds(cadence, next.prefix));
  }
  function regenerate() {
    const cadence = pending ? cadenceOf(pending) : null;
    if (!pending || !cadence) return;
    setInputs(pending);
    setRounds(generateRounds(cadence, pending.prefix));
    setPending(null);
    setEdited(false);
  }
  function editRound(index: number, field: keyof RoundDraft, value: string) {
    setEdited(true);
    setRounds((rows) => rows.map((r, i) => (i === index ? { ...r, [field]: value } : r)));
  }
  function toggle(source: string) {
    setApis((current) => (current.includes(source) ? current.filter((s) => s !== source) : [...current, source]));
  }

  async function submit() {
    if (reason !== null || sending.current) return;
    sending.current = true;
    setBusy(true);
    setRefusal(null);
    try {
      const result = await control.planPeriodic(project, {
        source_flow_id: flowId, rounds, apis: [...apis].sort(), allowed_hosts: hosts,
        max_units_each: unitsNumber!, max_requests_each: requestsNumber!, per_query: perQueryNumber!,
      });
      markSaved(snapshot);
      navigate(`/p/${encodeURIComponent(project)}/scheduler/s/${encodeURIComponent(result.schedule_id)}`);
    } catch (cause) {
      setRefusal(cause instanceof Error ? cause : new Error(String(cause)));
      sending.current = false;
      setBusy(false);
    }
  }

  if (projects.pending) return <Pending label={t("sched.loading")} />;
  if (projects.error) return <ErrorState error={projects.error} context="projects" />;
  if (flows.length === 0) return <p className="text-sm">{t("sched.new.flow.none")}</p>;

  const summaryHosts = hosts.length ? hosts.join(", ") : "—";
  return (
    <form onSubmit={(e) => { e.preventDefault(); void submit(); }} className="flex flex-col gap-5">
      <p className="text-sm text-muted-foreground">{t("sched.new.lede")}</p>
      <div className={`${cardClass} grid gap-4 sm:grid-cols-2`}>
        <Labeled label={t("sched.new.flow.label")} help={t("sched.new.flow.help")}>
          {(id) => (
            <select id={id} value={flowId} disabled={busy} onChange={(e) => setChosen(e.target.value)} className={inputClass}>
              {flows.map((f) => (
                <option key={f.flow_id} value={f.flow_id}>
                  {t("sched.new.flow.option", { title: f.title ?? t("sched.new.flow.untitled", { id: f.flow_id.slice(0, 12) }), label: f.selector_label })}
                </option>
              ))}
            </select>
          )}
        </Labeled>
        <Labeled label={t("sched.new.prefix")}>
          {(id) => <input id={id} value={shown.prefix} disabled={busy} onChange={(e) => change({ prefix: e.target.value })} className={inputClass} />}
        </Labeled>
        <Labeled label={t("sched.new.cadence.label")}>
          {(id) => (
            <select id={id} value={shown.kind} disabled={busy} onChange={(e) => change({ kind: e.target.value as Inputs["kind"] })} className={inputClass}>
              <option value="monthly">{t("sched.new.cadence.monthly")}</option>
              <option value="weekly">{t("sched.new.cadence.weekly")}</option>
              <option value="days">{t("sched.new.cadence.days")}</option>
            </select>
          )}
        </Labeled>
        {shown.kind === "days" ? (
          <Labeled label={t("sched.new.cadence.every")}>
            {(id) => <input id={id} type="number" min={1} value={shown.every} disabled={busy} onChange={(e) => change({ every: e.target.value })} className={inputClass} />}
          </Labeled>
        ) : null}
        <Labeled label={t("sched.new.start")}>
          {(id) => <input id={id} type="date" value={shown.start} disabled={busy} onChange={(e) => change({ start: e.target.value })} className={inputClass} />}
        </Labeled>
        <Labeled label={t("sched.new.count")}>
          {(id) => <input id={id} type="number" min={1} max={32} value={shown.count} disabled={busy} onChange={(e) => change({ count: e.target.value })} className={inputClass} />}
        </Labeled>
      </div>

      {pending ? (
        <div role="group" aria-label={t("sched.new.regen.ask")} className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card px-4 py-3 text-sm">
          <span>{t("sched.new.regen.ask")}</span>
          <button type="button" onClick={regenerate} disabled={!cadenceOf(pending)} className={primaryClass}>{t("sched.new.regen.yes")}</button>
          <button type="button" onClick={() => setPending(null)} className={quietClass}>{t("sched.new.regen.no")}</button>
        </div>
      ) : null}

      <RoundsEditor rounds={rounds} problems={problems} disabled={busy} onChange={editRound} />
      {flowNotes.map((name) => <p key={name} className="text-sm">{t("sched.new.note.flowExists", { name })}</p>)}

      <fieldset className="flex flex-col gap-2 rounded-xl border border-border bg-card px-4 py-3">
        <legend className="px-1 text-sm font-semibold">{t("sched.new.sources.legend")}</legend>
        {SOURCES.map((source) => (
          <label key={source} className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" checked={apis.includes(source)} disabled={busy} onChange={() => toggle(source)} />
            {t(`sched.new.sources.${source}`)}
          </label>
        ))}
        <p className="text-xs text-muted-foreground">{t("sched.new.sources.help")}</p>
      </fieldset>

      <details className="rounded-xl border border-border bg-card px-4 py-3">
        <summary className="cursor-pointer text-sm font-semibold break-words">
          {t("sched.new.advanced.summary", { hosts: summaryHosts, perQuery: perQuery || "—", requests: requestsEach || "—", units: unitsShown || "—" })}
        </summary>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Labeled label={t("sched.new.advanced.hosts")} help={t("sched.new.advanced.hostsHelp")}>
              {(id) => <textarea id={id} value={hostsShown} disabled={busy} spellCheck={false} onChange={(e) => setHostsText(e.target.value)} className={`${areaClass} w-full font-mono`} />}
            </Labeled>
          </div>
          <Labeled label={t("sched.new.advanced.perQuery")}>
            {(id) => <input id={id} type="number" min={1} value={perQuery} disabled={busy} onChange={(e) => setPerQuery(e.target.value)} className={inputClass} />}
          </Labeled>
          <Labeled label={t("sched.new.advanced.requestsEach")}>
            {(id) => <input id={id} type="number" min={1} value={requestsEach} disabled={busy} onChange={(e) => setRequestsEach(e.target.value)} className={inputClass} />}
          </Labeled>
          <Labeled label={t("sched.new.advanced.unitsEach")} help={searches ? t("sched.new.advanced.unitsHelp", { n: searches }) : undefined}>
            {(id) => <input id={id} type="number" min={1} value={unitsShown} disabled={busy} onChange={(e) => setUnitsText(e.target.value)} className={inputClass} />}
          </Labeled>
        </div>
      </details>

      {extraHosts.length ? <p className="text-sm">{t("sched.new.note.extraHosts", { hosts: extraHosts.join(", ") })}</p> : null}

      <FiguresPanel values={preview} />

      <section aria-label={t("sched.new.after.title")} className="flex flex-col gap-1 rounded-xl border border-border bg-card px-4 py-3 text-sm">
        <h2 className="text-base font-semibold">{t("sched.new.after.title")}</h2>
        <ul className="list-disc pl-5">
          <li>{t("sched.new.after.freeze")}</li>
          <li>{t("sched.new.after.plan")}</li>
          <li>{t("sched.new.after.noRequest")}</li>
          <li>{t("sched.new.after.nothing")}</li>
        </ul>
      </section>

      {overview.error ? <p role="alert" className="text-sm">{t("sched.new.topicsFailed", { message: overview.error.message })}</p> : null}
      {refusal ? (
        <div role="alert" className="text-sm text-red-700 dark:text-red-400">
          <p>{refusal.message}</p>
          {refusal instanceof ControlError && refusal.details.length ? (
            <ul className="list-disc pl-5">{refusal.details.map((d, i) => <li key={i}>{d.path}: {d.message}</li>)}</ul>
          ) : null}
        </div>
      ) : null}
      {reason ? <p id="ns-reason" className="text-sm text-muted-foreground">{t("sched.new.reason.prefix", { reason })}</p> : null}
      <button type="submit" disabled={reason !== null || busy} aria-describedby={reason ? "ns-reason" : undefined} className={`${primaryClass} self-start`}>
        {busy ? t("sched.new.saving") : t("sched.new.submit")}
      </button>
    </form>
  );
}

// "New series": a series of dated updates from a cadence. Saving writes a plan and nothing else; the
// calendar is approved separately on the series page.
export default function NewSeriesPage() {
  const { t } = useLocale();
  const session = useSession();
  const { project: raw } = useParams();
  const project = raw ? decodeURIComponent(raw) : "";
  const here = `/p/${encodeURIComponent(project)}/scheduler/new`;
  return (
    <section className="flex flex-col gap-5">
      <ProjectTabs project={project} />
      <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground">
        <Link to={`/p/${encodeURIComponent(project)}/scheduler`} className="inline-flex min-h-11 items-center hover:underline">{t("sched.series.back")}</Link>
      </nav>
      <h1 className="font-serif text-4xl leading-tight font-normal">{t("sched.new.title")}</h1>
      {!session.ready ? (
        <Pending label={t("shell.checking")} />
      ) : !session.operator ? (
        <p className="text-sm">
          {t("sched.signedOut")}{" "}
          <Link className="underline" to={`/login?next=${encodeURIComponent(here)}`}>{t("sched.signIn")}</Link>
        </p>
      ) : (
        <Body project={project} />
      )}
    </section>
  );
}
