import { useState } from "react";
import type { FormEvent } from "react";
import ErrorState from "@/components/ErrorState";
import { control } from "@/lib/control";
import type { OfferBody } from "@/lib/control";

// Record a verified offer (spec F5), with every field `docs/contracts/decisions.md` names:
// candidate, work and version, vendor, price, currency, tax status (optional), terms URL,
// verified-at and what the copy might resolve. The server validates each one; its refusal is
// shown as given, field by field sentence.
const EMPTY = {
  candidate_id: "",
  work_version: "",
  vendor: "",
  price: "",
  currency: "",
  tax_status: "",
  terms_url: "",
  verified_at: "",
  resolves: "",
};

const FIELDS: Array<{ key: keyof typeof EMPTY; label: string; hint?: string; mono?: boolean }> = [
  { key: "candidate_id", label: "Candidate key", mono: true },
  { key: "work_version", label: "Work and version" },
  { key: "vendor", label: "Vendor" },
  { key: "price", label: "Price", mono: true, hint: "a positive decimal, e.g. 27.50" },
  { key: "currency", label: "Currency", mono: true, hint: "ISO 4217, e.g. EUR" },
  { key: "tax_status", label: "Tax status", hint: "optional" },
  { key: "terms_url", label: "Terms URL" },
  { key: "verified_at", label: "Verified at", mono: true, hint: "ISO date-time with a zone" },
];

export default function RecordOfferForm(
  { project, flowId, onDone }: { project: string; flowId: string; onDone: () => void },
) {
  const [values, setValues] = useState(EMPTY);
  const [resolves, setResolves] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [recorded, setRecorded] = useState(false);

  function set(key: keyof typeof EMPTY, value: string) {
    setValues((previous) => ({ ...previous, [key]: value }));
    setRecorded(false);
  }

  async function submit(event: FormEvent) {
    event.preventDefault(); // the CSP has form-action 'none': a native submit is never wanted
    if (busy) return;
    setBusy(true);
    setError(null);
    setRecorded(false);
    try {
      const body: OfferBody = {
        candidate_id: values.candidate_id.trim(),
        work_version: values.work_version.trim(),
        vendor: values.vendor.trim(),
        price: values.price.trim(),
        currency: values.currency.trim(),
        terms_url: values.terms_url.trim(),
        verified_at: values.verified_at.trim(),
        resolves: resolves.trim(),
      };
      if (values.tax_status.trim()) body.tax_status = values.tax_status.trim();
      await control.recordOffer(project, flowId, body);
      setValues(EMPTY);
      setResolves("");
      setRecorded(true);
      onDone();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(false);
    }
  }

  const ready = Object.entries(values)
    .filter(([key]) => key !== "tax_status")
    .every(([, value]) => value.trim()) && resolves.trim();

  return (
    <section
      aria-label="Record a verified offer"
      className="rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800"
    >
      <h2 className="text-base font-semibold">Record a verified offer</h2>
      <p className="mb-3 mt-0.5 text-[13px] text-muted-foreground">
        An offer you verified yourself. Possession never comes from this form: a copy is
        established only by a file that passes intake.
      </p>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {FIELDS.map((field) => (
            <label key={field.key} className="flex flex-col gap-1 text-sm font-medium">
              {field.label}
              <input
                name={field.key}
                value={values[field.key]}
                onChange={(e) => set(field.key, e.target.value)}
                className={field.mono
                  ? "min-h-11 rounded-lg border border-border bg-card px-3 font-mono text-sm font-normal"
                  : "min-h-11 rounded-lg border border-border bg-card px-3 text-sm font-normal"}
              />
              {field.hint ? (
                <span className="text-xs font-normal text-muted-foreground">{field.hint}</span>
              ) : null}
            </label>
          ))}
        </div>
        <label className="flex flex-col gap-1 text-sm font-medium">
          What the copy might resolve
          <textarea
            name="resolves"
            value={resolves}
            onChange={(e) => { setResolves(e.target.value); setRecorded(false); }}
            rows={2}
            className="rounded-lg border border-border bg-card px-3 py-2 text-sm font-normal"
          />
        </label>
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={busy || !ready}
            className="min-h-11 rounded-lg bg-rail px-4 text-sm font-semibold text-rail-foreground disabled:opacity-50"
          >
            {busy ? "Recording…" : "Record verified offer"}
          </button>
          {recorded ? (
            <span data-testid="offer-recorded" className="text-[13px] text-muted-foreground">
              recorded; it is on the open list below
            </span>
          ) : null}
        </div>
      </form>
      {error ? <ErrorState error={error} context="offer" /> : null}
    </section>
  );
}
