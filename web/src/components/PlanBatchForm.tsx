import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import ErrorState from "@/components/ErrorState";
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import type { PlanBatchBody } from "@/lib/control";
import { useLocale } from "@/lib/i18n";

// `brave` needs two hosts: the search itself, and OpenAlex to confirm the DOI each result carries (D159).
const API_HOSTS = {
  openalex: ["api.openalex.org"],
  crossref: ["api.crossref.org"],
  arxiv: ["export.arxiv.org"],
  europepmc: ["www.ebi.ac.uk"],
  core: ["api.core.ac.uk"],
  brave: ["api.search.brave.com", "api.openalex.org"],
} as const;
// One search, up to 8 lookups, and the robots.txt of both hosts.
const BRAVE_MIN_REQUESTS_EACH = 11;
type Api = keyof typeof API_HOSTS;
const RESOLVER_HOSTS = ["api.unpaywall.org", "api.openalex.org", "api.core.ac.uk"] as const;
const RESOLVER_MIN_REQUESTS_EACH = 12;
const EXACT_HOST = /^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*$/;

export default function PlanBatchForm({ project, flowId, hasCandidates, onPlanned, primary = true }: {
  project: string; flowId: string; hasCandidates: boolean; onPlanned: () => void; primary?: boolean;
}) {
  const { t } = useLocale();
  const [stage, setStage] = useState<"discover" | "acquire">("discover");
  const [apis, setApis] = useState<Api[]>(["openalex"]);
  const [hostsText, setHostsText] = useState("");
  const [perQuery, setPerQuery] = useState(10);
  const [maxUnits, setMaxUnits] = useState(5);
  const [maxRequestsEach, setMaxRequestsEach] = useState(3);
  const [requestsTouched, setRequestsTouched] = useState(false);
  const [retryClasses, setRetryClasses] = useState<string[]>([]);
  const [retryReason, setRetryReason] = useState("");
  const [useApis, setUseApis] = useState(false);
  const [hostsTouched, setHostsTouched] = useState(false);
  // What the record says an acquire plan would need; a suggestion the person edits, never a grant.
  const suggestions = useApi(
    () => (stage === "acquire" ? control.acquireHosts(project, flowId) : Promise.resolve(null)),
    [project, flowId, stage]);
  const suggested = suggestions.data;
  // Hosts an open-access source named as the location of a work not read yet: proposed, never granted.
  const proposedHosts = (suggested?.refused_hosts ?? [])
    .filter((item) => (item.open_access_candidates ?? 0) > 0).map((item) => item.host);
  const listedHosts = hostsText.split(/\r?\n/).map((h) => h.trim());
  useEffect(() => {
    if (stage !== "acquire" || !suggested || hostsTouched) return;
    setHostsText(suggested.candidate_hosts.map((item) => item.host).join("\n"));
    if (suggested.pending_candidates > 0) setMaxUnits(suggested.pending_candidates);
  }, [stage, suggested, hostsTouched]);
  useEffect(() => {
    if (stage === "acquire" && suggested && !requestsTouched &&
        Number.isSafeInteger(suggested.suggested_max_requests_each)) {
      // The resolver lookups (Unpaywall, OpenAlex, CORE) and the robots.txt read of every host each spend one of a
      // candidate's requests before the first file is asked for: measured on 18 candidates at 5 each, 17 stopped
      // at the limit with no download attempted. Below the floor the suggestion would only repeat that.
      setMaxRequestsEach(useApis ? Math.max(suggested.suggested_max_requests_each, RESOLVER_MIN_REQUESTS_EACH)
        : suggested.suggested_max_requests_each);
    }
  }, [stage, suggested, requestsTouched, useApis]);
  useEffect(() => {
    if (stage === "discover" && apis.includes("brave") && !requestsTouched) {
      setMaxRequestsEach((old) => Math.max(old, BRAVE_MIN_REQUESTS_EACH));
    }
  }, [stage, apis, requestsTouched]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const hosts = stage === "discover" ? [...new Set(apis.flatMap((api) => [...API_HOSTS[api]]))]
    : [...new Set([...hostsText.split(/\r?\n/).map((host) => host.trim()).filter(Boolean),
        ...(useApis ? RESOLVER_HOSTS : [])])];
  const positive = [maxUnits, maxRequestsEach, ...(stage === "discover" ? [perQuery] : [])]
    .every((value) => Number.isSafeInteger(value) && value > 0);
  const safeCeiling = positive && Number.isSafeInteger(maxUnits * maxRequestsEach);
  const validHosts = hosts.length > 0 && hosts.every((host) => EXACT_HOST.test(host));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const problem = !safeCeiling ? t("planBatch.positive")
      : !validHosts ? t("planBatch.hostInvalid")
      : stage === "acquire" && retryClasses.length > 0 &&
        (retryReason.trim().length < 1 || retryReason.trim().length > 400)
        ? t("planBatch.retryReasonInvalid") : null;
    setValidation(problem);
    if (problem) return;
    const body: PlanBatchBody = {
      stage, apis: stage === "discover" ? apis : [], allowed_hosts: hosts,
      max_units: maxUnits, max_requests_each: maxRequestsEach,
      per_query: stage === "discover" ? perQuery : 25,
      ...(stage === "acquire" && useApis ? { use_apis: true } : {}),
      ...(stage === "acquire" && retryClasses.length > 0 ? {
        retry_classes: retryClasses, retry_reason: retryReason.trim(),
      } : {}),
    };
    setBusy(true);
    setError(null);
    try {
      await control.planBatch(project, flowId, body);
      onPlanned();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="mb-5 flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:p-5">
      <h3 className="font-semibold">{t("planBatch.heading")}</h3>
      <label className="flex flex-col gap-1 text-sm">{t("planBatch.stage")}
        <select value={stage} disabled={busy} onChange={(e) => {
          const next = e.target.value as "discover" | "acquire";
          setStage(next);
          if (next === "discover") setMaxUnits(5);
        }}
                className="min-h-11 rounded-md border bg-background px-3">
          <option value="discover">{t("planBatch.discover")}</option>
          {hasCandidates ? <option value="acquire">{t("planBatch.acquire")}</option> : null}
        </select>
      </label>
      {stage === "discover" ? (
        <>
          <fieldset disabled={busy} className="flex flex-wrap gap-4 text-sm">
            <legend>{t("planBatch.apis")}</legend>
            {(Object.keys(API_HOSTS) as Api[]).map((api) => (
              <label key={api} className="flex items-center gap-2">
                <input type="checkbox" checked={apis.includes(api)} onChange={(e) =>
                  setApis((old) => e.target.checked ? [...old, api] : old.filter((item) => item !== api))} />
                {api}
              </label>
            ))}
          </fieldset>
          <NumberField label={t("planBatch.perQuery")} value={perQuery} setValue={setPerQuery} busy={busy} />
        </>
      ) : (
        <>
          <label className="flex flex-col gap-1 text-sm">{t("planBatch.exactHosts")}
            <textarea value={hostsText} disabled={busy} onChange={(e) => { setHostsTouched(true); setHostsText(e.target.value); }}
                      rows={4} className="rounded-md border bg-background px-3 py-2" />
          </label>
          {suggested ? <p className="text-sm text-muted-foreground">{t("planBatch.suggested", {
            count: suggested.pending_candidates,
            hosts: suggested.candidate_hosts.map((item) => `${item.host} (${item.candidates})`).join(", ") || "—",
          })}</p> : null}
          {suggested && suggested.refused_hosts.length > 0 ? (
            <div className="flex flex-col gap-1 text-sm">
              <p>{t("planBatch.refusedEarlier")}</p>
              {proposedHosts.length > 0 ? (
                <>
                  <p className="text-muted-foreground">{t("planBatch.proposedNote")}</p>
                  <button type="button" disabled={busy || proposedHosts.every((h) => listedHosts.includes(h))}
                          onClick={() => { setHostsTouched(true);
                            setHostsText((old) => [...old.split(/\r?\n/).map((h) => h.trim()).filter(Boolean),
                              ...proposedHosts.filter((h) => !old.split(/\r?\n/).map((x) => x.trim()).includes(h))].join("\n")); }}
                          className="min-h-11 self-start rounded-md border px-3 disabled:opacity-50">
                    {t("planBatch.addProposed", { hosts: proposedHosts.join(", ") })}
                  </button>
                </>
              ) : null}
              <ul className="flex flex-wrap gap-2">
                {suggested.refused_hosts.map((item) => (
                  <li key={item.host}>
                    <button type="button" disabled={busy || hostsText.split(/\r?\n/).map((h) => h.trim()).includes(item.host)}
                            onClick={() => { setHostsTouched(true);
                              setHostsText((old) => (old.trim() ? `${old.trim()}\n` : "") + item.host); }}
                            className="min-h-11 rounded-md border px-3 disabled:opacity-50">
                      {t("planBatch.addHost", { host: item.host, count: item.candidates })}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={useApis} disabled={busy}
                   onChange={(e) => setUseApis(e.target.checked)} />
            {t("planBatch.useApis")}
          </label>
          {useApis ? <p className="text-sm text-muted-foreground">
            {t("planBatch.useApisNote", { hosts: RESOLVER_HOSTS.join(", ") })}</p> : null}
          {suggested && suggested.suggested_max_requests_each === 5 ?
            <p className="text-sm text-muted-foreground">{t("planBatch.httpSuggestion", {
              count: suggested.plain_http_candidates,
            })}</p> : null}
          {suggested && suggested.retryable_classes?.length > 0 ? (
            <fieldset disabled={busy} className="flex flex-col gap-2 text-sm">
              <legend className="font-medium">{t("planBatch.retryHeading")}</legend>
              <p>{t("planBatch.retryNote")}</p>
              {suggested.retryable_classes.map(({ failure_class, candidates }) => (
                <label key={failure_class} className="flex items-center gap-2">
                  <input type="checkbox" checked={retryClasses.includes(failure_class)}
                    onChange={(e) => {
                      setRetryClasses((old) => e.target.checked
                        ? [...old, failure_class] : old.filter((item) => item !== failure_class));
                      if (!e.target.checked) return;
                      // A retry starts at the candidate's own URL: its host has to be in the plan as well.
                      const own = (suggested.retry_hosts ?? [])
                        .filter((item) => item.failure_class === failure_class).map((item) => item.host);
                      setHostsTouched(true);
                      setHostsText((old) => {
                        const have = old.split(/\r?\n/).map((h) => h.trim()).filter(Boolean);
                        return [...have, ...own.filter((h) => !have.includes(h))].join("\n");
                      });
                    }} />
                  {failure_class} ({candidates})
                </label>
              ))}
              <label className="flex flex-col gap-1">{t("planBatch.retryWhy")}
                <input type="text" maxLength={400} required={retryClasses.length > 0}
                  value={retryReason} onChange={(e) => setRetryReason(e.target.value)}
                  className="min-h-11 rounded-md border bg-background px-3" />
              </label>
            </fieldset>
          ) : null}
        </>
      )}
      <NumberField label={stage === "discover" ? t("planBatch.maxQueries") : t("planBatch.maxCandidates")}
                   value={maxUnits} setValue={setMaxUnits} busy={busy} />
      <NumberField label={stage === "discover" ? t("planBatch.maxRequestsPerQuery") : t("planBatch.maxRequestsEach")}
                   value={maxRequestsEach} setValue={(value) => { setRequestsTouched(true); setMaxRequestsEach(value); }} busy={busy} />
      <p className="text-sm">{t("planBatch.allowedHosts")}: {hosts.length ? hosts.join(", ") : "—"}</p>
      <p className="text-sm font-medium">{t("planBatch.worstCase", {
        count: safeCeiling ? maxUnits * maxRequestsEach : "—", hosts: hosts.length ? hosts.join(", ") : "—",
      })}</p>
      <p className="text-sm text-muted-foreground">{t("planBatch.noRequest")}</p>
      {validation ? <p role="alert" className="text-sm text-not-obtained">{validation}</p> : null}
      {error ? <ErrorState error={error} context="batch" /> : null}
      <button type="submit" disabled={busy} className={`min-h-11 self-start rounded-lg px-4 text-sm font-semibold disabled:opacity-50 ${primary ? "bg-primary text-primary-foreground" : "border border-border bg-card"}`}>
        {busy ? t("planBatch.planning") : t("planBatch.plan")}
      </button>
    </form>
  );
}

function NumberField({ label, value, setValue, busy }: {
  label: string; value: number; setValue: (value: number) => void; busy: boolean;
}) {
  return <label className="flex flex-col gap-1 text-sm">{label}
    <input type="number" min="1" step="1" value={Number.isNaN(value) ? "" : value} disabled={busy}
           onChange={(e) => setValue(e.target.value === "" ? NaN : Number(e.target.value))}
           className="min-h-11 rounded-md border bg-background px-3" />
  </label>;
}
