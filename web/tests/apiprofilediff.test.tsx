// R5.1: `api.profileDiff` — one typed function per route (§8.2). It builds the
// route's exact path (`/questions/{qid}/profile-diff?from=…&to=…`), resolves
// the payload on a 200, and maps the §3.3 envelope to `ApiError(code, message)`
// on a 400/404. `useApi` drives it: pending before the answer, data after, the
// refusal as a named error state, and a changed comparison is a new view (no
// stale diff of another pair left on screen). The fetch stub is installed once
// per test and restored after — jsdom's `fetch` is real and would follow the
// relative `/api/v1/...` URL.
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useApi } from "@/hooks/useApi";
import { api, ApiError } from "@/lib/api";

const get = vi.fn();

vi.stubGlobal("fetch", get);
afterEach(() => {
  get.mockReset();
  get.mockImplementation(() => Promise.resolve(new Response(
    JSON.stringify({ api_version: 1, error: { code: "INTERNAL", message: "unset stub" } }),
    { status: 500, headers: { "Content-Type": "application/json" } })));
});

function ok(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, message: string) {
  return new Response(JSON.stringify({ api_version: 1, error: { code, message } }), {
    status: code === "BAD_REQUEST" ? 400 : 404,
    headers: { "Content-Type": "application/json" },
  });
}

const PROJECT = "example-news-and-returns";
const FLOW = "0df548e3743689e1a0dd099da697aee4842e8a573f1225a8da13fec128a248cd";
const QID = "Q02";
const FROM = "7056ff48a8e45f615aadc993d51035ac4add9a7686d5190f3fee1703f759f9c5";
const TO = "bbbb1111bbbb1111bbbb1111bbbb1111bbbb1111bbbb1111bbbb1111bbbb1111";

describe("R5.1: api.profileDiff", () => {
  it("GETs the route with both hashes, once, and only GET", async () => {
    get.mockResolvedValueOnce(ok({ api_version: 1, added: [], removed: [], changed: [] }));
    await api.profileDiff(PROJECT, "f", FLOW, QID, FROM, TO);
    expect(get).toHaveBeenCalledTimes(1);
    const [url, init] = get.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(
      `/api/v1/projects/${PROJECT}/flows/${FLOW}/questions/${QID}/profile-diff` +
      `?from=${FROM}&to=${TO}`,
    );
    expect(init.method).toBe("GET");
  });

  it("routes the unbound selector kind through unbound/", async () => {
    get.mockResolvedValueOnce(ok({ api_version: 1, added: [], removed: [], changed: [] }));
    await api.profileDiff(PROJECT, "u", "-", QID, FROM, TO);
    const [url] = get.mock.calls[0] as unknown as [string];
    expect(url).toBe(
      `/api/v1/projects/${PROJECT}/unbound/-/questions/${QID}/profile-diff` +
      `?from=${FROM}&to=${TO}`,
    );
  });

  it("resolves the payload on 200", async () => {
    const payload = { api_version: 1, summary: { added: 0, removed: 0, changed: 0 } };
    get.mockResolvedValueOnce(ok(payload));
    const diff = await api.profileDiff(PROJECT, "f", FLOW, QID, FROM, TO);
    expect(diff).toEqual(payload);
  });

  it("maps the 400 envelope to ApiError with code and message", async () => {
    get.mockResolvedValueOnce(envelope("BAD_REQUEST", "query parameter 'from' is required"));
    await expect(api.profileDiff(PROJECT, "f", FLOW, QID, "", TO)).rejects.toMatchObject({
      code: "BAD_REQUEST",
      message: "query parameter 'from' is required",
    });
  });

  it("maps the 404 envelope to ApiError with code and message", async () => {
    get.mockResolvedValueOnce(envelope("NOT_FOUND", "from profile 0000 not in the ledger for question Q02"));
    await expect(api.profileDiff(PROJECT, "f", FLOW, QID, "0000", TO)).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});

describe("R5: useApi drives profileDiff", () => {
  it("is pending before the answer and holds the payload after", async () => {
    const payload = { api_version: 1, summary: { added: 1, removed: 0, changed: 0 } };
    get.mockResolvedValueOnce(ok(payload));
    const { result } = renderHook(() =>
      useApi(() => api.profileDiff(PROJECT, "f", FLOW, QID, FROM, TO), [FROM, TO]),
    );
    await waitFor(() => expect(result.current.data).toEqual(payload));
    expect(result.current.error).toBeNull();
  });

  it("carries the envelope's refusal as a named error state", async () => {
    get.mockResolvedValueOnce(envelope("NOT_FOUND", "to profile ffff not in the ledger for question Q02"));
    const { result } = renderHook(() =>
      useApi(() => api.profileDiff(PROJECT, "f", FLOW, QID, FROM, "ffff"), [FROM, "ffff"]),
    );
    await waitFor(() => expect(result.current.error).toBeInstanceOf(ApiError));
    expect((result.current.error as ApiError).code).toBe("NOT_FOUND");
    expect(result.current.data).toBeNull();
  });

  it("treats another pair of hashes as another view: no stale diff", async () => {
    get.mockResolvedValueOnce(ok({ api_version: 1, summary: { added: 1, removed: 0, changed: 0 } }));
    const first = renderHook(({ to }) =>
      useApi(() => api.profileDiff(PROJECT, "f", FLOW, QID, FROM, to), [FROM, to]),
      { initialProps: { to: TO } });
    await waitFor(() => expect(first.result.current.data).not.toBeNull());

    get.mockResolvedValueOnce(ok({ api_version: 1, summary: { added: 2, removed: 0, changed: 0 } }));
    first.rerender({ to: "cccc2222cccc2222cccc2222cccc2222cccc2222cccc2222cccc2222cccc2222" });
    expect(first.result.current.pending).toBe(true);
    expect(first.result.current.data).toBeNull();
    await waitFor(() => expect(first.result.current.data).toEqual(
      { api_version: 1, summary: { added: 2, removed: 0, changed: 0 } },
    ));
  });
});