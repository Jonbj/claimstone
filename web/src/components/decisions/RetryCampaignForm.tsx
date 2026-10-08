import { useState } from "react";
import type { FormEvent } from "react";
import ErrorState from "@/components/ErrorState";
import { control } from "@/lib/control";
import type { RetryPreview } from "@/lib/control";
import { has } from "./rows";

// Plan a retry campaign (spec F5): candidate keys, then Preview — the server's exact plan
// rendered verbatim, refused hosts included — then a new campaign name and a request ceiling,
// then Approve. Editing the keys after a preview withdraws it: what is approved must be what
// was shown. Nothing here executes: the plan's own sentence says so.
function parseKeys(text: string): string[] {
  return text.split(/[\s,]+/).filter(Boolean);
}

export default function RetryCampaignForm(
  { project, flowId, onDone }: { project: string; flowId: string; onDone: () => void },
) {
  const [idsText, setIdsText] = useState("");
  const [preview, setPreview] = useState<RetryPreview | null>(null);
  const [previewedIds, setPreviewedIds] = useState<string[]>([]);
  const [campaign, setCampaign] = useState("");
  const [maxText, setMaxText] = useState("");
  const [busy, setBusy] = useState<"preview" | "approve" | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [approved, setApproved] = useState(false);

  const ids = parseKeys(idsText);
  const max = Number(maxText);
  const maxValid = Number.isInteger(max) && max >= 1 &&
    (preview === null || max <= preview.max_requests_cap);

  async function runPreview() {
    if (busy !== null || ids.length === 0) return;
    setBusy("preview");
    setError(null);
    setApproved(false);
    try {
      const plan = await control.retryPreview(project, flowId, ids);
      setPreview(plan);
      setPreviewedIds(ids);
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(null);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault(); // the CSP has form-action 'none': a native submit is never wanted
    if (busy !== null || preview === null || !campaign.trim() || !maxValid) return;
    setBusy("approve");
    setError(null);
    try {
      await control.approveRetry(project, flowId, {
        candidate_ids: previewedIds,
        campaign: campaign.trim(),
        max_requests: max,
      });
      setIdsText("");
      setPreview(null);
      setPreviewedIds([]);
      setCampaign("");
      setMaxText("");
      setApproved(true);
      onDone();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section
      aria-label="Plan a retry campaign"
      className="rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800"
    >
      <h2 className="text-base font-semibold">Plan a retry campaign</h2>
      <p className="mb-3 mt-0.5 text-[13px] text-muted-foreground">
        Candidate keys, then Preview: the exact plan the server built, refused hosts included.
        Only what was shown can be approved.
      </p>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm font-medium">
          Candidate keys
          <input
            name="candidate_ids"
            value={idsText}
            onChange={(e) => {
              setIdsText(e.target.value);
              setPreview(null); // a different selection needs a new preview
              setPreviewedIds([]);
              setApproved(false);
            }}
            placeholder="space or comma separated"
            className="min-h-11 rounded-lg border border-border bg-card px-3 font-mono text-sm font-normal"
          />
        </label>
        <button
          type="button"
          onClick={() => void runPreview()}
          disabled={busy !== null || ids.length === 0}
          className="min-h-11 self-start rounded-lg border border-border px-4 text-sm disabled:opacity-50"
        >
          {busy === "preview" ? "Previewing…" : "Preview"}
        </button>
        {preview ? (
          <div data-testid="retry-preview" className="rounded-lg bg-muted/50 p-4 text-[13px]">
            <p className="font-semibold">The exact plan, from the server</p>
            <ul className="mt-1">
              {preview.candidates.map((candidate) => (
                <li key={candidate.candidate_key} className="mt-1 font-mono text-xs">
                  {candidate.candidate_key} · {has(candidate.source_class)} · last failure:{" "}
                  {candidate.last_failure} · hosts:{" "}
                  {candidate.hosts.length > 0 ? candidate.hosts.join(", ") : "none"}
                </li>
              ))}
            </ul>
            <p className="mt-2">
              Hosts that may be contacted:{" "}
              <span className="font-mono">
                {preview.hosts.length > 0 ? preview.hosts.join(", ") : "none"}
              </span>
            </p>
            {Object.entries(preview.refused_hosts).map(([host, why]) => (
              <p key={host} data-refused-host={host} className="mt-1">
                <span className="font-mono">{host}</span> — {why}
              </p>
            ))}
            <p className="mt-2">
              robots: {preview.robots} · at most {preview.max_requests_cap} requests
            </p>
            <p className="mt-1 text-muted-foreground">{preview.executes}</p>
          </div>
        ) : null}
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm font-medium">
            Campaign name
            <input
              name="campaign"
              value={campaign}
              onChange={(e) => { setCampaign(e.target.value); setApproved(false); }}
              placeholder="retry-2026-10-07"
              className="min-h-11 rounded-lg border border-border bg-card px-3 font-mono text-sm font-normal"
            />
            <span className="text-xs font-normal text-muted-foreground">
              a new name, 3–64 of a-z 0-9 . _ -, never “routine”
            </span>
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium">
            Max requests
            <input
              name="max_requests"
              value={maxText}
              onChange={(e) => { setMaxText(e.target.value); setApproved(false); }}
              inputMode="numeric"
              className="min-h-11 rounded-lg border border-border bg-card px-3 font-mono text-sm font-normal"
            />
            <span className="text-xs font-normal text-muted-foreground">
              an integer from 1 to {preview ? preview.max_requests_cap : 50}
            </span>
          </label>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={busy !== null || preview === null || !campaign.trim() || !maxValid}
            className="min-h-11 rounded-lg bg-rail px-4 text-sm font-semibold text-rail-foreground disabled:opacity-50"
          >
            {busy === "approve" ? "Approving…" : "Approve"}
          </button>
          {approved ? (
            <span data-testid="campaign-approved" className="text-[13px] text-muted-foreground">
              approved as a record; it waits for an authorized operation, not for a person
            </span>
          ) : null}
        </div>
      </form>
      {error ? <ErrorState error={error} context="retry campaign" /> : null}
    </section>
  );
}
