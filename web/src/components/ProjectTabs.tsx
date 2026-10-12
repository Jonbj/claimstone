import { Link, useLocation } from "react-router";
import { useLocale } from "@/lib/i18n";

// Two tabs under a project's breadcrumb. The flows tab is the project page (or, for a single-flow
// project, the flow's journey it redirects to); the scheduler tab is the series of dated updates.
export default function ProjectTabs({ project }: { project: string }) {
  const { t } = useLocale();
  const { pathname } = useLocation();
  const base = `/p/${encodeURIComponent(project)}`;
  const onScheduler = pathname.startsWith(`${base}/scheduler`);
  const link = "inline-flex min-h-11 items-center rounded-lg px-3 text-sm";
  return (
    <nav aria-label={t("sched.tabs.label")} className="flex gap-1 border-b border-border">
      <Link to={`${base}?details=1`} aria-current={onScheduler ? undefined : "page"}
            className={`${link} ${onScheduler ? "text-muted-foreground" : "bg-card font-semibold"}`}>
        {t("sched.tabs.flows")}
      </Link>
      <Link to={`${base}/scheduler`} aria-current={onScheduler ? "page" : undefined}
            className={`${link} ${onScheduler ? "bg-card font-semibold" : "text-muted-foreground"}`}>
        {t("sched.tabs.scheduler")}
      </Link>
    </nav>
  );
}
