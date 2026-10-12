import { Link } from "react-router";
import { useLocale } from "@/lib/i18n";

/** "Series · round NAME", linking to the series page the flow belongs to. */
export default function SeriesChip({ project, scheduleId, round }: { project: string; scheduleId: string; round: string | null }) {
  const { t } = useLocale();
  return (
    <Link to={`/p/${encodeURIComponent(project)}/scheduler/s/${encodeURIComponent(scheduleId)}`}
          className="chip inline-flex min-h-11 items-center break-all underline">
      {round ? t("sched.flowChip", { round }) : t("sched.flowChipNoRound")}
    </Link>
  );
}
