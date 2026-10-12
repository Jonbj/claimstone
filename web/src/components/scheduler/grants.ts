// Finds the copy policies and local mandates of one series. The index lists every grant of the
// project, paged; a grant belongs to a series only by its own `schedule_id`. The first read walks
// the index (bounded) and remembers which ids matched and the index revision; a refresh then reads
// those ids and a one-row probe, and walks again only when the revision moved.
import { ControlError, control } from "@/lib/control";
import type { MandateStatus, PolicyStatus, Worker } from "@/lib/scheduler";

export const MAX_PAGES = 10;
export const WALK_LIMIT = 100;

/** Set to cancelled when the page is left: a walk stops before its next request. */
export interface Cancel { cancelled: boolean }

export interface SeriesGrants {
  policies: PolicyStatus[];
  mandates: MandateStatus[];
  /** Each mandate's worker with the time it was read; the probe carries only some of them. */
  mandateWorkers: Record<string, { worker: Worker; at: string }>;
  /** The index revision the matched ids were found under. */
  revision: string;
  /** False when pages remained after MAX_PAGES. */
  complete: boolean;
}

async function walk(project: string, scheduleId: string, cancel: Cancel): Promise<SeriesGrants> {
  const out: SeriesGrants = { policies: [], mandates: [], mandateWorkers: {}, revision: "", complete: true };
  let cursor: string | null = null;
  for (let page = 0; page < MAX_PAGES; page++) {
    if (cancel.cancelled) throw new Error("cancelled");
    const answer = await control.schedulerIndex(project, cursor, WALK_LIMIT);
    if (page === 0) out.revision = answer.archive.revision;
    out.policies.push(...answer.copy_policies.filter((p) => p.policy.schedule_id === scheduleId));
    out.mandates.push(...answer.local_mandates.filter((m) => m.mandate.schedule_id === scheduleId));
    const at = new Date().toISOString();
    for (const [id, worker] of Object.entries(answer.workers.mandates)) out.mandateWorkers[id] = { worker, at };
    cursor = answer.archive.next_cursor;
    if (!cursor) return out;
  }
  return { ...out, complete: false };
}

/** One restart is allowed if the archive changed while paging (409 ARCHIVE_CHANGED). */
export async function findSeriesGrants(project: string, scheduleId: string, cancel: Cancel): Promise<SeriesGrants> {
  try {
    return await walk(project, scheduleId, cancel);
  } catch (cause) {
    if (cause instanceof ControlError && cause.code === "ARCHIVE_CHANGED") return walk(project, scheduleId, cancel);
    throw cause;
  }
}

/** Reads again what is already known: the matched ids, and one index row for the revision and the
 *  workers. A moved revision means grants may have been added: walk again. */
export async function refreshGrants(project: string, scheduleId: string, previous: SeriesGrants,
                                    cancel: Cancel): Promise<SeriesGrants> {
  if (cancel.cancelled) throw new Error("cancelled");
  const probe = await control.schedulerIndex(project, null, 1);
  if (probe.archive.revision !== previous.revision) return findSeriesGrants(project, scheduleId, cancel);
  const [policies, mandates] = await Promise.all([
    Promise.all(previous.policies.map((p) => control.copyPolicy(project, p.policy_id))),
    Promise.all(previous.mandates.map((m) => control.localMandate(project, m.mandate_id))),
  ]);
  const at = new Date().toISOString();
  const mandateWorkers = { ...previous.mandateWorkers };
  for (const [id, worker] of Object.entries(probe.workers.mandates)) mandateWorkers[id] = { worker, at };
  return { ...previous, policies, mandates, mandateWorkers };
}
