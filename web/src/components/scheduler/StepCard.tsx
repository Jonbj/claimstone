import type { ReactNode } from "react";
import { useLocale } from "@/lib/i18n";
import StateWord from "./StateWord";

// One step of a series: a numbered heading, the server's state word, and the three fixed blocks
// that say what the step permits, what it does not, and what it can spend.
export default function StepCard({ n, title, state, permits, forbids, spend, children }: {
  n: number; title: string; state?: string | null; permits: string; forbids: string; spend: string;
  children?: ReactNode;
}) {
  const { t } = useLocale();
  const heading = t("sched.step.heading", { n, title });
  return (
    <section aria-label={heading} className="flex flex-col gap-3 rounded-xl border border-border bg-card px-4 py-4">
      <h2 className="flex flex-wrap items-center gap-3 text-base font-semibold">
        {heading}
        {state ? <StateWord word={state} /> : null}
      </h2>
      <div className="flex flex-col gap-2 text-sm">{children}</div>
      <dl className="grid gap-2 text-sm sm:grid-cols-3">
        {([["permits", permits], ["forbids", forbids], ["spend", spend]] as const).map(([key, text]) => (
          <div key={key}>
            <dt className="font-medium">{t(`sched.step.${key}`)}</dt>
            <dd className="text-muted-foreground">{text}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
