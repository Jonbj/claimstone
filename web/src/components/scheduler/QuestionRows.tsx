import { Link } from "react-router";
import { useLocale } from "@/lib/i18n";
import { questionRowsOf } from "@/lib/scheduler";
import type { QuestionRow } from "@/lib/scheduler";
import CopyButton from "./CopyButton";
import { ratio } from "./format";

const NOT_APPLICABLE = "LITERATURE_VERDICT_NOT_APPLICABLE";

function Profile({ row }: { row: QuestionRow }) {
  const { t } = useLocale();
  const p = row.profile;
  if (!p) return <span>{t("sched.res.q.noProfile")}</span>;
  if (p.state === NOT_APPLICABLE) return <span>{t("sched.res.q.notApplicable")}</span>;
  const counts = Object.entries(p.direction_count ?? {}).map(([k, n]) => `${k}: ${n}`).join(", ");
  return (
    <span className="flex flex-col gap-1">
      {p.state ? <span className="font-mono text-xs">{p.state}</span> : null}
      {p.provisional ? <span>{t("sched.res.q.provisional")}</span> : null}
      {p.blocking?.length ? <span className="font-mono text-xs break-words">{t("sched.series.blocking", { items: p.blocking.join(", ") })}</span> : null}
      {counts ? <span>{t("sched.res.q.counts", { counts })}</span> : null}
      {p.coverage ? <span>{t("sched.res.q.coverage", { ratio: ratio(p.coverage.sources, p.coverage.examined) })}</span> : null}
      {p.profile_sha256 ? (
        <span className="flex items-center gap-2">
          <code className="font-mono text-xs">{p.profile_sha256.slice(0, 12)}</code>
          <CopyButton value={p.profile_sha256} label={t("sched.res.q.copyHash", { id: row.questionId })} />
        </span>
      ) : null}
    </span>
  );
}

function Signature({ row }: { row: QuestionRow }) {
  const { t } = useLocale();
  const d = row.decision;
  const verdict = d?.verdict ? (typeof d.verdict.verdict === "string" ? d.verdict.verdict : t("sched.res.q.signed")) : t("sched.res.q.notSigned");
  return (
    <span className="flex flex-col gap-1">
      <span>{verdict}</span>
      {d?.stale || d?.stored_profile_stale ? <span>{t("sched.res.q.stale")}</span> : null}
      {d?.unavailable ? <span>{d.unavailable}</span> : null}
    </span>
  );
}

// Profiles and human decisions of the whole corpus, joined by question id. The link to a question
// goes to the whole-store reader and exists only when the project lists that reader.
export default function QuestionRows({ project, profiles, decisions, wholeStore }: {
  project: string; profiles: unknown; decisions: unknown; wholeStore: boolean;
}) {
  const { t } = useLocale();
  const rows = questionRowsOf(profiles, decisions);
  return (
    <section aria-label={t("sched.res.q.title")} className="flex flex-col gap-2 rounded-xl border border-border bg-card px-4 py-4 text-sm">
      <h2 className="text-base font-semibold">{t("sched.res.q.title")}</h2>
      {rows.length === 0 ? <p>{t("sched.res.q.empty")}</p> : (
        <table className="w-full text-left">
          <thead>
            <tr>
              <th scope="col">{t("sched.res.q.question")}</th>
              <th scope="col">{t("sched.res.q.profile")}</th>
              <th scope="col">{t("sched.res.q.signature")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.questionId} className="align-top">
                <th scope="row" className="font-mono text-xs font-normal">
                  {wholeStore
                    ? <Link className="underline" to={`/p/${encodeURIComponent(project)}/u/-/q/${encodeURIComponent(row.questionId)}`}>{row.questionId}</Link>
                    : row.questionId}
                </th>
                <td><Profile row={row} /></td>
                <td><Signature row={row} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {Array.isArray(profiles) && profiles.length === 0 ? <p className="text-xs">{t("sched.res.q.noProfiles")}</p> : null}
      <p className="text-xs text-muted-foreground">{t("sched.res.q.note")}</p>
    </section>
  );
}
