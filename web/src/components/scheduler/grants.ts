// Finds the copy policies and local mandates of one series. The index lists every grant of the
// project, paged; a grant belongs to a series only by its own `schedule_id`. The walk is bounded:
// past MAX_PAGES the answer says the grants are not fully loaded rather than guessing.
import { ControlError, control } from "@/lib/control";
import type { MandateStatus, PolicyStatus, Worker } from "@/lib/scheduler";

export const MAX_PAGES = 10;

export interface SeriesGrants {
  policies: PolicyStatus[];
  mandates: MandateStatus[];
  mandateWorkers: Record<string, Worker>;
  /** False when pages remained after MAX_PAGES. */
  complete: boolean;
}

async function walk(project: string, scheduleId: string): Promise<SeriesGrants> {
  const out: SeriesGrants = { policies: [], mandates: [], mandateWorkers: {}, complete: true };
  let cursor: string | null = null;
  for (let page = 0; page < MAX_PAGES; page++) {
    const answer = await control.schedulerIndex(project, cursor);
    out.policies.push(...answer.copy_policies.filter((p) => p.policy.schedule_id === scheduleId));
    out.mandates.push(...answer.local_mandates.filter((m) => m.mandate.schedule_id === scheduleId));
    Object.assign(out.mandateWorkers, answer.workers.mandates);
    cursor = answer.archive.next_cursor;
    if (!cursor) return out;
  }
  return { ...out, complete: false };
}

/** One restart is allowed if the archive changed while paging (409 ARCHIVE_CHANGED). */
export async function findSeriesGrants(project: string, scheduleId: string): Promise<SeriesGrants> {
  try {
    return await walk(project, scheduleId);
  } catch (cause) {
    if (cause instanceof ControlError && cause.code === "ARCHIVE_CHANGED") return walk(project, scheduleId);
    throw cause;
  }
}
