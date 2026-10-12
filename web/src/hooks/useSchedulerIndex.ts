// The project's scheduler index as pages: page one and every cursor the person has followed. A
// refresh reads them again in order; a page whose archive revision differs from page one's is
// dropped, and `409 ARCHIVE_CHANGED` restarts from page one with a notice that goes away with the
// next successful read. Only one read runs at a time, and leaving the page cancels the rest.
import { useCallback, useEffect, useRef, useState } from "react";
import { ControlError, control } from "@/lib/control";
import type { SchedulerIndex } from "@/lib/scheduler";

interface Token { cancelled: boolean; busy: boolean }

const changed = (cause: unknown) => cause instanceof ControlError && cause.code === "ARCHIVE_CHANGED";

async function readChain(project: string, depth: number): Promise<SchedulerIndex[]> {
  const first = await control.schedulerIndex(project);
  const pages = [first];
  while (pages.length < depth) {
    const cursor = pages[pages.length - 1].archive.next_cursor;
    if (!cursor) break;
    const page = await control.schedulerIndex(project, cursor);
    if (page.archive.revision !== first.archive.revision) break;
    pages.push(page);
  }
  return pages;
}

export function useSchedulerIndex(project: string) {
  const [pages, setPages] = useState<SchedulerIndex[] | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [restarted, setRestarted] = useState(false);
  const [busy, setBusy] = useState(false);
  const token = useRef<Token>({ cancelled: false, busy: false });
  const held = useRef<SchedulerIndex[] | null>(null);

  const run = useCallback(async (kind: "refresh" | "more") => {
    const mine = token.current;
    if (mine.busy) return;
    mine.busy = true;
    setBusy(true);
    try {
      let restart = false;
      let next: SchedulerIndex[];
      const current = held.current;
      try {
        if (kind === "more" && current) {
          const cursor = current[current.length - 1].archive.next_cursor;
          if (!cursor) return;
          const page = await control.schedulerIndex(project, cursor);
          if (page.archive.revision !== current[0].archive.revision) throw new ControlError(409, "ARCHIVE_CHANGED", "revision moved");
          next = [...current, page];
        } else {
          next = await readChain(project, current?.length ?? 1);
        }
      } catch (cause) {
        if (!changed(cause)) throw cause;
        restart = true;
        next = await readChain(project, 1);
      }
      if (mine.cancelled) return;
      held.current = next;
      setPages(next);
      setError(null);
      setRestarted(restart);
    } catch (cause) {
      if (mine.cancelled) return;
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      mine.busy = false;
      if (!mine.cancelled) setBusy(false);
    }
  }, [project]);

  useEffect(() => {
    const mine: Token = { cancelled: false, busy: false };
    token.current = mine;
    held.current = null;
    setPages(null);
    setError(null);
    setRestarted(false);
    void run("refresh");
    return () => { mine.cancelled = true; };
  }, [run]);

  const refresh = useCallback(() => { void run("refresh"); }, [run]);
  const more = useCallback(() => { void run("more"); }, [run]);
  return { pages, error, restarted, busy, pending: pages === null && error === null, refresh, more };
}
