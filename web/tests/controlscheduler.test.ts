import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { control, ControlError, setCsrfToken, setUnauthorizedHandler } from "@/lib/control";

let urls: string[];
let reply: () => Response;
beforeEach(() => {
  setCsrfToken("tok");
  urls = [];
  reply = () => new Response(JSON.stringify({ ok: true }),
    { status: 200, headers: { "Content-Type": "application/json" } });
  vi.stubGlobal("fetch", (url: string) => { urls.push(url); return Promise.resolve(reply()); });
});
afterEach(() => { vi.unstubAllGlobals(); setCsrfToken(null); setUnauthorizedHandler(null); });

describe("scheduler reads", () => {
  it("builds the index url with a limit and a cursor only when given", async () => {
    await control.schedulerIndex("news");
    await control.schedulerIndex("news", null, 10);
    await control.schedulerIndex("news", "abc=");
    expect(urls).toEqual([
      "/control/v1/p/news/scheduler?limit=25",
      "/control/v1/p/news/scheduler?limit=10",
      "/control/v1/p/news/scheduler?limit=25&cursor=abc%3D",
    ]);
  });
  it("reads one schedule, copy policy and local mandate", async () => {
    await control.schedule("news", "s1");
    await control.copyPolicy("news", "p1");
    await control.localMandate("news", "m1");
    expect(urls).toEqual([
      "/control/v1/p/news/schedules/s1",
      "/control/v1/p/news/copy-policies/p1",
      "/control/v1/p/news/local-mandates/m1",
    ]);
  });
  it("percent-encodes the project", async () => {
    await control.schedule("a b", "s1");
    expect(urls[0]).toBe("/control/v1/p/a%20b/schedules/s1");
  });
  it("reads the periodic dossier through the read API", async () => {
    await api.periodicDossier("news", "s1");
    expect(urls[0]).toBe("/api/v1/projects/news/periodic-dossiers/s1");
  });
  it("a 409 ARCHIVE_CHANGED rejects with the ControlError and does not sign out", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    reply = () => new Response(JSON.stringify({ error: { code: "ARCHIVE_CHANGED", message: "restart paging" } }),
      { status: 409, headers: { "Content-Type": "application/json" } });
    const error = await control.schedulerIndex("news", "c").catch((e) => e);
    expect(error).toBeInstanceOf(ControlError);
    expect(error).toMatchObject({ status: 409, code: "ARCHIVE_CHANGED" });
    expect(handler).not.toHaveBeenCalled();
  });
});
