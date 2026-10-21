import type { ReactNode } from "react";

// A block panel that is closed until asked for, so the Execution block opens on what is happening
// and not on every form below it. Native <details>: keyboard and screen-reader behaviour for free.
export default function Fold({ title, children, open = false }: { title: string; children: ReactNode; open?: boolean }) {
  return (
    <details open={open} className="mb-5 rounded-xl border border-border bg-card">
      <summary className="min-h-11 cursor-pointer px-4 py-3 text-sm font-semibold">{title}</summary>
      <div className="px-4 pb-4">{children}</div>
    </details>
  );
}
