import { Link } from "react-router";
import StateChip from "./StateChip";
import { has, linksOf, str } from "../decisions/rows";
import type { Row } from "@/lib/control";

// The intake list (spec F5): every item proposed for this flow with its latest state, newest
// first, in the order the server returns. A POSSIBLE_VERSION item is a person's identity
// question, so it links to this flow's Decisions page.
export default function IntakeList({ items, decisionsTo }: { items: Row[]; decisionsTo: string }) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">nothing proposed for this flow yet</p>;
  }
  return (
    <ul className="flex flex-col gap-3">
      {items.map((row, index) => {
        const state = str(row.state);
        const candidate = str(linksOf(row).candidate_key);
        return (
          <li key={`${str(row.intake_id)}-${index}`} className="border-t pt-3 first:border-t-0 first:pt-0">
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="min-w-0 break-all font-mono text-sm font-medium">
                {has(str(row.submitted) || str(row.value))}
              </span>
              <span className="text-xs text-muted-foreground">
                {str(row.kind)}
                {candidate ? <> · for <span className="font-mono">{candidate}</span></> : null}
              </span>
              <span className="ml-auto font-mono text-xs text-muted-foreground">
                {has(row.recorded_at)}
              </span>
              <StateChip state={state} />
            </div>
            <p className="mt-1 text-[13px] text-muted-foreground">{has(row.reason)}</p>
            {state === "POSSIBLE_VERSION" ? (
              <p className="mt-1 text-[13px]">
                waits for your identity answer on{" "}
                <Link to={decisionsTo} data-testid="identity-link" className="underline">
                  Decisions
                </Link>
                ; it will never count as a separate study if it is a version
              </p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
