import { useLocale } from "@/lib/i18n";

type Coverage = { found?: number | null; confirmed?: number | null; rate?: number | null; floor?: number | null } | null;

// A profile or verdict that rests on a round below its acquisition floor (D146). It says how much was read,
// against what, and what that does and does not allow; it is never a footnote and never a green mark.
export default function PartialBanner({ coverage }: { coverage: Coverage }) {
  const { t } = useLocale();
  return (
    <div role="note" data-testid="partial-banner"
         className="rounded-lg border border-amber-400 bg-amber-50 p-3 text-sm text-amber-950 dark:bg-amber-950/30 dark:text-amber-100">
      <p className="font-semibold">
        {t("partial.title", { read: coverage?.confirmed ?? "—", found: coverage?.found ?? "—", floor: coverage?.floor ?? "—" })}
      </p>
      <p className="mt-1">{t("partial.body")}</p>
    </div>
  );
}
