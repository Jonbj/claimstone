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
export function FieldError({ problems, path, id }: { problems: FieldProblem[]; path: string; id?: string }) {
  const message = messageFor(problems, path);
  // Not an alert: the summary is the one announcement; this text is linked to its input instead.
  return message ? (
    <p id={id} className="text-[13px] text-destructive">
      {message}
    </p>
  ) : null;
}

/** The sentence for a code the engine is known to send; the key is literal in every branch. */
function sentenceFor(code: string, t: (key: string) => string): string | null {
  switch (code) {
    case "STALE_REVISION": return t("wizard.errors.STALE_REVISION");
    case "DRAFT_CLOSED": return t("wizard.errors.DRAFT_CLOSED");
    case "PREVIEW_CHANGED": return t("wizard.errors.PREVIEW_CHANGED");
    case "NAME_TAKEN": return t("wizard.errors.NAME_TAKEN");
    case "INCOMPLETE": return t("wizard.errors.INCOMPLETE");
    case "UNAUTHORIZED": return t("wizard.errors.UNAUTHORIZED");
    case "VALIDATION": return t("wizard.errors.VALIDATION");
    default: return null;
  }
}

/** Every problem in one place, focused when it appears so a keyboard or screen-reader user lands on it.
 *  A known code gets a sentence in the page's language; the server's own message stays beneath it,
 *  and field-level details stay exactly as the engine wrote them. */
export function ErrorSummary({ error, onReload }: { error: Error | null; onReload?: () => void }) {
  const { t } = useLocale();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error) ref.current?.focus();
  }, [error]);
  if (!error) return null;
  const problems = problemsOf(error);
  const code = error instanceof ControlError ? error.code : "";
  const sentence = sentenceFor(code, t);
  const reloadable = code === "STALE_REVISION" || code === "PREVIEW_CHANGED";
  return (
    <div
      ref={ref}
      tabIndex={-1}
      role="alert"
      className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm"
    >
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
      ) : (
        <>
          <p>{sentence ?? (error instanceof ControlError ? error.message : t("wizard.errors.generic"))}</p>
          {sentence && error instanceof ControlError && error.message ? (
            <p className="mt-1 text-xs text-muted-foreground">{error.message}</p>
          ) : null}
        </>
      )}
      {reloadable && onReload ? (
        <button type="button" onClick={onReload} className="mt-2 min-h-11 rounded-lg border border-border px-3">
          {t("wizard.reload")}
        </button>
      ) : null}
    </div>
  );
}
