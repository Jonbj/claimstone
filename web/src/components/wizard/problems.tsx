import { useEffect, useRef } from "react";
import { ControlError } from "@/lib/control";
import type { FieldProblem } from "@/lib/control";
import { useLocale } from "@/lib/i18n";

export function problemsOf(error: Error | null): FieldProblem[] {
  return error instanceof ControlError ? error.details : [];
}

export function messageFor(problems: FieldProblem[], path: string): string | null {
  const hits = problems.filter((p) => p.path === path);
  return hits.length ? hits.map((p) => p.message).join(" ") : null;
}

/** The message under one field, for the exact path the server named. */
export function FieldError({ problems, path }: { problems: FieldProblem[]; path: string }) {
  const message = messageFor(problems, path);
  return message ? (
    <p role="alert" className="text-[13px] text-destructive">
      {message}
    </p>
  ) : null;
}

/** Every problem in one place, focused when it appears so a keyboard or screen-reader user lands on it. */
export function ErrorSummary({ error }: { error: Error | null }) {
  const { t } = useLocale();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error) ref.current?.focus();
  }, [error]);
  if (!error) return null;
  const problems = problemsOf(error);
  const stale = error instanceof ControlError && error.code === "STALE_REVISION";
  return (
    <div
      ref={ref}
      tabIndex={-1}
      role="alert"
      className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm"
    >
      {stale ? <p>{t("wizard.stale")}</p> : null}
      {problems.length ? (
        <>
          <p className="font-medium">{t("wizard.problems")}</p>
          <ul className="mt-1 list-disc pl-5">
            {problems.map((p) => (
              <li key={`${p.path}:${p.message}`}>
                {p.path ? <code className="font-mono text-xs">{p.path}</code> : null}{" "}
                <span>{p.message}</span>
              </li>
            ))}
          </ul>
        </>
      ) : stale ? null : (
        <p>{error instanceof ControlError ? error.message : t("wizard.errors.generic")}</p>
      )}
    </div>
  );
}
