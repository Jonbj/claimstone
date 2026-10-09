import type { Journey } from "@/components/JourneySteps";

// The Source selection block (spec 2026-10-09). These are the screening ledger's advisory
// observations: AI_PROVISIONAL judgements that order work but admit nothing and close no cohort.
// The server sends them already counted; a failure arrives as a named state with no figures, and
// this component prints a fixed sentence for it, never a zero.
type Selection = Journey["selection"];
type Scope = Selection["scopes"][number];

const STATE_TEXT: Record<string, string> = {
  INVENTORY_UNREADABLE: "The inventory file cannot be read. No figures are shown.",
  INVENTORY_DRIFTED:
    "The inventory file no longer matches the hash declared for this scope. No figures are shown.",
  SCREENING_OUTSIDE_INVENTORY:
    "Some screened works are not in the declared inventory. No figures are shown.",
  SELECTION_LEDGER_INVALID: "The screening or identity ledger is not valid. No figures are shown.",
};

const LABELS: [keyof NonNullable<Scope["figures"]>, string][] = [
  ["direct", "direct candidates"],
  ["context", "context"],
  ["not_direct", "not direct"],
  ["uncertain", "uncertain"],
  ["unobserved_count", "not yet observed"],
];

function ScopeBlock({ scope }: { scope: Scope }) {
  const figures = scope.figures;
  return (
    <div className="mt-3 border-t pt-3" data-scope={scope.scope_id}>
      <p className="text-sm">
        <b>{scope.question_id}</b>{" "}
        <span className="font-mono text-xs text-muted-foreground">{scope.scope_id}</span>
      </p>
      {figures === null ? (
        <p className="mt-1 text-sm">
          {STATE_TEXT[scope.state] ?? "This scope cannot be read. No figures are shown."}{" "}
          <code className="text-xs">{scope.state}</code>
        </p>
      ) : (
        <>
          <dl className="mt-2 grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-2.5">
            {LABELS.map(([key, label]) => (
              <div key={key} data-figure={key} className="rounded-lg bg-muted p-2.5">
                <dt className="text-xs text-muted-foreground">
                  {key === "unobserved_count" ? `${label}, of ${figures.inventory_count}` : label}
                </dt>
                <dd className="text-xl font-semibold">{figures[key]}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-xs text-muted-foreground">
            {figures.identity_observations} identity observations (possible versions of the
            same work).
          </p>
        </>
      )}
    </div>
  );
}

export default function SelectionPanel({ selection }: { selection: Selection }) {
  return (
    <section aria-label="Source selection" className="flex flex-col gap-1">
      <h2 className="text-base font-semibold">Source selection</h2>
      <p className="text-sm text-muted-foreground">
        Which works belong in the population. It runs beside the pipeline and admits nothing.
      </p>
      {selection.state === "NO_SCOPE_DECLARED" ? (
        <>
          <p className="mt-2 text-sm">No selection scope is declared for this flow.</p>
          <p className="text-xs text-muted-foreground">This does not mean there is nothing to select.</p>
        </>
      ) : selection.state === "SCOPES_FILE_INVALID" ? (
        <p className="mt-2 text-sm">
          The selection declaration cannot be read. No figures are shown.{" "}
          <code className="text-xs">SCOPES_FILE_INVALID</code>
        </p>
      ) : (
        <>
          <p className="mt-2 rounded-lg px-3 py-2 text-sm ring-1 ring-provisional">
            Advisory · {selection.assessment_status} judgements, not a person's ·{" "}
            {selection.cohort_closed ? "cohort closed" : "cohort open"} · admitted{" "}
            {selection.admitted_candidates}
          </p>
          {selection.scopes.map((scope) => <ScopeBlock key={scope.scope_id} scope={scope} />)}
        </>
      )}
    </section>
  );
}
