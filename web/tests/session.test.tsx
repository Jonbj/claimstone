// F1: the session provider. It reads the session at start, a 401 from any control route signs
// it out, and signIn/signOut move the operator.
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { control, setCsrfToken } from "@/lib/control";
import { SessionProvider, useSession } from "@/lib/session";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

function Probe() {
  const s = useSession();
  return (
    <div>
      <span data-testid="who">{!s.ready ? "loading" : s.operator ? s.operator.name : "signed-out"}</span>
      <button type="button" onClick={() => void s.signOut()}>out</button>
    </div>
  );
}

const SIGNED_IN = { operator: { id: "o1", name: "Ada", role: "admin", must_change_password: false }, csrf_token: "tok" };

describe("F1: SessionProvider", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("reads the session at start", async () => {
    vi.stubGlobal("fetch", () => json(200, SIGNED_IN));
    render(<SessionProvider><Probe /></SessionProvider>);
    expect(screen.getByTestId("who").textContent).toBe("loading");
    await waitFor(() => expect(screen.getByTestId("who").textContent).toBe("Ada"));
  });

  it("starts signed out on a 401", async () => {
    vi.stubGlobal("fetch", () => json(401, { error: { code: "UNAUTHORIZED", message: "no" } }));
    render(<SessionProvider><Probe /></SessionProvider>);
    await waitFor(() => expect(screen.getByTestId("who").textContent).toBe("signed-out"));
  });

  it("a 401 from any control route signs the session out", async () => {
    let first = true;
    vi.stubGlobal("fetch", () => {
      if (first) {
        first = false;
        return json(200, SIGNED_IN);
      }
      return json(401, { error: { code: "UNAUTHORIZED", message: "expired" } });
    });
    render(<SessionProvider><Probe /></SessionProvider>);
    await waitFor(() => expect(screen.getByTestId("who").textContent).toBe("Ada"));
    await act(async () => {
      await control.today().catch(() => undefined);
    });
    expect(screen.getByTestId("who").textContent).toBe("signed-out");
  });

  it("signing out clears the operator even though the server answers", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", () => (++calls === 1 ? json(200, SIGNED_IN) : json(200, { ended: true })));
    render(<SessionProvider><Probe /></SessionProvider>);
    await waitFor(() => expect(screen.getByTestId("who").textContent).toBe("Ada"));
    await act(async () => {
      screen.getByText("out").click();
    });
    await waitFor(() => expect(screen.getByTestId("who").textContent).toBe("signed-out"));
  });

  it("recheck restores the operator when the server knows the session, and never throws on 401", async () => {
    let signedIn = false;
    vi.stubGlobal("fetch", () =>
      signedIn ? json(200, SIGNED_IN) : json(401, { error: { code: "UNAUTHORIZED", message: "no" } }));
    function Again() {
      const s = useSession();
      return <button type="button" onClick={() => void s.recheck()}>again</button>;
    }
    render(<SessionProvider><Probe /><Again /></SessionProvider>);
    await waitFor(() => expect(screen.getByTestId("who").textContent).toBe("signed-out"));
    await act(async () => { screen.getByText("again").click(); });
    expect(screen.getByTestId("who").textContent).toBe("signed-out");
    signedIn = true;
    await act(async () => { screen.getByText("again").click(); });
    await waitFor(() => expect(screen.getByTestId("who").textContent).toBe("Ada"));
  });
});
