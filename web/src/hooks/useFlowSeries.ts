// Which series each flow of a project belongs to, from the schedules' entries in the scheduler index.
// The index needs a session, so signed out there is no request. This only decorates a flow card with a
// link: if the read fails, the cards stay as they are. It reads the first page of the index (25
// schedules); a flow of a series beyond it simply has no chip.
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import { useOperator } from "@/lib/session";

export function useFlowSeries(project: string): Map<string, string> {
  const operator = useOperator();
  const signedIn = operator !== null;
  const index = useApi(() => (signedIn ? control.schedulerIndex(project) : Promise.resolve(null)), [project, signedIn]);
  const out = new Map<string, string>();
  for (const schedule of index.data?.schedules ?? []) {
    for (const entry of schedule.plan.entries) out.set(entry.flow_id, schedule.schedule_id);
  }
  return out;
}
