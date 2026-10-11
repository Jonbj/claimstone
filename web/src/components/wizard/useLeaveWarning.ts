import { useEffect, useState } from "react";

/** Warns (the browser's own dialog) when the page is closed or reloaded with typing that was never
 *  saved. `snapshot` is the form's current content as a string; `markSaved(s)` records what was
 *  sent. In-app navigation is not guarded: a router blocker needs a data router. */
export function useLeaveWarning(snapshot: string): (saved: string) => void {
  const [baseline, setBaseline] = useState(snapshot);
  const dirty = snapshot !== baseline;
  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = ""; // some browsers only warn when this is set
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  return setBaseline;
}
