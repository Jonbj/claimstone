import { useEffect, useState } from "react";

const QUERY = "(min-width: 900px)";

function read(): boolean {
  return typeof matchMedia === "function" ? Boolean(matchMedia(QUERY)?.matches) : true;
}

/** The portal's one breakpoint (the sidebar already turns into a top bar at 900 px). */
export function useWide(): boolean {
  const [wide, setWide] = useState(read);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const list = matchMedia(QUERY);
    const on = () => setWide(Boolean(list?.matches));
    list?.addEventListener?.("change", on);
    on();
    return () => list?.removeEventListener?.("change", on);
  }, []);
  return wide;
}
