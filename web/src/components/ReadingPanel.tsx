import { Link } from "react-router";
import Chip from "@/components/Chip";
import type { MatrixRow } from "@/components/QuestionMatrix";
import { useLocale } from "@/lib/i18n";

// What a person reads before signing, one card per literature question: the direction count (labelled
// a count), the coverage it rests on, what the gate rejected and what still blocks signing. It restates
// the server's row and decides nothing; the profile itself is one click away even when it cannot be
// signed yet, so the block is never an empty line.
export default function ReadingPanel({ rows, base }: { rows: MatrixRow[]; base: string }) {
  const { t } = useLocale();
  const literature = rows.filter((row) => !row.operational_not_applicable);
  if (literature.length === 0) return null;
  return (
    <section aria-label={t("reading.heading")} className="flex flex-col gap-3">
      {literature.map((row) => {
        const directions = Object.entries(row.direction_count).map(([name, count]) => `${name} ${String(count)}`);
        const rejected = Object.entries(row.gate_rejected).map(([name, count]) => `${name} ${String(count)}`);
        return (
          <article key={row.id} data-question-id={row.id}
                   className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4 sm:px-5">
            <div className="flex flex-wrap items-center gap-2">
              <Link to={`${base}/q/${encodeURIComponent(row.id)}`} className="font-mono text-sm text-link hover:underline">{row.id}</Link>
              <Chip text={row.verdict ?? (row.display_state === "no_verified_claim" ? "NO_VERIFIED_CLAIM" : row.display_state)} />
              {row.partial ? <Chip text="partial" title={t("reading.partialNote")} /> : null}
            </div>
            <p className="text-sm">{row.text}</p>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs text-muted-foreground sm:grid-cols-2">
              <div><dt className="inline">{t("reading.direction")}: </dt>
                <dd className="inline font-mono text-foreground">{directions.length > 0 ? directions.join(" · ") : "—"}</dd>
                <dd className="text-[11px]">{row.direction_count_note}</dd></div>
              <div><dt className="inline">{t("reading.coverage")}: </dt>
                <dd className="inline font-mono text-foreground">
                  {row.coverage.sources ?? "—"} / {row.coverage.examined ?? "—"}
                </dd></div>
              <div><dt className="inline">{t("reading.rejected")}: </dt>
                <dd className="inline font-mono text-foreground">{row.gate_rejected_total}{rejected.length > 0 ? ` (${rejected.join(", ")})` : ""}</dd></div>
              <div><dt className="inline">{t("reading.awaitingReview")}: </dt>
                <dd className="inline font-mono text-foreground">{row.awaiting_review}</dd></div>
            </dl>
            {row.blocking.length > 0 ? (
              <p className="text-xs"><span className="text-muted-foreground">{t("reading.blocking")}: </span>
                <span className="font-mono">{row.blocking.join(", ")}</span></p>
            ) : null}
            <div>
              <Link to={`${base}/q/${encodeURIComponent(row.id)}`}
                    className="inline-flex min-h-11 items-center rounded-lg border border-border bg-card px-4 text-sm font-medium hover:bg-muted">
                {t("reading.open")}
              </Link>
            </div>
          </article>
        );
      })}
    </section>
  );
}
