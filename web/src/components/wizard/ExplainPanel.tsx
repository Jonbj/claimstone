import type { Figures } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { explainParams } from "./figures";
import { useWide } from "./useWide";

const MOMENTS = ["afterSave", "atCreation", "afterStart"] as const;

// "What Claimstone will do": fixed copy from the catalog, plus figures the server computed. The
// three moments are the same text wide or narrow; only the container changes.
export default function ExplainPanel(
  { step, figures, extra = {} }: { step: 1 | 2 | 3 | 4; figures: Figures; extra?: Record<string, string> },
) {
  const { t } = useLocale();
  const wide = useWide();
  const params = explainParams(figures, extra);
  const sections = MOMENTS.map((moment) => ({
    moment,
    title: t(`wizard.explain.${moment}`),
    body: t(`wizard.step${step}.${moment}`, params),
  }));

  return (
    <div className="flex flex-col gap-3 rounded-xl bg-card p-4 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
      <h2 className="text-base font-semibold">{t("wizard.explain.title")}</h2>
      {sections.map(({ moment, title, body }, index) =>
        wide ? (
          <section key={moment} className="border-l-2 border-amber-400 pl-3">
            <h3 className="text-[13px] font-semibold">{title}</h3>
            <p className="mt-1 text-[13px] text-muted-foreground">{body}</p>
          </section>
        ) : (
          <details key={moment} open={index === 0} className="border-l-2 border-amber-400 pl-3">
            <summary className="cursor-pointer text-[13px] font-semibold">{title}</summary>
            <p className="mt-1 text-[13px] text-muted-foreground">{body}</p>
          </details>
        ),
      )}
    </div>
  );
}
