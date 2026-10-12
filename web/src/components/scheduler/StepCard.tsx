import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useLocale } from "@/lib/i18n";
import StateWord from "./StateWord";

interface StepApi {
  /** A write succeeded: announce `message` once the step's data has been read again, and move the focus
   *  to the step heading. */
  done: (message: string) => void;
  focusHeading: () => void;
}
const StepContext = createContext<StepApi | null>(null);
const NOTHING: StepApi = { done: () => undefined, focusHeading: () => undefined };
export const useStep = (): StepApi => useContext(StepContext) ?? NOTHING;

// One step of a series: a numbered heading, the server's state word, and the three fixed blocks
// that say what the step permits, what it does not, and what it can spend. The live region lives
// here, outside the panels, so it is still there when a panel disappears after a write; it speaks
// only after `version` (the step's data) has changed, i.e. after the page read the result again.
export default function StepCard({ n, title, state, permits, forbids, spend, version = "", children }: {
  n: number; title: string; state?: string | null; permits: string; forbids: string; spend: string;
  /** Changes whenever the data the step shows changes. */
  version?: string;
  children?: ReactNode;
}) {
  const { t } = useLocale();
  const heading = t("sched.step.heading", { n, title });
  const headingRef = useRef<HTMLHeadingElement>(null);
  const pending = useRef<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const first = useRef(true);
  const [said, setSaid] = useState("");

  const say = useCallback(() => {
    if (pending.current === null) return;
    setSaid(pending.current);
    pending.current = null;
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    headingRef.current?.focus();
  }, []);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    say();
  }, [version, say]);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const api = useRef<StepApi>({
    done: (message) => {
      pending.current = message;
      setSaid("");
      // If the re-read brings nothing new (an exact repeat), say it anyway after a moment.
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(say, 4000);
    },
    focusHeading: () => headingRef.current?.focus(),
  });

  return (
    <StepContext.Provider value={api.current}>
      <section aria-label={heading} className="flex flex-col gap-3 rounded-xl border border-border bg-card px-4 py-4">
        <h2 ref={headingRef} tabIndex={-1} className="flex flex-wrap items-center gap-3 text-base font-semibold outline-none">
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
        <span role="status" className="sr-only">{said}</span>
      </section>
    </StepContext.Provider>
  );
}
