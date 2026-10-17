import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { ControlError, control } from "@/lib/control";
import type { RetryPolicyBody, RetryPolicyStatus } from "@/lib/control";
import { useLocale } from "@/lib/i18n";

// The two resolver hosts a `use_apis` plan adds, as PlanBatchForm does; they are listed and sent,
// never invented by the client.
const RESOLVER_HOSTS = ["api.unpaywall.org", "api.openalex.org"] as const;
const EXACT_HOST = /^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*$/;
const YEAR_MS = 366 * 24 * 3600 * 1000;

function defaultExpiry(): string {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + 30);
  return date.toISOString().slice(0, 10);
}

// A `YYYY-MM-DD` read as the UTC end of that day, or null when it is not a real calendar date.
function endOfDayUtc(text: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return null;
  const [year, month, day] = text.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day, 23, 59, 59));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    return null;
  }
  return date.toISOString();
}

const inRange = (value: number, lo: number, hi: number): boolean =>
  Number.isSafeInteger(value) && value >= lo && value <= hi;

export default function RetryPolicyPanel({ project, flowId }: { project: string; flowId: string }) {
  const { t } = useLocale();
  const rows = useApi(() => control.retryPolicies(project, flowId), [project, flowId]);
  const policies = rows.data?.policies ?? [];
  const authorized = policies.some((policy) => policy.state === "AUTHORIZED");

  // The plan form (only while no AUTHORIZED policy exists for the flow).
  const [hostsText, setHostsText] = useState("");
  const [hostsTouched, setHostsTouched] = useState(false);
  const [maxRetries, setMaxRetries] = useState(20);
  const [maxAttemptsEach, setMaxAttemptsEach] = useState(3);
  const [maxRequestsEach, setMaxRequestsEach] = useState(10);
  const [useApis, setUseApis] = useState(false);
  const [baseDelay, setBaseDelay] = useState(6);
  const [maxDelay, setMaxDelay] = useState(48);
  const [expiresOn, setExpiresOn] = useState(defaultExpiry);

  const [confirming, setConfirming] = useState<{ policy: RetryPolicyStatus; kind: "authorize" | "revoke" } | null>(null);
  const [planChanged, setPlanChanged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const inFlight = useRef(false);

  // Hosts pre-filled from the record only: the hosts of candidates not yet attempted. Hosts an earlier
  // plan refused are deliberately not suggested here: they are usually publishers behind a paywall,
  // and a retry policy that quietly widened to them would defeat the exact-host rule. A suggestion
  // the person edits, never a grant.
  const suggestions = useApi(() => control.acquireHosts(project, flowId), [project, flowId]);
  useEffect(() => {
    if (hostsTouched || !suggestions.data) return;
    setHostsText(suggestions.data.candidate_hosts.map((item) => item.host).join("\n"));
  }, [suggestions.data, hostsTouched]);

  const hosts = [...new Set([
    ...hostsText.split(/\r?\n/).map((host) => host.trim()).filter(Boolean),
    ...(useApis ? RESOLVER_HOSTS : []),
  ])];
  const validHosts = hosts.length > 0 && hosts.every((host) => EXACT_HOST.test(host));
  const numbersValid = inRange(maxRetries, 1, 200) && inRange(maxAttemptsEach, 1, 5) &&
    inRange(maxRequestsEach, 1, 20) && inRange(baseDelay, 1, 72);
  const delayValid = inRange(maxDelay, baseDelay, 168);
  const expiresIso = endOfDayUtc(expiresOn);
  const expiresValid = expiresIso !== null && Date.parse(expiresIso) > Date.now() &&
    Date.parse(expiresIso) - Date.now() <= YEAR_MS;

  // The nominal backoff `min(max, base·2^(n-1))` for n = 1..max_attempts_each, and nothing beyond it.
  const nominalReady = Number.isSafeInteger(baseDelay) && Number.isSafeInteger(maxDelay) &&
    Number.isSafeInteger(maxAttemptsEach) && maxAttemptsEach >= 1 && baseDelay >= 1 && maxDelay >= baseDelay;
  const waits = nominalReady
    ? Array.from({ length: maxAttemptsEach }, (_, i) => `${Math.min(maxDelay, baseDelay * 2 ** i)} h`).join(", then ")
    : "—";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const problem = !validHosts ? t("retryPolicy.hostsInvalid")
      : !numbersValid ? t("retryPolicy.numbersInvalid")
      : !delayValid ? t("retryPolicy.delayInvalid")
      : !expiresValid ? t("retryPolicy.expiresInvalid") : null;
    setValidation(problem);
    if (problem) return;
    const body: RetryPolicyBody = {
      allowed_hosts: hosts,
      max_retries: maxRetries,
      max_attempts_each: maxAttemptsEach,
      max_requests_each: maxRequestsEach,
      use_apis: useApis,
      base_delay_hours: baseDelay,
      max_delay_hours: maxDelay,
      expires_at: expiresIso as string,
    };
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      await control.planRetryPolicy(project, flowId, body);
      rows.reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function confirm() {
    if (!confirming || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    const { policy, kind } = confirming;
    try {
      if (kind === "authorize") {
        // The hash and limits go back exactly as the list returned them: the server refuses a plan
        // that differs (409 PLAN_DIFFERS), and that refusal is a reload, never a resend.
        await control.authorizeRetryPolicy(project, policy.policy_id, {
          policy_sha256: policy.policy_id,
          max_retries: policy.policy.max_retries,
          max_requests_each: policy.policy.max_requests_each,
          max_total_requests: policy.policy.max_total_requests,
        });
      } else {
        await control.revokeRetryPolicy(project, policy.policy_id);
      }
      setConfirming(null);
      setPlanChanged(false);
      rows.reload();
    } catch (cause) {
      if (cause instanceof ControlError && cause.code === "PLAN_DIFFERS") {
        setConfirming(null);
        setPlanChanged(true);
        rows.reload();
      } else {
        setError(cause instanceof Error ? cause : new Error(String(cause)));
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return <section aria-label={t("retryPolicy.heading")} className="mb-5 rounded-md border border-border p-4">
    <h2 className="font-semibold">{t("retryPolicy.heading")}</h2>
    {rows.error ? <ErrorState error={rows.error} context="retry policies" /> : null}
    {rows.pending || rows.refreshing ? <Pending label={t("retryPolicy.loading")} /> : null}
    {rows.data && !rows.refreshing ? policies.length > 0 ? policies.map((policy) =>
      <div key={policy.policy_id} className="mt-3 text-sm">
        <p>{t("retryPolicy.state")}: {policy.state} · {policy.policy_id}</p>
        <p>{t("retryPolicy.hosts")}: {policy.policy.allowed_hosts.join(", ")}</p>
        <p>{t("retryPolicy.retries", { remaining: policy.remaining_retries, max: policy.policy.max_retries })}</p>
        <p>{t("retryPolicy.requests", { reserved: policy.reserved_requests, max: policy.policy.max_total_requests })}</p>
        <p>{t("retryPolicy.expires")}: {policy.policy.expires_at}</p>
        <p>{t("retryPolicy.baseDelay")}: {policy.policy.base_delay_hours} h</p>
        <p>{t("retryPolicy.maxDelay")}: {policy.policy.max_delay_hours} h</p>
        <p>{t("retryPolicy.attempts")}: {policy.policy.max_attempts_each}</p>
        {policy.state === "PLANNED" ? (
          <button type="button" disabled={busy} onClick={() => { setConfirming({ policy, kind: "authorize" }); setError(null); setPlanChanged(false); }}
            className="min-h-11 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50">
            {t("retryPolicy.authorize")}</button>
        ) : policy.state === "AUTHORIZED" ? (
          <button type="button" disabled={busy} onClick={() => { setConfirming({ policy, kind: "revoke" }); setError(null); setPlanChanged(false); }}
            className="min-h-11 rounded-md border px-3 disabled:opacity-50">
            {t("retryPolicy.revoke")}</button>
        ) : null}
      </div>) : <p className="mt-2 text-sm">{t("retryPolicy.none")}</p> : null}

    {rows.data && !authorized ? (
      <form onSubmit={submit} noValidate className="mt-4 flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">{t("retryPolicy.exactHosts")}
          <textarea value={hostsText} disabled={busy} onChange={(event) => { setHostsTouched(true); setHostsText(event.target.value); }}
            rows={4} className="rounded-md border bg-background px-3 py-2" />
        </label>
        <NumberField label={t("retryPolicy.maxRetries")} value={maxRetries} setValue={setMaxRetries} busy={busy} min={1} max={200} />
        <NumberField label={t("retryPolicy.attempts")} value={maxAttemptsEach} setValue={setMaxAttemptsEach} busy={busy} min={1} max={5} />
        <NumberField label={t("retryPolicy.maxRequestsEach")} value={maxRequestsEach} setValue={setMaxRequestsEach} busy={busy} min={1} max={20} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={useApis} disabled={busy}
            onChange={(event) => setUseApis(event.target.checked)} />
          {t("retryPolicy.useApisCheck")}
        </label>
        {useApis ? <p className="text-sm text-muted-foreground">{t("retryPolicy.useApisNote")}</p> : null}
        <NumberField label={t("retryPolicy.baseDelayLabel")} value={baseDelay} setValue={setBaseDelay} busy={busy} min={1} max={72} />
        <NumberField label={t("retryPolicy.maxDelayLabel")} value={maxDelay} setValue={setMaxDelay} busy={busy} min={baseDelay} max={168} />
        <p className="text-sm text-muted-foreground">
          {nominalReady
            ? `${t("retryPolicy.nominal")}: ${t("retryPolicy.preview", { waits, max: maxDelay })}`
            : `${t("retryPolicy.nominal")}: —`}
        </p>
        <label className="flex flex-col gap-1 text-sm">{t("retryPolicy.expiresOn")}
          <input type="date" value={expiresOn} disabled={busy} min={new Date().toISOString().slice(0, 10)}
            onChange={(event) => setExpiresOn(event.target.value)}
            className="min-h-11 rounded-md border bg-background px-3" />
        </label>
        <p className="text-sm">{t("retryPolicy.does")}</p>
        <p className="text-sm">{t("retryPolicy.doesNot")}</p>
        <p className="text-sm">{t("retryPolicy.revocable")}</p>
        <p className="text-sm">{t("retryPolicy.planningNothing")}</p>
        {validation ? <p role="alert" className="text-sm text-not-obtained">{validation}</p> : null}
        <button type="submit" disabled={busy}
          className="min-h-11 self-start rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50">
          {busy ? t("retryPolicy.planning") : t("retryPolicy.plan")}
        </button>
      </form>
    ) : null}

    {planChanged ? <p role="alert" className="mt-3 text-sm">{t("retryPolicy.planChanged")}</p> : null}
    {confirming ? <div role="dialog" aria-modal="true"
      aria-label={confirming.kind === "authorize" ? t("retryPolicy.confirmAuthorize") : t("retryPolicy.confirmRevoke")}
      className="mt-4 rounded-lg bg-card p-5 ring-2 ring-primary">
      <h3 className="font-semibold">{confirming.kind === "authorize" ? t("retryPolicy.confirmAuthorize") : t("retryPolicy.confirmRevoke")}</h3>
      {confirming.kind === "authorize" ? <ul className="list-disc pl-5 text-sm">
        <li>{t("retryPolicy.hosts")}: {confirming.policy.policy.allowed_hosts.join(", ")}</li>
        <li>{t("retryPolicy.maxRetries")}: {confirming.policy.policy.max_retries}</li>
        <li>{t("retryPolicy.maxRequestsEach")}: {confirming.policy.policy.max_requests_each}</li>
        <li>{t("retryPolicy.maxTotal")}: {confirming.policy.policy.max_total_requests}</li>
        <li>{t("retryPolicy.attempts")}: {confirming.policy.policy.max_attempts_each}</li>
        <li>{t("retryPolicy.baseDelay")}: {confirming.policy.policy.base_delay_hours} h</li>
        <li>{t("retryPolicy.maxDelay")}: {confirming.policy.policy.max_delay_hours} h</li>
        <li>{t("retryPolicy.expires")}: {confirming.policy.policy.expires_at}</li>
        <li>{t("retryPolicy.useApis")}: {confirming.policy.policy.use_apis ? t("retryPolicy.on") : t("retryPolicy.off")}</li>
      </ul> : <p className="text-sm">{confirming.policy.policy_id}</p>}
      <div className="mt-3 flex gap-3">
        <button type="button" disabled={busy} onClick={confirm}
          className="min-h-11 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50">
          {t("retryPolicy.confirm")}</button>
        <button type="button" disabled={busy} onClick={() => setConfirming(null)}
          className="min-h-11 rounded-md border px-3">
          {t("retryPolicy.cancel")}</button>
      </div>
    </div> : null}
    {error ? <ErrorState error={error} context="retry policy" /> : null}
  </section>;
}

function NumberField({ label, value, setValue, busy, min, max }: {
  label: string; value: number; setValue: (value: number) => void; busy: boolean; min: number; max: number;
}) {
  return <label className="flex flex-col gap-1 text-sm">{label}
    <input type="number" min={min} max={max} step="1" value={Number.isNaN(value) ? "" : value} disabled={busy}
      onChange={(event) => setValue(event.target.value === "" ? NaN : Number(event.target.value))}
      className="min-h-11 rounded-md border bg-background px-3" />
  </label>;
}
