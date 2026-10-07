import { useEffect, useState } from "react";
import { Link } from "react-router";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import type { ProfileDiff, StoredProfiles } from "@/lib/api-types";

export type StoredProfileList = StoredProfiles["profiles"];
/** An outside request to compare two hashes; `nonce` makes a repeat request count again. */
export interface DiffRequest {
  from: string;
  to: string;
  nonce: number;
}

// R5 (spec §8.3 question page): compare two stored profiles of this question,
// result by result. An **audit view** — it carries no verdict word and concludes
// nothing (invariant 2): every field renders verbatim, a removed entry's reason
// is what the review ledger recorded, never a narrative, and the direction
// counts are labelled a count, never a strength. The read API has no route
// listing a question's stored profile hashes, so the operator pastes them; the
// `from` prefill is the one hash the question page already holds. A comparison
// is fetched only on the compare action, never on load — the collapsed
// `<details>` keeps the page's existing behaviour unchanged (R5.3).
const card = "rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800";
const input = "w-full rounded border border-border bg-card px-2 py-1 font-mono text-xs";

// The contract keeps `added`/`removed` result rows and `changed` field pairs
// open (`[k: string]: unknown`), so the panel reads the keys it renders by name
// and prints anything else verbatim as JSON.
type Row = { [k: string]: unknown };

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <p className="py-0.5 text-sm">
      <span className="font-semibold">{label} </span>
      {children}
    </p>
  );
}

const joined = (entries: [string, unknown][]) =>
  entries.length > 0 ? entries.map(([k, v]) => `${k} ${String(v)}`).join(" · ") : "—";

function text(row: Row | null | undefined, key: string): string {
  const value = row ? row[key] : undefined;
  return value === undefined || value === null ? "" : String(value);
}

function EntryLineageLink({ base, resultId }: { base: string; resultId: string }) {
  return (
    <Link
      to={`${base}/claim/${encodeURIComponent(resultId)}`}
      className="font-mono text-[13px] text-blue-600 hover:underline dark:text-blue-400"
    >
      {resultId.slice(0, 16)}
    </Link>
  );
}

// by_class is per relation ("for"/"against"), each holding per source class —
// rendered as `relation: class n · class n`, verbatim, never aggregated.
function byClassText(side: ProfileDiff["counts"]["from"]): string {
  const relations = Object.entries(side.by_class ?? {}) as [string, unknown][];
  const parts = relations.map(([relation, classes]) => {
    const list = Object.entries((classes ?? {}) as Record<string, unknown>)
      .map(([klass, n]) => `${klass} ${String(n)}`);
    return `${relation}: ${list.length > 0 ? list.join(" · ") : "—"}`;
  });
  return parts.join("; ");
}

export default function ProfileDiffPanel({
  project,
  kind,
  sel,
  qid,
  currentProfileSha256,
  profiles,
  request,
}: {
  project: string;
  kind: "f" | "u";
  sel: string;
  qid: string;
  currentProfileSha256: string | null;
  /** The stored profiles of this question (BR). Empty, null or undefined: the hashes are pasted. */
  profiles?: StoredProfileList | null;
  request?: DiffRequest | null;
}) {
  // `from` prefilled with the question's current stored hash when the page has
  // one; an empty prefill stays empty — a hash the page does not hold is not
  // for this component to invent.
  const [fromSha, setFromSha] = useState(currentProfileSha256 ?? "");
  const [toSha, setToSha] = useState("");
  const [compare, setCompare] = useState<{ from: string; to: string } | null>(null);

  const [open, setOpen] = useState(false);
  const listed = profiles && profiles.length > 0 ? profiles : null;

  useEffect(() => {
    if (!request) return;
    setFromSha(request.from);
    setToSha(request.to);
    setCompare({ from: request.from, to: request.to });
    setOpen(true);
  }, [request?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  const diff = useApi(
    () =>
      compare
        ? api.profileDiff(project, kind, sel, qid, compare.from, compare.to)
        : Promise.resolve(null),
    [project, kind, sel, qid, compare?.from, compare?.to],
  );

  const base = `/p/${encodeURIComponent(project)}/${kind}/${encodeURIComponent(sel)}`;

  function onCompare() {
    if (fromSha.trim() && toSha.trim()) {
      setCompare({ from: fromSha.trim(), to: toSha.trim() });
    }
  }

  return (
    <details className={card} open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="cursor-pointer text-base font-semibold">profile diff</summary>
      <p className="mt-1 text-xs text-muted-foreground">
        {listed
          ? "Compare two stored profiles of this question. "
          : "The read API listed no stored profiles for this question, so paste both hashes. "}
        This is an audit view and carries no verdict.
      </p>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <HashChoice label="from (profile_sha256)" value={fromSha} onChange={setFromSha} profiles={listed} />
        <HashChoice label="to (profile_sha256)" value={toSha} onChange={setToSha} profiles={listed} />
      </div>
      <button
        type="button"
        className="mt-2 rounded bg-primary px-3 py-1 text-sm font-semibold text-primary-foreground disabled:opacity-50"
        disabled={!(fromSha.trim() && toSha.trim())}
        onClick={onCompare}
      >
        compare
      </button>

      {diff.error ? (
        <div className="mt-3">
          <ErrorState error={diff.error} context="profile diff" />
        </div>
      ) : diff.pending && compare ? (
        <div className="mt-3">
          <Pending label="comparing profiles…" />
        </div>
      ) : diff.data ? (
        <div className="mt-3">
          <ProfileDiffBody base={base} data={diff.data} />
        </div>
      ) : null}
    </details>
  );
}

function HashChoice({
  label,
  value,
  onChange,
  profiles,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  profiles: StoredProfileList | null;
}) {
  if (!profiles) {
    return (
      <label className="block">
        <span className="text-xs font-semibold">{label}</span>
        <input
          className={`${input} mt-1`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
        />
      </label>
    );
  }
  return (
    <label className="block">
      <span className="text-xs font-semibold">{label}</span>
      <select
        className={`${input} mt-1`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">— choose a stored profile</option>
        {profiles.map((p) => (
          <option key={p.profile_sha256} value={p.profile_sha256}>
            {`${p.profile_sha256.slice(0, 12)} · built ${p.built_at} · ${p.state ?? "—"}` +
              `${p.provisional ? " · provisional" : ""}${p.current ? " · current" : ""}`}
          </option>
        ))}
      </select>
    </label>
  );
}

function ProfileDiffBody({ base, data }: { base: string; data: ProfileDiff }) {
  const sideText = (side: ProfileDiff["from"]) =>
    `${side.profile_sha256} · built ${side.built_at} · gate v${side.claim_gate_version}` +
    ` · contract v${side.decision_contract_version} · registry v${side.registry_version}`;

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm">
        <span className="font-semibold">added</span> {data.summary.added} ·{" "}
        <span className="font-semibold">removed</span> {data.summary.removed} ·{" "}
        <span className="font-semibold">changed</span> {data.summary.changed}
      </p>
      {data.reason ? (
        <p className="break-all text-sm">
          <span className="font-semibold">reason </span>
          {data.reason}
        </p>
      ) : null}
      <p className="break-all font-mono text-xs text-muted-foreground">
        from {sideText(data.from)}
        <br />
        to {sideText(data.to)}
      </p>

      {data.added.length > 0 ? (
        <div>
          <h3 className="text-sm font-semibold">added</h3>
          {data.added.map((entry, i) => (
            <AddedRemoved key={i} base={base} entry={entry as Row} kind="added" />
          ))}
        </div>
      ) : null}
      {data.removed.length > 0 ? (
        <div>
          <h3 className="text-sm font-semibold">removed</h3>
          {data.removed.map((entry, i) => (
            <AddedRemoved key={i} base={base} entry={entry as Row} kind="removed" />
          ))}
        </div>
      ) : null}
      {data.changed.length > 0 ? (
        <div>
          <h3 className="text-sm font-semibold">changed</h3>
          {data.changed.map((entry, i) => (
            <Changed key={i} base={base} entry={entry as Row} />
          ))}
        </div>
      ) : null}

      <div className="mt-1 rounded bg-muted/40 p-3">
        <h3 className="text-sm font-semibold">counts — a count, not a strength</h3>
        <Field label="from by_class">{byClassText(data.counts.from) || "—"}</Field>
        <Field label="from direction count">
          {joined(Object.entries(data.counts.from.direction_count))}
        </Field>
        <Field label="to by_class">{byClassText(data.counts.to) || "—"}</Field>
        <Field label="to direction count">
          {joined(Object.entries(data.counts.to.direction_count))}
        </Field>
      </div>
    </div>
  );
}

function AddedRemoved({
  base,
  entry,
  kind,
}: {
  base: string;
  entry: Row;
  kind: "added" | "removed";
}) {
  const row = entry.result as Row | null;
  const resultId = String(entry.result_id ?? "");
  const reason = entry.reason;
  return (
    <div className="mt-2 rounded bg-muted/40 p-3">
      <p>
        <EntryLineageLink base={base} resultId={resultId} />
      </p>
      <Field label="claim">{text(row, "claim") || "—"}</Field>
      <Field label="evidence_quote">
        {text(row, "evidence_quote") ? (
          <blockquote className="border-l-[3px] border-border pl-3">
            <q>{String(row?.evidence_quote)}</q>
          </blockquote>
        ) : (
          "—"
        )}
      </Field>
      <Field label="stance">{text(row, "stance") || "—"}</Field>
      <Field label="source_class">{text(row, "source_class") || "—"}</Field>
      {kind === "removed" && reason !== null && reason !== undefined ? (
        // What the review ledger recorded, verbatim — never a narrative.
        <Field label="reason">{String(reason)}</Field>
      ) : null}
    </div>
  );
}

function Changed({ base, entry }: { base: string; entry: Row }) {
  const resultId = String(entry.result_id ?? "");
  const fields = (entry.fields ?? {}) as Record<string, { from?: unknown; to?: unknown }>;
  return (
    <div className="mt-2 rounded bg-muted/40 p-3">
      <p>
        <EntryLineageLink base={base} resultId={resultId} />
      </p>
      {Object.entries(fields).map(([field, pair]) => (
        <Field key={field} label={field}>
          {`${JSON.stringify(pair?.from ?? null)} → ${JSON.stringify(pair?.to ?? null)}`}
        </Field>
      ))}
    </div>
  );
}