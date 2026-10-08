import Chip from "@/components/Chip";
import type { OpenDecision } from "@/lib/control";
import DeferDecline from "./DeferDecline";
import { has, str } from "./rows";

// An open retry-campaign decision (spec F5). A campaign is recorded only by its approval, so
// an open one is a deferral whose date has come: it offers defer-again and decline, never a
// re-approval — a new approval over new facts is a new campaign through the form below.
export default function CampaignCard(
  { item, project, flowId, onDone }: {
    item: OpenDecision;
    project: string;
    flowId: string;
    onDone: () => void;
  },
) {
  const row = item.item;
  const plan = typeof row.plan === "object" && row.plan !== null
    ? (row.plan as Record<string, unknown>)
    : {};
  const hosts = Array.isArray(plan.hosts) ? plan.hosts.map(String) : [];

  return (
    <section
      aria-label={`campaign ${item.id}`}
      data-open-id={item.id}
      className="flex flex-col gap-3 rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800"
    >
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="rounded-full bg-neutral-soft px-2.5 py-0.5 text-xs font-semibold text-neutral-ink">
          Optional · retry campaign
        </span>
        <span className="font-mono text-[13px] text-muted-foreground">
          campaign {str(row.campaign)}
        </span>
        <span className="ml-auto font-mono text-xs text-muted-foreground">{has(item.recorded_at)}</span>
      </div>
      <p className="flex flex-wrap items-baseline gap-2 text-[17px] font-medium">
        Retry campaign {str(row.campaign)}
        <Chip text={str(row.state)} />
      </p>
      <p className="text-[13px]">
        at most {has(row.max_requests)} requests · hosts{" "}
        <span className="font-mono">{hosts.length > 0 ? hosts.join(", ") : "—"}</span>
      </p>
      {str(row.until) ? (
        <p className="text-[13px] text-muted-foreground">
          deferred until {has(row.until)} — the date has come, so it is on the open list again
        </p>
      ) : null}
      {str(row.reason) ? (
        <p className="text-[13px] text-muted-foreground">{str(row.reason)}</p>
      ) : null}
      <DeferDecline
        project={project}
        flowId={flowId}
        decisionId={item.id}
        onDone={onDone}
        allowDecline
      />
      <p className="text-xs text-muted-foreground">
        An approval is a record until an authorized operation names it; declining it makes no
        request to any host.
      </p>
    </section>
  );
}
