import { useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router";
import Chip from "@/components/Chip";
import CommandBlock from "@/components/CommandBlock";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import ProfileDiffPanel from "@/components/ProfileDiffPanel";
import type { DiffRequest } from "@/components/ProfileDiffPanel";
import SignaturePanel from "@/components/SignaturePanel";
import { useApi } from "@/hooks/useApi";
import { usePoll } from "@/hooks/usePoll";
import { api } from "@/lib/api";
import type { QuestionDetail } from "@/lib/api-types";
import { useSession } from "@/lib/session";

// One question (§8.3): the profile, its results with claim links, and any recorded
// verdict. `CommandBlock` shows the adjudicate command with its placeholders — a person
// reads the profile and signs; an agent does not (§4.2 rule 4). The next signing action
// is the server's own `adjudication_card` (the inbox's card), rendered verbatim: null
// means nothing can be signed now. Polls every 3 s (rule 8).
const card = "rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800";

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

export default function QuestionPage({ kind }: { kind: "f" | "u" }) {
  const { project: raw, sel: rawSel, qid: rawQid } = useParams();
  const project = raw ? decodeURIComponent(raw) : "";
  const sel = rawSel ? decodeURIComponent(rawSel) : "";
  const qid = rawQid ? decodeURIComponent(rawQid) : "";

  const detail = useApi(() => api.question(project, kind, sel, qid), [project, kind, sel, qid]);
  const profiles = useApi(() => api.profiles(project, kind, sel, qid), [project, kind, sel, qid]);
  usePoll(project || null, () => detail.reload());
  const session = useSession();
  const location = useLocation();
  const [diffRequest, setDiffRequest] = useState<DiffRequest | null>(null);

  // The last answer this view received. A poll reload that fails must not unmount the page: the
  // signature panel below holds the reasoning somebody is typing, in memory only, and an error
  // state in its place would drop it. The old values stay on screen under a named banner; the
  // first load of a view that fails still shows the plain error state.
  const viewKey = `${project}|${kind}|${sel}|${qid}`;
  const lastGood = useRef<{ key: string; data: QuestionDetail; at: string } | null>(null);
  const failure = useRef<{ error: Error; at: string } | null>(null);
  if (detail.data && lastGood.current?.data !== detail.data) {
    lastGood.current = { key: viewKey, data: detail.data, at: new Date().toISOString() };
  }
  if (detail.error && failure.current?.error !== detail.error) {
    failure.current = { error: detail.error, at: new Date().toISOString() };
  }
  const held = lastGood.current?.key === viewKey ? lastGood.current : null;
  const data: QuestionDetail | null = detail.data ?? held?.data ?? null;
  const refreshFailed = detail.error && held ? failure.current : null;

  if (detail.error && !held) return <ErrorState error={detail.error} context="question" />;
  if (!data) return <Pending label="loading question…" />;

  const base = `/p/${encodeURIComponent(project)}/${kind}/${encodeURIComponent(sel)}`;
  const fields = data.profile_fields;

  // What the signing area shows. The panel appears only for a bound flow, a signed-in person,
  // a question that takes a verdict, and a final stored profile; every other case says why not.
  const note = (text: React.ReactNode) => (
    <section className={card}>
      <h2 className="mb-1 text-base font-semibold">signature</h2>
      <p className="text-sm text-muted-foreground">{text}</p>
    </section>
  );
  const profileHash = fields.profile_sha256;
  let signing: React.ReactNode = null;
  if (data.operational_not_applicable) {
    signing = null; // the verdict section above already shows the API's state
  } else if (kind === "u") {
    signing = note("This selector is not bound to a flow, so it is read-only and signing is not offered.");
  } else if (fields.provisional === true) {
    signing = note("This profile is provisional; signing is not offered for it.");
  } else if (!profileHash || fields.unavailable) {
    signing = note("There is no current stored profile to sign.");
  } else if (!session.ready) {
    signing = <Pending label="checking the session…" />;
  } else if (!session.operator) {
    signing = note(
      <>
        Sign in to sign.{" "}
        <Link
          to={`/login?next=${encodeURIComponent(location.pathname)}`}
          className="text-blue-600 hover:underline dark:text-blue-400"
        >
          Sign in
        </Link>
      </>,
    );
  } else {
    signing = (
      <SignaturePanel
        key={`${project}|${sel}|${qid}`}
        project={project}
        flowId={sel}
        qid={qid}
        operatorName={session.operator.name}
        latestHash={profileHash}
        onReload={() => {
          detail.reload();
          profiles.reload();
        }}
        onCompare={(from, to) => setDiffRequest((r) => ({ from, to, nonce: (r?.nonce ?? 0) + 1 }))}
        onSigned={() => {
          detail.reload();
          profiles.reload();
        }}
      />
    );
  }

  return (
    <section className="flex flex-col gap-5">
      {refreshFailed && held ? (
        <div role="alert" data-testid="refresh-failed"
             className="rounded-lg border border-amber-400 bg-amber-50 p-3 text-sm text-amber-950 dark:bg-amber-950/30 dark:text-amber-100">
          <p className="font-semibold">
            Refresh failed at {refreshFailed.at}; the values shown are from {held.at}.
          </p>
          <p className="mt-1">
            Your unsaved text is kept. The page will try again when the ledgers next change.
          </p>
          <ErrorState error={refreshFailed.error} context="refresh" />
        </div>
      ) : null}
      <header>
        <h1 className="text-[26px] font-normal">
          <span className="font-mono">{data.id}</span>: {data.text}
          {detail.refreshing || (detail.pending && held) ? (
            <span className="pending ml-3" role="status">
              refreshing…
            </span>
          ) : null}
        </h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {data.project} · kind {data.kind}
        </p>
      </header>

      <section className={card}>
        <h2 className="mb-1 text-base font-semibold">profile</h2>
        <Field label="state">
          {fields.state ?? <span title="not knowable">—</span>}
          {fields.provisional ? " · provisional" : ""}
        </Field>
        {fields.blocking.length > 0 ? (
          <Field label="blocking:">{fields.blocking.join(", ")}</Field>
        ) : null}
        <Field label="coverage">
          {String(fields.coverage.sources ?? "—")} / {String(fields.coverage.examined ?? "—")}{" "}
          examined
        </Field>
        <Field label="direction count">
          {joined(Object.entries(fields.direction_count))} ({fields.direction_count_note})
        </Field>
        <Field label="gate rejected">{joined(Object.entries(fields.gate_rejected ?? {}))}</Field>
        <Field label="reviewed, not usable">{joined(Object.entries(fields.reviewed_not_usable ?? {}))}</Field>
        <Field label="awaiting review">{fields.awaiting_review}</Field>
        <Field label="linkage">{String(fields.linkage)}</Field>
        {fields.extraction ? (
          <Field label="extraction">{joined(Object.entries(fields.extraction))}</Field>
        ) : null}
        <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
          profile {fields.profile_sha256 ?? "—"}
        </p>
        {fields.stored_profile_stale ? (
          <p className="mt-1">
            <Chip text="stored profile differs; showing current evidence, run synthesize before signing" />
          </p>
        ) : null}
        {fields.unavailable ? (
          <p className="mt-1 flex flex-wrap items-baseline gap-2 text-sm">
            <Chip text={fields.unavailable} />
            <span className="text-xs text-muted-foreground">
              — profiles shown are historical
            </span>
          </p>
        ) : null}
      </section>

      <section className={card}>
        <h2 className="mb-1 text-base font-semibold">results</h2>
        {data.results.length > 0 ? (
          <table className="mt-2 w-full min-w-[520px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="p-2 font-semibold">claim</th>
                <th className="p-2 font-semibold">source</th>
                <th className="p-2 font-semibold">stance</th>
                <th className="p-2 font-semibold">as written</th>
                <th className="p-2 font-semibold">sample</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((row, index) => (
                <tr key={index} className="border-b border-border/60">
                  <td className="p-2 font-mono text-[13px]">
                    <Link
                      to={`${base}/claim/${encodeURIComponent(String(row.claim_id))}`}
                      className="text-blue-600 hover:underline dark:text-blue-400"
                    >
                      {String(row.claim_id).slice(0, 16)}
                    </Link>
                  </td>
                  <td className="p-2">{String(row.source_id)}</td>
                  <td className="p-2">{String(row.stance)}</td>
                  <td className="p-2">
                    {String(row.estimate_as_written ?? row.contrast_as_written ?? "")}
                  </td>
                  <td className="p-2">{String(row.sample ?? "")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="mt-1 text-sm text-muted-foreground">no results for this scope</p>
        )}
      </section>

      {profiles.error ? <ErrorState error={profiles.error} context="stored profiles" /> : null}
      <ProfileDiffPanel
        project={project}
        kind={kind}
        sel={sel}
        qid={qid}
        currentProfileSha256={fields.profile_sha256}
        profiles={profiles.data?.profiles ?? null}
        request={diffRequest}
      />

      <section className={card}>
        <h2 className="mb-1 text-base font-semibold">verdict</h2>
        {data.operational_not_applicable ? (
          <p>
            <Chip text={data.not_applicable_state ?? "—"} />
          </p>
        ) : data.verdict ? (
          <p className="flex flex-wrap items-baseline gap-2 text-sm">
            <Chip text={data.verdict.verdict} />
            <span>· by {data.verdict.adjudicated_by}</span>
            <span>· {data.verdict.adjudicated_at}</span>
            {data.verdict_stale ? <Chip text="stale" /> : null}
          </p>
        ) : (
          <p className="chip dashed">— no verdict recorded</p>
        )}
        {data.verdict?.rationale ? (
          <p className="mt-1 text-sm">{data.verdict.rationale}</p>
        ) : null}
        {data.operational_not_applicable ? (
          <p className="mt-1 text-xs text-muted-foreground">kind operational: no verdict</p>
        ) : null}
        {data.adjudication_card ? (
          <>
            <p className="mb-2 mt-2 text-xs text-muted-foreground">
              {data.adjudication_card.cause}
            </p>
            {data.adjudication_card.command ? (
              <CommandBlock
                command={data.adjudication_card.command}
                note={data.adjudication_card.note}
              />
            ) : null}
          </>
        ) : null}
        <p className="mt-3 text-xs text-muted-foreground">
          A person reads the profile and signs; an agent does not.
        </p>
      </section>

      {signing}
    </section>
  );
}