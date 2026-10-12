import { Link } from "react-router";
import { useLocale } from "@/lib/i18n";
import type { PeriodicCumulativeDossier } from "@/lib/api-types";
import StepCard from "./StepCard";

export default function ResultStep({ project, scheduleId, dossier }: {
  project: string; scheduleId: string; dossier: PeriodicCumulativeDossier | null;
}) {
  const { t } = useLocale();
  return (
    <StepCard n={5} title={t("sched.resultStep.title")} permits={t("sched.resultStep.permits")}
              forbids={t("sched.resultStep.forbids")} spend={t("sched.resultStep.spend")}>
      {dossier ? (
        <>
          <p><span className="text-muted-foreground">{t("sched.resultStep.state")}</span>{" "}
            <b className="font-mono">{dossier.state}</b></p>
          <p><span className="text-muted-foreground">{t("sched.resultStep.firstBlocker")}</span>{" "}
            {dossier.blockers[0] ?? t("sched.resultStep.noBlockers")}</p>
        </>
      ) : <p>{t("sched.resultStep.unavailable")}</p>}
      <Link className="inline-flex min-h-11 items-center underline"
            to={`/p/${encodeURIComponent(project)}/scheduler/s/${encodeURIComponent(scheduleId)}/result`}>
        {t("sched.resultStep.open")}
      </Link>
    </StepCard>
  );
}
