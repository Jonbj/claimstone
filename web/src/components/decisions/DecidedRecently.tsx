import Chip from "@/components/Chip";
import { has, str } from "./rows";
import type { Row } from "@/lib/control";

// The server's own "decided recently" rows, newest first as they arrived, described with the
// row's own words. Nothing is recomputed or re-classified here.
export default function DecidedRecently({ rows }: { rows: Row[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">nothing decided in this flow yet</p>;
  }
  return (
    <ul className="flex flex-col gap-2 text-[13px]">
      {rows.map((row, index) => {
        const kind = str(row.kind);
        const subject = kind === "retry_campaign"
          ? `campaign ${str(row.campaign)}`
          : kind === "purchase_offer"
            ? `offer for ${str(row.candidate_key)}`
            : `identity ${str(row.answer)} on ${str(row.intake_id)}`;
        return (
          <li
            key={str(row.decision_id) || index}
            className="grid items-baseline gap-2 border-t pt-2 sm:grid-cols-[110px_minmax(0,1fr)_auto]"
          >
            <Chip text={str(row.state)} />
            <span>
              {subject}
              {str(row.until) ? <> · returns {str(row.until)}</> : null}
              {str(row.reason) ? <> · {str(row.reason)}</> : null}
            </span>
            <span className="font-mono text-xs text-muted-foreground">{has(row.recorded_at)}</span>
          </li>
        );
      })}
    </ul>
  );
}
