import { useState } from "react";
import ErrorState from "@/components/ErrorState";
import { control } from "@/lib/control";
import type { Overview } from "@/lib/api-types";
import { useLocale } from "@/lib/i18n";
import StateChip from "./StateChip";

type Lead = Overview["citation_suggestions"][number];

// Leads from citation edges around this flow's own candidates (D143). They are suggestions: nothing is
// fetched and nothing counts until a person proposes one, and then it goes through the same intake as any
// proposal. The number beside a lead is how many of our sources link to it — a count of seeds, not a
// measure of relevance (invariant 7) — and the page says so.
export default function CitationLeads({ project, flowId, leads, onDone }: {
  project: string; flowId: string; leads: Lead[]; onDone: () => void;
}) {
  const { t } = useLocale();
  const [busy, setBusy] = useState<string | null>(null);
  const [states, setStates] = useState<Record<string, string>>({});
  const [error, setError] = useState<Error | null>(null);

  if (leads.length === 0) return null;

  async function propose(lead: Lead) {
    if (busy) return;
    setBusy(lead.doi);
    setError(null);
    try {
      const answer = await control.submitIntake(project, flowId, {
        kind: "doi", value: lead.doi, note: t("leads.note", { n: lead.links }),
      });
      setStates((old) => ({ ...old, [lead.doi]: String(answer.intake.state ?? "") }));
      onDone();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section id="leads" aria-labelledby="leads-title" className="rounded-xl border border-border bg-card p-5">
      <h2 id="leads-title" className="text-base font-semibold">
        {t("leads.title")} <span className="font-mono text-sm font-medium text-muted-foreground">{leads.length}</span>
      </h2>
      <p className="mb-3 mt-0.5 text-sm text-muted-foreground">{t("leads.lede")}</p>
      <ul className="flex flex-col divide-y divide-border">
        {leads.map((lead) => (
          <li key={lead.doi} className="flex flex-wrap items-start gap-x-6 gap-y-2 py-3 first:pt-0 last:pb-0">
            <div className="min-w-0 flex-1 basis-80">
              <p className="text-base font-medium leading-snug">{lead.title ?? `doi:${lead.doi}`}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {[lead.venue, lead.year].filter(Boolean).join(" · ")}
                {lead.venue || lead.year ? " · " : ""}
                <span className="font-mono">doi:{lead.doi}</span>
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {t("leads.links", { n: lead.links })}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <a href={`https://doi.org/${lead.doi}`} target="_blank" rel="noreferrer noopener"
                 className="inline-flex min-h-11 items-center rounded-lg border border-border px-3 text-sm font-medium hover:bg-muted">
                {t("leads.open")} ↗
              </a>
              {states[lead.doi] ? (
                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                  {t("leads.proposed")} <StateChip state={states[lead.doi]} />
                </span>
              ) : (
                <button type="button" disabled={busy !== null} onClick={() => void propose(lead)}
                        className="min-h-11 rounded-lg border border-border px-4 text-sm font-semibold hover:bg-muted disabled:opacity-50">
                  {busy === lead.doi ? t("leads.sending") : t("leads.propose")}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {error ? <div className="mt-3"><ErrorState error={error} context="proposal" /></div> : null}
    </section>
  );
}
