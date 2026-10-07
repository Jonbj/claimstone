import CampaignCard from "@/components/decisions/CampaignCard";
import IdentityCard from "@/components/decisions/IdentityCard";
import OfferCard from "@/components/decisions/OfferCard";
import type { OpenDecision } from "@/lib/control";
import { str } from "./rows";

// One open card, dispatched on the server's own `type` word. An unknown type is still shown,
// neutral and empty of controls — server data is never dropped silently.
export default function OpenDecisionCard(
  { item, project, flowId, onDone }: {
    item: OpenDecision;
    project: string;
    flowId: string;
    onDone: () => void;
  },
) {
  if (item.type === "identity") {
    return <IdentityCard item={item} project={project} flowId={flowId} onDone={onDone} />;
  }
  if (item.type === "purchase_offer") {
    return <OfferCard item={item} project={project} flowId={flowId} onDone={onDone} />;
  }
  if (item.type === "retry_campaign") {
    return <CampaignCard item={item} project={project} flowId={flowId} onDone={onDone} />;
  }
  return (
    <section
      aria-label={`decision ${item.id}`}
      data-open-id={item.id}
      className="rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800"
    >
      <p className="text-sm">
        <span className="font-mono">{item.type}</span>
        <span className="ml-2 text-xs text-muted-foreground">
          candidate {str(item.candidate_key)} — no controls for this type; the server decides
          what it is
        </span>
      </p>
    </section>
  );
}
