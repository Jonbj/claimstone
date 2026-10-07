// F1: the control client. Every POST carries the CSRF token, same-origin credentials and an
// Idempotency-Key — except login (no token yet, no key), logout (no key) and the file upload.
// An envelope becomes a ControlError; a reply that is not the envelope is a plain Error; a 401
// tells the session provider; the token is never written to storage.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ControlError, control, setCsrfToken, setUnauthorizedHandler, uploadIntakeFile,
} from "@/lib/control";

type Call = { url: string; init: RequestInit };
let calls: Call[] = [];

function reply(status: number, body: unknown) {
  return () =>
    Promise.resolve(new Response(JSON.stringify(body), {
      status, headers: { "Content-Type": "application/json" },
    }));
}

function mockFetch(responder: (call: Call) => Promise<Response>) {
  calls = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    const call = { url, init };
    calls.push(call);
    return responder(call);
  });
}

const headersOf = (call: Call) => call.init.headers as Record<string, string>;

describe("F1: control client transport", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => {
    vi.unstubAllGlobals();
    setUnauthorizedHandler(null);
  });

  it("login sends no CSRF token and no Idempotency-Key, and keeps the token in memory", async () => {
    mockFetch(reply(200, { operator: { id: "o", name: "O" }, csrf_token: "tok" }));
    const info = await control.signIn("o", "pw");
    expect(info.csrf_token).toBe("tok");
    const headers = headersOf(calls[0]);
    expect(calls[0].url).toBe("/control/v1/session");
    expect(calls[0].init.credentials).toBe("same-origin");
    expect(headers["Content-Type"]).toBe("application/json");
    expect(headers["X-CSRF-Token"]).toBeUndefined();
    expect(headers["Idempotency-Key"]).toBeUndefined();
    expect(JSON.stringify({ ...localStorage })).not.toContain("tok");
    expect(JSON.stringify({ ...sessionStorage })).not.toContain("tok");
  });

  it("a write carries CSRF, same-origin credentials, JSON and a fresh Idempotency-Key", async () => {
    mockFetch(reply(201, { seen: {} }));
    setCsrfToken("tok");
    await control.seen({ project: "p" });
    await control.seen({ project: "p" });
    for (const call of calls) {
      const headers = headersOf(call);
      expect(call.init.method).toBe("POST");
      expect(call.init.credentials).toBe("same-origin");
      expect(headers["X-CSRF-Token"]).toBe("tok");
      expect(headers["Content-Type"]).toBe("application/json");
      expect(headers["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
    }
    expect(headersOf(calls[0])["Idempotency-Key"]).not.toBe(headersOf(calls[1])["Idempotency-Key"]);
  });

  it("logout has the CSRF token but no Idempotency-Key, and forgets the token", async () => {
    mockFetch(reply(200, { ended: true }));
    setCsrfToken("tok");
    await control.signOut();
    expect(headersOf(calls[0])["X-CSRF-Token"]).toBe("tok");
    expect(headersOf(calls[0])["Idempotency-Key"]).toBeUndefined();
    expect(calls[0].url).toBe("/control/v1/session/end");
    mockFetch(reply(200, { seen: {} }));
    await expect(control.seen({})).rejects.toBeInstanceOf(ControlError);
    expect(calls).toEqual([]); // no token, so nothing was sent
  });

  it("maps an envelope to ControlError(status, code, message)", async () => {
    mockFetch(reply(409, { error: { code: "STALE_PROFILE", message: "the profile moved" } }));
    setCsrfToken("tok");
    const failure = await control
      .adjudicate("p", "f", "Q1", {
        verdict: "SUPPORTED", rationale: "x", profile_sha256: "a".repeat(64), attest: true,
      })
      .catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ControlError);
    const error = failure as ControlError;
    expect([error.status, error.code, error.message]).toEqual(
      [409, "STALE_PROFILE", "the profile moved"]);
  });

  it("a reply that is not the envelope is a plain Error", async () => {
    mockFetch(() => Promise.resolve(new Response("<html>502</html>", { status: 502 })));
    const failure = await control.today().catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(Error);
    expect(failure).not.toBeInstanceOf(ControlError);
    expect((failure as Error).message).toContain("HTTP 502");
  });

  it("a 401 tells the session provider and drops the token", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch(reply(401, { error: { code: "UNAUTHORIZED", message: "sign in" } }));
    setCsrfToken("tok");
    await expect(control.today()).rejects.toBeInstanceOf(ControlError);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("a wrong password is a 401 that does not sign anyone out", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch(reply(401, { error: { code: "UNAUTHORIZED", message: "no" } }));
    await expect(control.signIn("o", "bad")).rejects.toMatchObject({ code: "UNAUTHORIZED" });
    expect(handler).not.toHaveBeenCalled();
  });

  it("the upload sends application/pdf and the CSRF token, and refuses over 50 MiB", async () => {
    const sent: { headers: Record<string, string>; url: string; body: unknown } = {
      headers: {}, url: "", body: null,
    };
    class FakeXhr {
      upload: { onprogress: unknown } = { onprogress: null };
      withCredentials = true;
      status = 201;
      responseText = JSON.stringify({ intake: { state: "READY" } });
      onload: () => void = () => {};
      onerror: () => void = () => {};
      open(_method: string, url: string) { sent.url = url; }
      setRequestHeader(name: string, value: string) { sent.headers[name] = value; }
      send(body: unknown) { sent.body = body; queueMicrotask(() => this.onload()); }
    }
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    setCsrfToken("tok");
    const file = new File(["%PDF"], "a.pdf", { type: "application/pdf" });
    await expect(uploadIntakeFile("p", "f", "c1", file)).resolves.toEqual({ intake: { state: "READY" } });
    expect(sent.headers["Content-Type"]).toBe("application/pdf");
    expect(sent.headers["X-CSRF-Token"]).toBe("tok");
    expect(sent.headers["Idempotency-Key"]).toBeUndefined();
    expect(sent.url).toBe("/control/v1/p/p/flows/f/intake/file?target=c1");

    const big = new File(["x"], "big.pdf");
    Object.defineProperty(big, "size", { value: 50 * 1024 * 1024 + 1 });
    await expect(uploadIntakeFile("p", "f", "c1", big)).rejects.toMatchObject({ code: "TOO_LARGE" });
  });
});
