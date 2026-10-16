import { useState } from "react";
import type { FormEvent } from "react";
import ErrorState from "@/components/ErrorState";
import { control } from "@/lib/control";
import type { PlanBatchBody } from "@/lib/control";
import { useLocale } from "@/lib/i18n";

const API_HOSTS = {
  openalex: "api.openalex.org",
  crossref: "api.crossref.org",
  arxiv: "export.arxiv.org",
} as const;
type Api = keyof typeof API_HOSTS;
const RESOLVER_HOSTS = ["api.unpaywall.org", "api.openalex.org"] as const;
const EXACT_HOST = /^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*$/;

export default function PlanBatchForm({ project, flowId, hasCandidates, onPlanned }: {
  project: string; flowId: string; hasCandidates: boolean; onPlanned: () => void;
}) {
  const { t } = useLocale();
  const [stage, setStage] = useState<"discover" | "acquire">("discover");
  const [apis, setApis] = useState<Api[]>(["openalex"]);
  const [hostsText, setHostsText] = useState("");
  const [perQuery, setPerQuery] = useState(10);
  const [maxUnits, setMaxUnits] = useState(5);
  const [maxRequestsEach, setMaxRequestsEach] = useState(3);
  const [useApis, setUseApis] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const hosts = stage === "discover" ? apis.map((api) => API_HOSTS[api])
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
      : !validHosts ? t("planBatch.hostInvalid") : null;
    setValidation(problem);
    if (problem) return;
    const body: PlanBatchBody = {
      stage, apis: stage === "discover" ? apis : [], allowed_hosts: hosts,
      max_units: maxUnits, max_requests_each: maxRequestsEach,
      per_query: stage === "discover" ? perQuery : 25,
      ...(stage === "acquire" && useApis ? { use_apis: true } : {}),
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
    <form onSubmit={submit} noValidate className="mb-5 flex flex-col gap-3 rounded-md border border-border p-4">
      <h3 className="font-semibold">{t("planBatch.heading")}</h3>
      <label className="flex flex-col gap-1 text-sm">{t("planBatch.stage")}
        <select value={stage} disabled={busy} onChange={(e) => setStage(e.target.value as "discover" | "acquire")}
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
            <textarea value={hostsText} disabled={busy} onChange={(e) => setHostsText(e.target.value)}
                      rows={4} className="rounded-md border bg-background px-3 py-2" />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={useApis} disabled={busy}
                   onChange={(e) => setUseApis(e.target.checked)} />
            {t("planBatch.useApis")}
          </label>
          {useApis ? <p className="text-sm text-muted-foreground">
            {t("planBatch.useApisNote", { hosts: RESOLVER_HOSTS.join(", ") })}</p> : null}
        </>
      )}
      <NumberField label={stage === "discover" ? t("planBatch.maxQueries") : t("planBatch.maxCandidates")}
                   value={maxUnits} setValue={setMaxUnits} busy={busy} />
      <NumberField label={stage === "discover" ? t("planBatch.maxRequestsPerQuery") : t("planBatch.maxRequestsEach")}
                   value={maxRequestsEach} setValue={setMaxRequestsEach} busy={busy} />
      <p className="text-sm">{t("planBatch.allowedHosts")}: {hosts.length ? hosts.join(", ") : "—"}</p>
      <p className="text-sm font-medium">{t("planBatch.worstCase", {
        count: safeCeiling ? maxUnits * maxRequestsEach : "—", hosts: hosts.length ? hosts.join(", ") : "—",
      })}</p>
      <p className="text-sm text-muted-foreground">{t("planBatch.noRequest")}</p>
      {validation ? <p role="alert" className="text-sm text-not-obtained">{validation}</p> : null}
      {error ? <ErrorState error={error} context="batch" /> : null}
      <button type="submit" disabled={busy} className="min-h-11 self-start rounded-md bg-teal-600 px-4 text-sm font-medium text-white disabled:opacity-50">
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
