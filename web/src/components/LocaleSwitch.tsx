import { LOCALES, LOCALE_NAMES, useLocale } from "@/lib/i18n";
import { cn } from "@/lib/utils";

// Two buttons, the current one pressed. The label is the language code; the language's own name,
// in that language, is the tooltip (the accessible name stays "EN" / "IT").
export default function LocaleSwitch() {
  const { locale, setLocale, t } = useLocale();
  return (
    <div role="group" aria-label={t("shell.language")} className="flex gap-1">
      {LOCALES.map((code) => (
        <button
          key={code}
          type="button"
          lang={code}
          title={LOCALE_NAMES[code]}
          aria-pressed={locale === code}
          onClick={() => setLocale(code)}
          className={cn(
            "min-h-8 rounded-md border border-rail-border px-2 text-xs",
            locale === code
              ? "bg-rail-active font-medium text-rail-foreground"
              : "text-rail-muted hover:text-rail-foreground",
          )}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
