// A ledger row shown as labelled text, from the fields the portal knows how to name. Anything
// else in the row is not rendered (and never as raw JSON): the row's own page is the place for it.
const FIELDS: Array<[string, string]> = [
  ["kind", "kind"],
  ["state", "state"],
  ["candidate_key", "candidate"],
  ["candidate_id", "candidate"],
  ["source_id", "source"],
  ["question_id", "question"],
  ["intake_id", "intake"],
  ["decision_id", "decision"],
  ["export_id", "export"],
  ["verdict", "verdict"],
  ["acquired", "acquired"],
  ["failure_class", "failure class"],
  ["claim_id", "claim"],
  ["http_status", "HTTP"],
  ["licence", "licence"],
  ["provisional", "provisional"],
  ["adjudicated_by", "signed by"],
  ["backend", "backend"],
  ["model", "model"],
  ["decision", "decision"],
];

export default function RowFields({ row }: { row: Record<string, unknown> }) {
  const seen = new Set<string>();
  const shown: Array<[string, string]> = [];
  for (const [key, label] of FIELDS) {
    const value = row[key];
    if (value === null || value === undefined) continue;
    if (typeof value !== "string" && typeof value !== "number" && typeof value !== "boolean") continue;
    if (value === "") continue;
    // Two spellings of one field (candidate_key / candidate_id): show the first present.
    if (seen.has(label)) continue;
    seen.add(label);
    shown.push([label, String(value)]);
  }
  if (shown.length === 0) {
    return <span className="text-muted-foreground">no field the portal names</span>;
  }
  return (
    <span className="break-all">
      {shown.map(([label, value], i) => (
        <span key={label}>
          {i > 0 ? " · " : ""}
          <span className="text-muted-foreground">{label}</span>{" "}
          <span className="font-mono">{value.length > 80 ? `${value.slice(0, 80)}…` : value}</span>
        </span>
      ))}
    </span>
  );
}
