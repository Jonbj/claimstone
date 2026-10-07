import { useState } from "react";
import { Link, useParams } from "react-router";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { control } from "@/lib/control";
import type { ExportCreated, ExportVerified } from "@/lib/control";
import { useSession } from "@/lib/session";

// Export (spec v2.1 F6; contracts/exports.md). A snapshot freezes one flow's ledgers; the list is
// the read API's, and the two actions are the control API's. Nothing here runs a check on load:
// Verify is a button, per row, because a verification is an action and never a side effect of
// opening a page (B10). Only flows can be exported, so there is no `/u/` route.
const card = "rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800";
const primary = "min-h-11 rounded-md bg-teal-600 px-4 text-sm font-medium text-white disabled:opacity-50";

type CopyEntry = Record<string, unknown>;

/** The `copies` answer: `{included: [...], excluded: [...]}` or null when copies were not asked for. */
function CopiesAnswer({ copies }: { copies: unknown }) {
  if (copies === null || copies === undefined) {
    return <p className="mt-1 text-sm text-muted-foreground">Copies were not asked for in this snapshot.</p>;
  }
  const c = copies as { included?: CopyEntry[]; excluded?: CopyEntry[] };
  const included = Array.isArray(c.included) ? c.included : [];
  const excluded = Array.isArray(c.excluded) ? c.excluded : [];
  return (
    <div className="mt-2 text-sm">
      <p className="font-semibold">Copies included ({included.length})</p>
      {included.length === 0 ? <p className="text-muted-foreground">none</p> : (
        <ul className="list-disc pl-5">
          {included.map((e, i) => (
            <li key={i}>
              <span className="font-mono text-xs">{String(e.candidate_key)}</span>
              {" · licence "}{String(e.licence ?? "—")}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 font-semibold">Copies left out ({excluded.length})</p>
      {excluded.length === 0 ? <p className="text-muted-foreground">none</p> : (
        <ul className="list-disc pl-5">
          {excluded.map((e, i) => (
            <li key={i}>
              <span className="font-mono text-xs">{String(e.candidate_key)}</span>
              {": "}{String(e.reason ?? "no reason given")}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function ExportPage() {
  const { project: raw, sel: rawSel } = useParams();
  const project = raw ? decodeURIComponent(raw) : "";
  const flowId = rawSel ? decodeURIComponent(rawSel) : "";
  const session = useSession();
  const list = useApi(() => api.exports(project, flowId), [project, flowId]);

  const [includeCopies, setIncludeCopies] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<Error | null>(null);
  const [created, setCreated] = useState<ExportCreated | null>(null);
  const [verifying, setVerifying] = useState<string | null>(null);
  const [verified, setVerified] = useState<Record<string, ExportVerified>>({});
  const [verifyError, setVerifyError] = useState<{ id: string; error: Error } | null>(null);

  async function create() {
    if (creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      const made = await control.createExport(project, flowId, includeCopies);
      setCreated(made);
      list.reload();
    } catch (cause) {
      setCreateError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setCreating(false);
    }
  }

  async function verify(id: string) {
    if (verifying !== null) return;
    setVerifying(id);
    setVerifyError(null);
    try {
      const answer = await control.verifyExport(project, flowId, id);
      setVerified((v) => ({ ...v, [id]: answer }));
    } catch (cause) {
      setVerifyError({ id, error: cause instanceof Error ? cause : new Error(String(cause)) });
    } finally {
      setVerifying(null);
    }
  }

  const base = `/p/${encodeURIComponent(project)}/f/${encodeURIComponent(flowId)}`;
  const signedIn = session.operator !== null;
  const loginLink = (
    <Link to={`/login?next=${encodeURIComponent(`${base}/export`)}`}
          className="text-blue-600 hover:underline dark:text-blue-400">Sign in</Link>
  );

  return (
    <section className="flex flex-col gap-5">
      <header>
        <p className="text-sm"><Link to={base} className="text-blue-600 hover:underline dark:text-blue-400">
          ← {flowId}</Link></p>
        <h1 className="text-[26px]">Export</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          A snapshot freezes the ledgers of one research flow and derives every file from the frozen
          bytes. It can be checked later against the live store.
        </p>
      </header>

      <section className={card}>
        <h2 className="text-base font-semibold">Create a snapshot</h2>
        {!session.ready ? <Pending label="checking the session…" /> : !signedIn ? (
          <p className="mt-1 text-sm text-muted-foreground">Sign in to create a snapshot. {loginLink}</p>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); void create(); }} className="mt-2">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={includeCopies} disabled={creating}
                     onChange={(e) => setIncludeCopies(e.target.checked)} />
              Include copies whose licence allows it
            </label>
            <p className="mt-1 text-xs text-muted-foreground">
              A copy with an unknown licence is left out and listed with its reason.
            </p>
            <button type="submit" disabled={creating} className={`${primary} mt-3`}>
              {creating ? "Creating…" : "Create snapshot"}
            </button>
          </form>
        )}
        {createError ? <div className="mt-2"><ErrorState error={createError} context="create snapshot" /></div> : null}
        {created ? (
          <div className="mt-3 text-sm" role="status">
            <p>
              <span className="font-mono text-xs">{created.export_id}</span>{" "}
              {created.created_now ? "created now" : "already existed: the same bytes, instruments and protocol give the same snapshot"}
            </p>
            <CopiesAnswer copies={created.copies} />
          </div>
        ) : null}
      </section>

      <section className={card}>
        <h2 className="text-base font-semibold">Earlier snapshots</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Verify runs the same check as <span className="font-mono">claimstone export-verify</span>. It
          is an explicit action, never a side effect of opening this page.
        </p>
        {list.error ? <ErrorState error={list.error} context="exports" /> :
         list.pending || !list.data ? <Pending label="loading snapshots…" /> :
         list.data.exports.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">No snapshot has been made for this flow.</p>
        ) : (
          <ul className="mt-2 divide-y divide-border">
            {list.data.exports.map((row) => {
              const result = verified[row.export_id];
              return (
                <li key={row.export_id} className="py-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-mono text-xs break-all">{row.export_id}</span>
                    <span className="text-xs text-muted-foreground">
                      {row.created_at}{row.actor ? ` · by ${row.actor}` : ""}
                    </span>
                    {signedIn ? (
                      <button type="button" disabled={verifying !== null}
                              onClick={() => void verify(row.export_id)}
                              className="min-h-11 rounded-md px-4 text-sm ring-1 ring-gray-300 disabled:opacity-50">
                        {verifying === row.export_id ? "Verifying…" : "Verify"}
                      </button>
                    ) : (
                      <span className="text-xs text-muted-foreground">Sign in to verify. {loginLink}</span>
                    )}
                  </div>
                  {result ? (
                    <div className="mt-1 text-sm" role="status">
                      <p>{result.holds ? "Still holds: the live ledgers begin with the recorded bytes."
                                       : "Does not hold."}</p>
                      {result.problems.length > 0 ? (
                        <ul className="list-disc pl-5 font-mono text-xs">
                          {result.problems.map((p, i) => <li key={i}>{String(p)}</li>)}
                        </ul>
                      ) : null}
                    </div>
                  ) : <p className="mt-1 text-xs text-muted-foreground">Not checked in this visit.</p>}
                  {verifyError?.id === row.export_id ? (
                    <div className="mt-1"><ErrorState error={verifyError.error} context="verify" /></div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </section>
  );
}
