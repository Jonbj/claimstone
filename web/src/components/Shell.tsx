import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router";
import ThemeToggle from "@/components/ThemeToggle";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

// §8.3 shell: white top bar with the product name, the tabs (Projects · Flows · Inbox ·
// Administration) and, on the right, `read-only · rev <12 chars>`. The content sits on
// gray-50 with a max width of 1360 px.
const TABS: Array<{ id: string; label: string; to: string; active: (pathname: string) => boolean }> = [
  { id: "projects", label: "Projects", to: "/", active: (p) => p === "/" },
  // There is no cross-project flows page in the design (§4.1): the index lists every
  // project's flows, and the Flows tab is the one lit while a flow is on screen.
  { id: "flows", label: "Flows", to: "/", active: (p) => /^\/p\/[^/]+\/f\//.test(p) },
  { id: "inbox", label: "Inbox", to: "/inbox", active: (p) => p.startsWith("/inbox") },
  { id: "admin", label: "Administration", to: "/admin", active: (p) => p.startsWith("/admin") },
];

function useRevision(): { text: string; title: string } {
  const [revision, setRevision] = useState<string | null>(null);
  const [dirty, setDirty] = useState<boolean | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    // The header shows the API's code identity: one GET, rendered verbatim (§4.2 rule 5).
    api
      .meta()
      .then((meta) => {
        if (!alive) return;
        setRevision(meta.code?.revision ?? null);
        setDirty(meta.code?.dirty ?? null);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);
  if (failed) return { text: "rev unreachable", title: "the API is unreachable" };
  if (revision !== null) {
    return {
      text: `rev ${revision.slice(0, 12)}${dirty === true ? " (dirty)" : ""}`,
      title: "This view derives from the ledgers and writes nothing",
    };
  }
  return { text: "…", title: "code revision not loaded yet" };
}

export default function Shell() {
  const { pathname } = useLocation();
  const rev = useRevision();
  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="flex min-h-[60px] flex-wrap items-center gap-7 border-b border-gray-200 bg-white px-8">
        <span className="text-base font-bold">Claimstone</span>
        <nav className="flex flex-wrap gap-5 self-stretch" aria-label="Primary">
          {TABS.map((tab) => {
            const active = tab.active(pathname);
            return (
              <Link
                key={tab.id}
                to={tab.to}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center border-b-2",
                  active
                    ? "border-blue-600 font-medium text-blue-600"
                    : "border-transparent text-gray-500",
                )}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>
        <span
          className="ml-auto font-mono text-xs text-gray-500"
          title={rev.title}
        >
          read-only · {rev.text}
        </span>
        <ThemeToggle />
      </header>
      <main className="mx-auto flex max-w-[1360px] flex-col gap-6 px-8 pb-12 pt-7">
        <Outlet />
      </main>
    </div>
  );
}
