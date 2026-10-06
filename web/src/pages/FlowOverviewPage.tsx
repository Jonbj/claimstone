import { useParams } from "react-router";
import Chip from "@/components/Chip";
import ErrorState from "@/components/ErrorState";
import FloorPanel from "@/components/FloorPanel";
import InboxCards from "@/components/InboxCards";
import OverviewKpis from "@/components/OverviewKpis";
import Pending from "@/components/Pending";
import QuestionMatrix from "@/components/QuestionMatrix";
import SourceTracker from "@/components/SourceTracker";
import CommandBlock from "@/components/CommandBlock";
import { BarList } from "@/components/tremor/BarList/BarList";
import { useApi } from "@/hooks/useApi";
import { usePoll } from "@/hooks/usePoll";
import { api } from "@/lib/api";

// The flow/legacy overview (§8.3): binding badge, the four KPI cards, the source
// tracker, the questions table with the rejections side card, the per-class floor
// panel, the inbox, the scoped activity. Polls every 3 s (§4.2 rule 8) and keeps
// the previous numbers on screen with a discreet "refreshing…" while the same view
// recomputes. The BarList is fed only by `rejections_by_reason` (F11); the next
// action is the server's own first card carrying a command, rendered verbatim.
export default function FlowOverviewPage({ kind }: { kind: "f" | "u" }) {
  const { project: raw, sel: rawSel } = useParams();
  const project = raw ? decodeURIComponent(raw) : "";
  const sel = rawSel ? decodeURIComponent(rawSel) : "";

  const overview = useApi(() => api.overview(project, kind, sel), [project, kind, sel]);
  usePoll(project || null, () => overview.reload());

  if (overview.error) return <ErrorState error={overview.error} context="overview" />;
  if (overview.pending || !overview.data) return <Pending label="computing…" />;
  const data = overview.data;

  const base = `/p/${encodeURIComponent(project)}/${kind}/${encodeURIComponent(sel)}`;
  const rejections = Object.entries(
    data.state.rejections_by_reason as Record<string, number>,
  ).map(([name, value]) => ({ name, value }));
  const next = data.inbox.find((card) => card.command !== null) ?? null;
  const flowId = data.flow ? String((data.flow as { flow_id?: unknown }).flow_id ?? "") : "";

  return (
    <section className="flex flex-col gap-5">
      <header>
        <h1 className="text-[22px] font-semibold">
          {data.selector_label}
          {data.legacy ? " — legacy" : ""}
          {overview.refreshing ? (
            <span className="pending ml-3" role="status">
              refreshing…
            </span>
          ) : null}
        </h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {data.project}
          {flowId ? ` · protocol ${flowId.slice(0, 12)}` : ""}
        </p>
      </header>

      {data.legacy ? (
        <section className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
          <h2 className="mb-1 text-sm font-semibold">binding</h2>
          <p>
            <Chip text="legacy: protocol not verified" />
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {data.selector_label} has data and no flow: nothing binds it to the protocol
            it ran under. `claimstone flow create` binds one; until then its figures
            are shown, not certified.
          </p>
        </section>
      ) : data.binding_state ? (
        <section className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
          <h2 className="mb-1 text-sm font-semibold">binding</h2>
          <p className="flex flex-wrap items-baseline gap-2 text-sm">
            <Chip text={data.binding_state.state} />
            {data.binding_state.differences.length > 0 ? (
              <span>— differs in: {data.binding_state.differences.join(", ")}</span>
            ) : (
              <span>— no differences</span>
            )}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            The binding is compared against the live project and never supplies a value
            to a computation (review F4).
          </p>
          {(data.flow as { bound_after_data?: boolean } | null)?.bound_after_data ? (
            <p className="mt-1 text-xs text-muted-foreground">
              bound after data existed: rows written before binding are not verified
              against this protocol
            </p>
          ) : null}
        </section>
      ) : null}

      {data.errors.map((err) => (
        <section
          key={err}
          className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800"
        >
          <h2 className="mb-1 text-sm font-semibold">ledger integrity</h2>
          <p>
            <Chip text={err} />
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Figures that depend on a damaged ledger are withheld, not zero.
          </p>
        </section>
      ))}

      {data.unavailable ? (
        <section className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
          <h2 className="mb-1 text-sm font-semibold">corpus</h2>
          <p>
            <Chip text={data.unavailable} />
          </p>
        </section>
      ) : null}

      <OverviewKpis overview={data} />

      <section className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
        <div className="flex flex-wrap justify-between gap-2">
          <h2 className="text-base font-semibold">Sources in this scope</h2>
          <span className="text-xs text-muted-foreground">
            one block per candidate, server order
          </span>
        </div>
        <div className="mt-3">
          <SourceTracker entries={data.source_tracker} />
        </div>
      </section>

      <div className="flex flex-wrap gap-5">
        <section className="min-w-0 flex-[3_1_560px] overflow-x-auto rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
          <h2 className="mb-3 text-base font-semibold">Questions</h2>
          <QuestionMatrix rows={data.questions.rows} base={base} />
        </section>
        <section className="flex-[2_1_360px] rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
          <h2 className="text-base font-semibold">Rejected by the gate</h2>
          <p className="mb-3 mt-0.5 text-[13px] text-muted-foreground">
            current, by reason — the denominator
          </p>
          {rejections.length > 0 ? (
            <BarList data={rejections} />
          ) : (
            <p className="text-sm text-muted-foreground">
              no gate rejections recorded in this scope
            </p>
          )}
          <div className="mt-4 border-t pt-3.5">
            {next ? (
              <>
                <div className="text-sm font-semibold">Next: {next.subject}</div>
                <p className="mb-2 mt-1 text-xs text-muted-foreground">{next.cause}</p>
                {next.command ? <CommandBlock command={next.command} note={next.note} /> : null}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                no card with a command in this scope
              </p>
            )}
          </div>
        </section>
      </div>

      <FloorPanel panel={data.floor_panel} />

      <section>
        <h2 className="mb-2 text-sm font-semibold">inbox — what a person can do next</h2>
        <InboxCards cards={data.inbox} />
        <p className="mt-2 text-xs text-muted-foreground">
          Commands are text to copy, never buttons: no route here starts work. Cards
          arrive in server order, never sorted by expected result (review F13).
        </p>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold">activity — this scope only</h2>
        {data.activity.map((row, index) => (
          <p key={index} className="flex flex-wrap items-baseline gap-3 py-0.5 text-sm">
            <span className="font-mono text-xs text-muted-foreground">{row.when}</span>
            <span>{row.stage}</span>
            <span className="text-xs text-muted-foreground">
              {JSON.stringify(row.row).slice(0, 220)}
            </span>
          </p>
        ))}
        {data.activity.length === 0 ? (
          <p className="text-sm text-muted-foreground">no rows in this scope</p>
        ) : null}
        <p className="mt-2 text-xs text-muted-foreground">
          Scoped rows carry their own timestamps; rows without one have no trustworthy
          time and are not shown.
        </p>
      </section>
    </section>
  );
}
