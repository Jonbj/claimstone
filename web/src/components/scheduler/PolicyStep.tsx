import { useLocale } from "@/lib/i18n";
import { formatUtc } from "@/lib/datetime";
import type { PolicyStatus } from "@/lib/scheduler";
import StateWord from "./StateWord";
import StepCard from "./StepCard";
import { identityName, ratio, requestsLine, utcRange } from "./format";

function Policy({ row }: { row: PolicyStatus }) {
  const { t } = useLocale();
  const p = row.policy;
  return (
    <div className="flex flex-col gap-1 border-t border-border pt-2 first:border-t-0 first:pt-0">
      <p><StateWord word={row.state} /></p>
      <p className="break-words">{t("sched.policy.hosts", { hosts: p.allowed_hosts.join(", ") })}</p>
      <p>{t("sched.policy.classes", { classes: p.source_classes.join(", ") })}</p>
      <p>{utcRange(p.not_before, p.expires_at)}</p>
      <p>{requestsLine(p.max_requests_each, p.max_candidates, p.max_total_requests)}</p>
      <p>{t("sched.policy.reserved", { ratio: ratio(row.reserved_candidates, p.max_candidates) })}</p>
      <p>{t("sched.policy.requests", { n: row.reserved_requests })}</p>
      {row.events.map((event, i) => (
        <p key={i} className="text-xs">
          <span className="font-mono">{event.event}</span>{" · "}{identityName(event.identity)}{" · "}{formatUtc(event.at)}
        </p>
      ))}
    </div>
  );
}

/** `rows` is null when the grants could not be read at all; an empty list is "not decided". */
export default function PolicyStep({ rows, complete }: { rows: PolicyStatus[] | null; complete: boolean }) {
  const { t } = useLocale();
  const first = rows?.[0];
  const many = (rows?.length ?? 0) > 1;
  const spend = many ? t("sched.policy.spendMany") : first
    ? t("sched.policy.spend", { line: requestsLine(first.policy.max_requests_each, first.policy.max_candidates, first.policy.max_total_requests) })
    : t("sched.policy.spendNone");
  return (
    <StepCard n={3} title={t("sched.policy.title")} state={many ? null : first?.state ?? null}
              permits={t("sched.policy.permits")} forbids={t("sched.policy.forbids")} spend={spend}>
      {rows === null ? <p>{t("sched.series.grantsFailed")}</p>
        : rows.length ? rows.map((row) => <Policy key={row.policy_id} row={row} />)
        : <p>{complete ? t("sched.grant.undecided") : t("sched.grant.notLoaded")}</p>}
    </StepCard>
  );
}
