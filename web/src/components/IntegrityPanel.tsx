import Chip from "@/components/Chip";
import type { Integrity } from "@/lib/api-types";

// Integrity (§4.1): can these numbers be trusted now. Every state is a named chip with
// its word (§4.2 rule 7); a null is a dash with the "not knowable" title, never a zero
// (rule 1). Display text (`error` strings) is rendered verbatim (rule 5).
export default function IntegrityPanel({ integrity }: { integrity: Integrity }) {
  const ledgerEntries = Object.entries(integrity.ledgers).sort(([a], [b]) =>
    a.localeCompare(b),
  );
  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <h3 className="text-sm font-semibold">
        integrity — can these numbers be trusted now
      </h3>
      <p className="mt-2 text-sm">
        <b>config</b> <Chip text={integrity.config.state} />{" "}
        {integrity.config.error ? (
          <span className="text-sm text-muted-foreground">{integrity.config.error}</span>
        ) : null}
      </p>
      <p className="mt-1 text-sm">
        <b>registry</b> <Chip text={integrity.registry.state} />{" "}
        {integrity.registry.error ? (
          <span className="text-sm text-muted-foreground">{integrity.registry.error}</span>
        ) : null}
      </p>
      <p className="mt-1 text-sm">
        <b>ledger repairs</b> {integrity.ledger_repairs}
      </p>
      <p className="mt-1 text-sm">
        <b>orphans</b>{" "}
        {integrity.orphans === null ? (
          <span title="not knowable">—</span>
        ) : (
          integrity.orphans
        )}
      </p>
      {integrity.invalid_flows.map((fid) => (
        <p key={fid} className="mt-1 flex flex-wrap items-baseline gap-2 text-sm">
          <b>invalid flow row</b>
          <Chip text="id is not the hash of its binding" />
          <span className="font-mono text-xs">{fid.slice(0, 16)}</span>
        </p>
      ))}
      <p className="mt-1 text-sm">
        <b>instruments</b>{" "}
        {integrity.instruments.length ? (
          <>
            <Chip text="NOT acknowledged" />
            {integrity.instruments.map((problem) => (
              <span key={problem} className="block text-sm text-muted-foreground">
                {problem}
              </span>
            ))}
          </>
        ) : (
          <Chip text="acknowledged" />
        )}
      </p>
      <p className="mt-1 text-sm">
        <b>code</b> {(integrity.code.revision ?? "unknown").slice(0, 12)}
        {integrity.code.dirty ? " · dirty" : ""} · grobid{" "}
        {(integrity.code.grobid_image ?? "").slice(0, 40)}
      </p>
      {ledgerEntries.map(([name, entry]) => (
        <p key={name} className="mt-1 flex flex-wrap items-baseline gap-2 text-sm">
          <span className="font-mono text-xs">{name}</span>
          <span>· {entry?.rows} rows</span>
          {entry?.torn_tail ? <Chip text="torn tail" /> : null}
          {entry?.error ? <Chip text={entry.error} /> : null}
        </p>
      ))}
    </section>
  );
}
