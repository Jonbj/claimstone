import { useRef, useState } from "react";
import type { FormEvent } from "react";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { ControlError, MAX_UPLOAD_BYTES, uploadIntakeFile } from "@/lib/control";
import type { Row } from "@/lib/control";
import StateChip from "./StateChip";
import { has, str } from "../decisions/rows";

// Upload a file for one candidate (spec F5): a target fed from the overview's source tracker
// entries, a PDF picker, an upload with progress. The client refuses a file over 50 MiB before
// anything is sent; the server is still the authority. Progress is text, never a style
// attribute — the CSP has style-src 'self' without 'unsafe-inline'.
const MAX_MIB = Math.round(MAX_UPLOAD_BYTES / (1024 * 1024));

export default function UploadForm(
  { project, flowId, onDone }: { project: string; flowId: string; onDone: () => void },
) {
  const overview = useApi(() => api.overview(project, "f", flowId), [project, flowId]);
  const [target, setTarget] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [percent, setPercent] = useState<number | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [result, setResult] = useState<Row | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  function pick(chosen: File | undefined) {
    setError(null);
    setResult(null);
    if (!chosen) {
      setFile(null);
      return;
    }
    if (chosen.size > MAX_UPLOAD_BYTES) {
      // Refused before anything is sent; the server keeps the same limit and stays the authority.
      setFile(null);
      if (picker.current) picker.current.value = "";
      setError(new ControlError(413, "TOO_LARGE", `a file must be at most ${MAX_MIB} MiB`));
      return;
    }
    setFile(chosen);
  }

  async function submit(event: FormEvent) {
    event.preventDefault(); // the CSP has form-action 'none': a native submit is never wanted
    if (busy || !file || !target) return;
    setBusy(true);
    setError(null);
    setResult(null);
    setPercent(0);
    try {
      const answer = await uploadIntakeFile(project, flowId, target, file, (loaded, total) => {
        setPercent(total > 0 ? Math.round((loaded / total) * 100) : null);
      });
      setResult(answer.intake);
      setFile(null);
      setPercent(null);
      if (picker.current) picker.current.value = "";
      onDone();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
      setPercent(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      aria-label="Upload a file"
      className="rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800"
    >
      <h2 className="text-base font-semibold">Upload a file</h2>
      <p className="mb-3 mt-0.5 text-[13px] text-muted-foreground">
        A PDF you hold for one candidate of this flow. It is quarantined, checked by the
        engine's own gates, and counted only by its declared policy — at most {MAX_MIB} MiB.
      </p>
      {overview.error ? (
        <ErrorState error={overview.error} context="the candidate list" />
      ) : overview.pending || !overview.data ? (
        <Pending label="the candidate list…" />
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex max-w-xl flex-col gap-1 text-sm font-medium">
            Target candidate
            <select
              name="target"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              required
              className="min-h-11 rounded-lg border border-border bg-card px-3 font-mono text-sm font-normal"
            >
              <option value="">choose a candidate…</option>
              {overview.data.source_tracker.map((entry) => (
                <option key={entry.candidate_key} value={entry.candidate_key}>
                  {entry.candidate_key} · {entry.source_class} · {entry.state}
                </option>
              ))}
            </select>
            <span className="text-xs font-normal text-muted-foreground">
              key · source class · acquisition state, as the overview reports them
            </span>
          </label>
          <label className="flex max-w-xl flex-col gap-1 text-sm font-medium">
            PDF
            <input
              ref={picker}
              name="file"
              type="file"
              accept="application/pdf,.pdf"
              onChange={(e) => pick(e.target.files?.[0])}
              required
              className="min-h-11 rounded-lg border border-border bg-card px-3 text-sm font-normal"
            />
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={busy || file === null || !target}
              className="min-h-11 rounded-lg bg-rail px-4 text-sm font-semibold text-rail-foreground disabled:opacity-50"
            >
              {busy ? "Uploading…" : "Upload"}
            </button>
            {percent !== null ? (
              <span role="status" className="font-mono text-xs text-muted-foreground">
                uploading {percent}%
              </span>
            ) : null}
          </div>
        </form>
      )}
      {result ? (
        <div data-testid="upload-result" className="mt-3 rounded-lg bg-muted/50 p-3 text-[13px]">
          <p className="flex flex-wrap items-baseline gap-2">
            <span className="font-mono">{has(str(result.value).slice(0, 16))}</span>
            <StateChip state={str(result.state)} />
            <span className="ml-auto font-mono text-xs text-muted-foreground">
              {has(result.recorded_at)}
            </span>
          </p>
          <p className="mt-1 text-muted-foreground">{has(result.reason)}</p>
        </div>
      ) : null}
      {error ? <ErrorState error={error} context="upload" /> : null}
    </section>
  );
}
