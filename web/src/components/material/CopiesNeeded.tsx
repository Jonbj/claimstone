import StateChip from "./StateChip";
import { linksOf, str } from "../decisions/rows";
import type { Row } from "../decisions/rows";
import type { Overview } from "@/lib/api-types";
import { useLocale } from "@/lib/i18n";

type Entry = Overview["source_tracker"][number];

// The documents Claimstone found but could not read (D140). A person decides here whether to get one
// themselves — through a library, a purchase or the author — and uploads the PDF against that exact
// candidate. Nothing here buys anything: the publisher link is the publisher's own page. A copy a person
// supplies counts by the project's declared `supplied_copies` policy, never silently.
//
// Every field is the server's: the title, venue and DOI come from the candidate row, and the cause is
// the stored failure class rendered by the one `failure_display`, so the client derives nothing (F11).

function cause(t: (key: string) => string, failure: string | null): string {
  const code = failure ?? "";
  if (code.includes("PAYWALL_403")) return t("copies.cause.paywall");
  if (code.includes("EXCLUDED_HOST")) return t("copies.cause.excluded");
  if (code.includes("REDIRECT_ERROR")) return t("copies.cause.redirect");
  if (code.includes("NOT_FOUND_404")) return t("copies.cause.notFound");
  if (code.includes("ROBOTS")) return t("copies.cause.robots");
  return code || t("copies.cause.notTried");
}

export default function CopiesNeeded({ entries, intake, onChoose }: {
  entries: Entry[];
  intake: Row[];
  onChoose: (candidateKey: string) => void;
}) {
  const { t } = useLocale();
  const needed = entries.filter((e) => e.state === "not_obtained" || e.state === "not_attempted");
  const offered = new Map<string, string>();
  for (const row of intake) {
    const key = str(linksOf(row).candidate_key);
    if (key && str(row.kind) === "file") offered.set(key, str(row.state));
  }
  return (
    <section id="copies" aria-labelledby="copies-title" className="rounded-xl border border-border bg-card p-5">
      <h2 id="copies-title" className="text-base font-semibold">
        {t("copies.title")} <span className="font-mono text-sm font-medium text-muted-foreground">{needed.length}</span>
      </h2>
      <p className="mb-3 mt-0.5 text-sm text-muted-foreground">{t("copies.lede")}</p>
      {needed.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("copies.none")}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {needed.map((entry) => {
            const state = offered.get(entry.candidate_key);
            return (
              <li key={entry.candidate_key} className="flex flex-wrap items-start gap-x-6 gap-y-3 py-3 first:pt-0 last:pb-0">
                <div className="min-w-0 flex-1 basis-80">
                  <p className="text-base font-medium leading-snug">{entry.title ?? entry.candidate_key}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {[entry.venue, entry.year, entry.source_class].filter(Boolean).join(" · ")}
                  </p>
                  <p className="mt-1.5 text-sm">
                    <span className="text-muted-foreground">{t("copies.why")}</span> {cause(t, entry.failure_display)}
                  </p>
                  {entry.doi ? (
                    <p className="mt-1 break-all font-mono text-xs text-muted-foreground">doi:{entry.doi}</p>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {entry.doi ? (
                    <a
                      href={`https://doi.org/${entry.doi}`}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex min-h-11 items-center rounded-lg border border-border px-3 text-sm font-medium hover:bg-muted"
                    >
                      {t("copies.publisher")} ↗
                    </a>
                  ) : null}
                  {state ? (
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      {t("copies.offered")} <StateChip state={state} />
                    </span>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => onChoose(entry.candidate_key)}
                    className="min-h-11 rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground hover:brightness-95"
                  >
                    {state ? t("copies.replace") : t("copies.upload")}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-3 text-xs text-muted-foreground">{t("copies.policy")}</p>
    </section>
  );
}
