import { useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ControlError } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { primaryClass, quietClass } from "@/components/wizard/stepTypes";

// The one confirmation pattern of the scheduler's writes. A box has to be ticked before the button
// works; the button sends exactly what the parent shows (`onConfirm` closes over those values); while
// it runs everything is disabled and a second click sends nothing. The panel keeps NO copy of what
// the server holds: after a success it calls `onDone` and the parent reads again, and a changed plan
// (`409 PLAN_DIFFERS`) clears the box, says so, calls `onDiffers` and is never retried. Any other
// refusal is shown as the server wrote it.
export default function GrantPanel({ explanation, confirmLabel, actionLabel, danger = false, requireRead = true,
                                     disabledReason = null, onConfirm, onDone, onDiffers }: {
  explanation?: ReactNode;
  /** The text of the box ("I have read what this permits…"). */
  confirmLabel: string;
  actionLabel: string;
  danger?: boolean;
  /** False for an action that permits nothing (saving a plan): no box, only the button. */
  requireRead?: boolean;
  /** Why the button cannot work yet, shown beside it. */
  disabledReason?: string | null;
  onConfirm: () => Promise<unknown>;
  onDone: () => void;
  onDiffers: () => void;
}) {
  const { t } = useLocale();
  const base = useId();
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; details: string[] } | null>(null);
  const [done, setDone] = useState(false);
  const running = useRef(false);
  const alertRef = useRef<HTMLDivElement>(null);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);
  // After a failure the focus goes to the sentence, so it is read out.
  useEffect(() => { if (error) alertRef.current?.focus(); }, [error]);

  const ready = (!requireRead || checked) && disabledReason === null;

  async function run() {
    if (running.current || !ready) return;
    running.current = true;
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      await onConfirm();
      if (alive.current) { setChecked(false); setDone(true); }
      onDone();
    } catch (cause) {
      if (!alive.current) return;
      setChecked(false);
      if (cause instanceof ControlError && cause.code === "PLAN_DIFFERS") {
        setError({ message: t("sched.grant.differs"), details: [] });
        onDiffers();
      } else {
        const details = cause instanceof ControlError ? cause.details.map((d) => `${d.path}: ${d.message}`) : [];
        setError({ message: cause instanceof Error ? cause.message : String(cause), details });
      }
    } finally {
      running.current = false;
      if (alive.current) setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border px-3 py-3 text-sm">
      {explanation ? <div>{explanation}</div> : null}
      {requireRead ? (
        <label className="flex min-h-11 items-center gap-2">
          <input type="checkbox" checked={checked} disabled={busy} onChange={(e) => setChecked(e.target.checked)}
                 aria-describedby={error ? `${base}-e` : undefined} />
          {confirmLabel}
        </label>
      ) : null}
      {disabledReason ? <p className="text-muted-foreground">{disabledReason}</p> : null}
      {error ? (
        <div ref={alertRef} id={`${base}-e`} role="alert" tabIndex={-1} className="text-red-700 dark:text-red-400">
          <p>{error.message}</p>
          {error.details.length ? <ul className="list-disc pl-5">{error.details.map((d, i) => <li key={i}>{d}</li>)}</ul> : null}
        </div>
      ) : null}
      <button type="button" onClick={run} disabled={busy || !ready}
              className={`${danger ? quietClass : primaryClass} self-start`}>
        {busy ? t("sched.grant.working") : actionLabel}
      </button>
      <span role="status" className="sr-only">{done ? t("sched.grant.done") : ""}</span>
    </div>
  );
}
