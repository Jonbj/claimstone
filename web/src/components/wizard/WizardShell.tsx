import type { ReactNode } from "react";
import { Link } from "react-router";
import { useLocale } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const STEPS = [1, 2, 3, 4] as const;

// Wide: rail | form | explanation. Narrow: the rail is a strip on top, the explanation sits under
// the form (the DOM order is already that order, so no layout trick hides or duplicates anything).
export default function WizardShell(
  { draftId, current, saved, children, explain }:
  { draftId: string; current: number; saved: number[]; children: ReactNode; explain: ReactNode },
) {
  const { t } = useLocale();
  return (
    <div className="grid gap-5 min-[900px]:grid-cols-[210px_minmax(0,1fr)_320px]">
      <nav aria-label={t("wizard.rail.label")} className="min-w-0">
        <ol className="relative flex gap-2 overflow-x-auto min-[900px]:flex-col min-[900px]:overflow-visible">
          {STEPS.map((n) => {
            const done = saved.includes(n);
            const active = n === current;
            return (
              <li key={n} className="min-w-[8.5rem] min-[900px]:min-w-0">
                <Link
                  to={`/new/${encodeURIComponent(draftId)}/${n}`}
                  aria-current={active ? "step" : undefined}
                  className={cn(
                    "flex min-h-11 flex-col justify-center rounded-lg px-3 py-1.5 text-sm ring-1",
                    active
                      ? "bg-rail text-rail-foreground ring-rail"
                      : "bg-card ring-gray-200 hover:bg-muted dark:ring-gray-800",
                  )}
                >
                  <span className="flex items-baseline gap-2 font-medium">
                    <span className="font-mono text-xs">{n}</span>
                    {t(`wizard.steps.${n}.name`)}
                    {active ? <span className="sr-only">, {t("wizard.rail.current")}</span> : null}
                    {done ? <span className="ml-auto text-xs">✓ <span className="sr-only">{t("wizard.rail.done")}</span></span> : null}
                  </span>
                  <span className={cn("hidden text-xs min-[900px]:block", active ? "text-rail-muted" : "text-muted-foreground")}>
                    {t(`wizard.steps.${n}.hint`)}
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
      </nav>
      <div className="flex min-w-0 flex-col gap-4">{children}</div>
      <aside className="min-w-0 min-[900px]:sticky min-[900px]:top-4 min-[900px]:self-start">{explain}</aside>
    </div>
  );
}
