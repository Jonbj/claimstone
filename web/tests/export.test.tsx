// F6: Export. The list is the read API's; Create and Verify are the control API's; nothing is
// verified on load; both buttons are disabled while a request runs; a failed list is named.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { SessionProvider } from "@/lib/session";
import ExportPage from "@/pages/ExportPage";

const ID = "a".repeat(64);
function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

interface Opts { signedIn?: boolean; exports?: unknown[] | "fail"; post?: (url: string, body: unknown) => Promise<Response> }
const calls: Array<{ url: string; method: string; body?: string }> = [];

function mount(o: Opts = {}) {
  calls.length = 0;
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? "GET", body: init?.body as string | undefined });
    if (url.startsWith("/control/v1/session") && !url.includes("end")) {
      return o.signedIn === false
        ? json(401, { error: { code: "UNAUTHORIZED", message: "no" } })
        : json(200, { operator: { id: "o1", name: "Ada" }, csrf_token: "t" });
    }
    if (url.startsWith("/api/v1/projects/p/flows/f1/exports")) {
      if (o.exports === "fail") return json(404, { error: { code: "NOT_FOUND", message: "no such flow" }, api_version: 1 });
      return json(200, { api_version: 1, project: "p", flow_id: "f1", exports: o.exports ?? [] });
    }
    if (init?.method === "POST" && o.post) return o.post(url, init.body);
    return json(404, { error: { code: "NOT_FOUND", message: "x" } });
  });
  render(
    <MemoryRouter initialEntries={["/p/p/f/f1/export"]}>
      <SessionProvider>
        <Routes><Route path="/p/:project/f/:sel/export" element={<ExportPage />} /></Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

describe("F6: Export", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("names a failed list", async () => {
    mount({ exports: "fail" });
    expect(await screen.findByText("NOT_FOUND")).toBeTruthy();
    expect(screen.getByText("no such flow")).toBeTruthy();
  });

  it("says plainly when there is no snapshot", async () => {
    mount({ exports: [] });
    expect(await screen.findByText(/No snapshot has been made/)).toBeTruthy();
  });

  it("never verifies on load", async () => {
    mount({ exports: [{ export_id: ID, created_at: "2026-10-03T18:02:00Z" }] });
    await screen.findByText(ID);
    await screen.findByRole("button", { name: "Verify" });
    expect(calls.filter((c) => c.method === "POST")).toEqual([]);
  });

  it("verifies one row, disabled while running, renders holds and problems", async () => {
    let release!: (r: Response) => void;
    mount({
      exports: [{ export_id: ID, created_at: "t" }],
      post: () => new Promise<Response>((res) => { release = res; }),
    });
    const button = await screen.findByRole("button", { name: "Verify" });
    fireEvent.click(button);
    await waitFor(() => expect((screen.getByRole("button", { name: "Verifying…" }) as HTMLButtonElement).disabled).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "Verifying…" }));
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(1);
    release(new Response(JSON.stringify({ export_id: ID, holds: false, problems: ["PREFIX_CHANGED candidates.jsonl"] }),
                         { status: 200, headers: { "Content-Type": "application/json" } }));
    expect(await screen.findByText("Does not hold.")).toBeTruthy();
    expect(screen.getByText("PREFIX_CHANGED candidates.jsonl")).toBeTruthy();
  });

  it("creates a snapshot with copies and shows included and excluded with reasons", async () => {
    mount({
      post: () => json(201, {
        export_id: ID, created_now: true,
        copies: { included: [{ candidate_key: "k1", licence: "cc-by" }],
                  excluded: [{ candidate_key: "k2", reason: "licence unknown" }] },
      }),
    });
    const box = await screen.findByLabelText("Include copies whose licence allows it");
    fireEvent.click(box);
    fireEvent.click(screen.getByRole("button", { name: "Create snapshot" }));
    expect(await screen.findByText("k2")).toBeTruthy();
    expect(screen.getByText(/licence unknown/)).toBeTruthy();
    const post = calls.find((c) => c.method === "POST")!;
    expect(JSON.parse(post.body!)).toEqual({ include_copies: true });
  });

  it("signed out offers no create or verify", async () => {
    mount({ signedIn: false, exports: [{ export_id: ID, created_at: "t" }] });
    await screen.findByText(ID);
    expect(screen.queryByRole("button", { name: "Create snapshot" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Verify" })).toBeNull();
  });

  it("names a refused creation", async () => {
    mount({ post: () => json(409, { error: { code: "REFUSED", message: "flow is not bound" } }) });
    fireEvent.click(await screen.findByRole("button", { name: "Create snapshot" }));
    expect(await screen.findByText("REFUSED")).toBeTruthy();
  });
});
