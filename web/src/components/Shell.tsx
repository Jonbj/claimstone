import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router";
import ThemeToggle from "@/components/ThemeToggle";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

// v2.1 shell (spec F1): a dark left rail, 232 px wide, with New project (disabled: nothing
// builds projects from the web yet), Today, Projects and Administration, and a footer with the
// signed-in operator and Sign out, or Sign in. Under 900 px the rail becomes a top bar. The
// rail is dark in both themes (`bg-rail`); the content area follows the theme tokens. The old
// Inbox tab is gone from the rail, but `/inbox` is still routable.
const NAV: Array<{ id: string; label: string; to: string; active: (pathname: string) => boolean }> = [
  { id: "today", label: "Today", to: "/", active: (p) => p === "/" },
  // A project or flow on screen lights Projects: Today is the only other top-level page.
  {
    id: "projects",
    label: "Projects",
    to: "/projects",
    active: (p) => p.startsWith("/projects") || p.startsWith("/p/") || p.startsWith("/inbox"),
  },
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
      title: "the code revision the API reports",
    };
  }
  return { text: "…", title: "code revision not loaded yet" };
}

function Operator() {
  const session = useSession();
  const { pathname, search } = useLocation();
  if (!session.ready) {
    return <span className="text-xs text-rail-muted">checking session…</span>;
  }
  if (session.operator) {
    return (
      <div className="flex items-center gap-2 min-[900px]:flex-col min-[900px]:items-start">
        <span className="text-sm font-medium text-rail-foreground" data-testid="operator-name">
          {session.operator.name}
        </span>
        <button
          type="button"
          onClick={() => void session.signOut()}
          className="min-h-11 rounded-lg border border-rail-border px-3 text-sm text-rail-muted hover:text-rail-foreground"
        >
          Sign out
        </button>
      </div>
    );
  }
  // Come back to where the operator was; `safeNext` only accepts a path starting with one `/`.
  const next = pathname === "/login" ? "" : `?next=${encodeURIComponent(pathname + search)}`;
  return (
    <Link
      to={`/login${next}`}
      className="flex min-h-11 items-center rounded-lg border border-rail-border px-3 text-sm text-rail-foreground"
    >
      Sign in
    </Link>
  );
}

export default function Shell() {
  const { pathname } = useLocation();
  const rev = useRevision();
  return (
    <div className="min-h-screen bg-muted/40 text-foreground min-[900px]:flex">
      <nav
        aria-label="Primary"
        className="flex flex-wrap items-center gap-x-4 gap-y-2 bg-rail px-4 py-3 text-rail-muted min-[900px]:sticky min-[900px]:top-0 min-[900px]:h-screen min-[900px]:w-[232px] min-[900px]:shrink-0 min-[900px]:flex-col min-[900px]:flex-nowrap min-[900px]:items-stretch min-[900px]:gap-1 min-[900px]:px-3.5 min-[900px]:py-5"
      >
        <Link to="/" className="font-serif text-2xl text-rail-foreground min-[900px]:mb-3 min-[900px]:px-2.5">
          Claimstone
        </Link>
        <div className="flex flex-col min-[900px]:mb-3">
          <button
            type="button"
            disabled
            aria-describedby="new-project-note"
            title="creating projects from the web is not built yet"
            className="min-h-11 rounded-lg bg-rail-active px-3 text-sm font-semibold text-rail-muted opacity-60"
          >
            + New project
          </button>
          <span id="new-project-note" className="mt-1 hidden text-xs text-rail-muted min-[900px]:block">
            creating projects from the web is not built yet
          </span>
        </div>
        <div className="flex flex-wrap gap-1 min-[900px]:flex-col">
          {NAV.map((item) => {
            const active = item.active(pathname);
            return (
              <Link
                key={item.id}
                to={item.to}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex min-h-11 items-center rounded-lg px-2.5 text-sm",
                  active
                    ? "bg-rail-active font-medium text-rail-foreground"
                    : "text-rail-muted hover:text-rail-foreground",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
        <div className="ml-auto flex items-center gap-3 min-[900px]:mt-auto min-[900px]:ml-0 min-[900px]:flex-col min-[900px]:items-stretch min-[900px]:border-t min-[900px]:border-rail-border min-[900px]:pt-3">
          <Operator />
          <span className="font-mono text-xs text-rail-muted" title={rev.title}>
            {rev.text}
          </span>
          <ThemeToggle />
        </div>
      </nav>
      <main className="mx-auto flex min-w-0 max-w-[1360px] flex-1 flex-col gap-6 px-4 pb-12 pt-7 min-[900px]:px-8">
        <Outlet />
      </main>
    </div>
  );
}
