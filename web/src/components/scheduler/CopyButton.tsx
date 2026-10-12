import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/lib/i18n";

/** Copies `value` to the clipboard. "Copied" is announced through a live region that is always in the
 *  page (one that appears with its text is often not read out) and goes away after 2 s. */
export default function CopyButton({ value, label }: { value: string; label: string }) {
  const { t } = useLocale();
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      return;
    }
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 2000);
  }
  return (
    <>
      <button type="button" onClick={copy} aria-label={label}
              className="inline-flex min-h-11 items-center rounded-lg px-3 text-xs ring-1 ring-gray-300 dark:ring-gray-700">
        {t("sched.series.copy")}
      </button>
      <span role="status" className="sr-only">{copied ? t("sched.series.copied") : ""}</span>
    </>
  );
}
