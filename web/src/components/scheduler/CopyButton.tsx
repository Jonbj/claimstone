import { useState } from "react";
import { useLocale } from "@/lib/i18n";

/** Copies `value` to the clipboard; a refusal leaves the button as it was. */
export default function CopyButton({ value, label }: { value: string; label: string }) {
  const { t } = useLocale();
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }
  return (
    <button type="button" onClick={copy} aria-label={label}
            className="inline-flex min-h-11 items-center rounded-lg px-3 text-xs ring-1 ring-gray-300 dark:ring-gray-700">
      {copied ? t("sched.series.copied") : t("sched.series.copy")}
    </button>
  );
}
