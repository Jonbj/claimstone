import { useId } from "react";
import { formatUtc } from "@/lib/datetime";
import { useLocale } from "@/lib/i18n";
import type { ProblemCode, RoundDraft, RoundProblem } from "@/lib/cadence";
import { inputClass } from "@/components/wizard/stepTypes";

type Field = keyof RoundDraft;

function RoundRow({ n, round, problems, disabled, onChange }: {
  n: number; round: RoundDraft; problems: ProblemCode[]; disabled: boolean;
  onChange: (field: Field, value: string) => void;
}) {
  const { t } = useLocale();
  const base = useId();
  const problemId = `${base}-p`;
  const input = (field: Field, label: string, help?: string) => (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={`${base}-${field}`} className="text-sm font-medium">{label}</label>
      <input id={`${base}-${field}`} value={round[field]} disabled={disabled} spellCheck={false}
             onChange={(e) => onChange(field, e.target.value)} className={`${inputClass} w-full break-all`} />
      {help ? <span className="text-xs text-muted-foreground">{help}</span> : null}
    </div>
  );
  return (
    <fieldset aria-describedby={problems.length ? problemId : undefined}
              className="grid gap-3 rounded-xl border border-border bg-card px-4 py-3 sm:grid-cols-2">
      <legend className="px-1 text-sm font-semibold">{t("sched.new.round.legend", { n })}</legend>
      {input("round", t("sched.new.round.name"))}
      {input("title", t("sched.new.round.title"))}
      {input("not_before", t("sched.new.round.start"), formatUtc(round.not_before))}
      {input("expires_at", t("sched.new.round.end"), formatUtc(round.expires_at))}
      {problems.length ? (
        <p id={problemId} className="text-sm text-red-700 sm:col-span-2 dark:text-red-400">
          {problems.map((code) => t(`sched.new.problem.${code}`)).join(" ")}
        </p>
      ) : null}
    </fieldset>
  );
}

// One fieldset per round. The early problems of `checkRounds` sit inside the round they belong to and
// are linked to it; the server stays the authority and its sentence is shown if it differs.
export default function RoundsEditor({ rounds, problems, disabled, onChange }: {
  rounds: RoundDraft[]; problems: RoundProblem[]; disabled: boolean;
  onChange: (index: number, field: Field, value: string) => void;
}) {
  const { t } = useLocale();
  const general = problems.filter((p) => p.index === -1);
  return (
    <section aria-label={t("sched.new.rounds.title")} className="flex flex-col gap-3">
      <h2 className="text-base font-semibold">{t("sched.new.rounds.title")}</h2>
      <p className="text-sm text-muted-foreground">{t("sched.new.rounds.help")}</p>
      <p className="text-xs text-muted-foreground">{t("sched.new.round.format")}</p>
      {general.length ? <p role="status" className="text-sm text-red-700 dark:text-red-400">{general.map((p) => t(`sched.new.problem.${p.code}`)).join(" ")}</p> : null}
      {rounds.map((round, index) => (
        <RoundRow key={index} n={index + 1} round={round} disabled={disabled}
                  problems={problems.filter((p) => p.index === index).map((p) => p.code)}
                  onChange={(field, value) => onChange(index, field, value)} />
      ))}
    </section>
  );
}
