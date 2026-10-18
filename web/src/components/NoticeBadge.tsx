import type { Overview } from "@/lib/api-types";
import { useLocale } from "@/lib/i18n";
import StatePill from "@/components/StatePill";

type Status = Overview["source_tracker"][number]["status"];

// What Crossref reported about a work (D142). A notice is shown, never acted on: nothing here removes a
// claim. `NO_NOTICE_RECORDED` is silence and says so; it is not a green "clean" mark, and a failed lookup is
// its own word. The caller renders nothing for a source nobody asked about (`status` null).
export default function NoticeBadge({ status }: { status: Status }) {
  const { t } = useLocale();
  if (!status) return null;
  if (status.state === "LOOKUP_FAILED") return <StatePill tone="neutral">○ {t("status.failed")}</StatePill>;
  if (status.state === "NO_NOTICE_RECORDED") {
    return <span className="text-xs text-muted-foreground" title={t("status.silent")}>{t("status.silent")}</span>;
  }
  return (
    <>
      {status.notices.map((notice, i) => (
        <StatePill key={`${notice.type}-${i}`} tone={notice.kind === "withdrawing" ? "blocked" : "partial"}>
          {notice.kind === "withdrawing" ? "■ " : "▲ "}
          {notice.kind === "withdrawing" ? t("status.withdrawing") : notice.kind === "correcting" ? t("status.correcting") : t("status.other")}
          {notice.label ? ` · ${notice.label}` : ""}
        </StatePill>
      ))}
    </>
  );
}
