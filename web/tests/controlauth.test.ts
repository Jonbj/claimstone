import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { control, ControlError, setCsrfToken, setUnauthorizedHandler } from "@/lib/control";

let calls: Array<{ url: string; method: string; body: unknown; headers: Record<string, string> }>;
let reply: () => Response;
beforeEach(() => {
  setCsrfToken("tok");
  calls = [];
  reply = () => new Response(JSON.stringify({ ok: true }),
    { status: 200, headers: { "Content-Type": "application/json" } });
  vi.stubGlobal("fetch", (url: string, init: RequestInit = {}) => {
    calls.push({ url, method: init.method ?? "GET", body: init.body ? JSON.parse(String(init.body)) : null,
                 headers: (init.headers ?? {}) as Record<string, string> });
    return Promise.resolve(reply());
  });
});
afterEach(() => { vi.unstubAllGlobals(); setCsrfToken(null); setUnauthorizedHandler(null); });

describe("control auth methods", () => {
  it("reads the account", async () => {
    await control.account();
    expect(calls[0]).toMatchObject({ url: "/control/v1/account", method: "GET" });
  });
  it("changes the password with the current one, with no Idempotency-Key", async () => {
    await control.changePassword("old old old old", "new new new new");
    expect(calls[0]).toMatchObject({ url: "/control/v1/account/password", method: "POST",
      body: { current: "old old old old", new: "new new new new" } });
    expect(calls[0].headers["X-CSRF-Token"]).toBe("tok");
    expect(calls[0].headers["Idempotency-Key"]).toBeUndefined();
  });
  it("lists and ends sessions", async () => {
    await control.accountSessions();
    await control.endOtherSessions();
    expect(calls.map((c) => c.url)).toEqual(["/control/v1/account/sessions", "/control/v1/account/sessions/end-others"]);
    expect(calls[1].headers["Idempotency-Key"]).toBeUndefined();
  });
  it("manages people, always carrying the acting password and no Idempotency-Key", async () => {
    await control.people();
    await control.createPerson({ password: "me", id: "bob", name: "Bob", email: "b@x.org", role: "operator", temporary_password: "tmp tmp tmp tmp" });
    await control.personAct("bob", "disable", { password: "me" });
    await control.personAct("bob", "password", { password: "me", new_password: "tmp tmp tmp tmp" });
    expect(calls.map((c) => c.url)).toEqual(["/control/v1/people", "/control/v1/people", "/control/v1/people/bob/disable", "/control/v1/people/bob/password"]);
    for (const call of calls.slice(1)) expect(call.headers["Idempotency-Key"]).toBeUndefined();
  });
  it("percent-encodes the person id", async () => {
    await control.personAct("a/b c", "enable", { password: "me" });
    expect(calls[0].url).toBe("/control/v1/people/a%2Fb%20c/enable");
  });
  it.each(["REAUTH", "PASSWORD_CHANGE_REQUIRED"])("a 403 %s is an error, not a sign-out", async (code) => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    reply = () => new Response(JSON.stringify({ error: { code, message: "no" } }),
      { status: 403, headers: { "Content-Type": "application/json" } });
    await expect(control.account()).rejects.toBeInstanceOf(ControlError);
    expect(handler).not.toHaveBeenCalled();
    // the token survives: a later write still carries it
    await expect(control.endOtherSessions()).rejects.toBeInstanceOf(ControlError);
    expect(calls[1].headers["X-CSRF-Token"]).toBe("tok");
  });
  it("a 401 is a sign-out", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    reply = () => new Response(JSON.stringify({ error: { code: "UNAUTHORIZED", message: "no session" } }),
      { status: 401, headers: { "Content-Type": "application/json" } });
    await expect(control.account()).rejects.toBeInstanceOf(ControlError);
    expect(handler).toHaveBeenCalledOnce();
  });
});
