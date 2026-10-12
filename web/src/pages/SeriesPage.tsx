import { useParams } from "react-router";
import ProjectTabs from "@/components/ProjectTabs";
import { useLocale } from "@/lib/i18n";

// Placeholder: the scheduler's page is filled in by a later task of the plan.
export default function SeriesPage() {
  const { t } = useLocale();
  const { project: raw } = useParams();
  const project = raw ? decodeURIComponent(raw) : "";
  return (
    <section className="flex flex-col gap-5">
      <ProjectTabs project={project} />
      <h1 className="font-serif text-4xl leading-tight font-normal">{t("sched.series.title")}</h1>
    </section>
  );
}
