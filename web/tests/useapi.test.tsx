// Review of R2: a poll-triggered reload keeps the view's data on screen (refreshing), while a
// change of view drops it (pending) — the page never flashes empty, and never shows another
// view's numbers.
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useApi } from "@/hooks/useApi";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe("useApi", () => {
  it("keeps data while refreshing the same view", async () => {
    let next = deferred<string>();
    const { result } = renderHook(() => useApi(() => next.promise, ["view-a"]));
    expect(result.current.pending).toBe(true);
    await act(async () => next.resolve("first"));
    await waitFor(() => expect(result.current.data).toBe("first"));

    next = deferred<string>();
    act(() => result.current.reload());
    expect(result.current.data).toBe("first");
    expect(result.current.refreshing).toBe(true);
    expect(result.current.pending).toBe(false);
    await act(async () => next.resolve("second"));
    await waitFor(() => expect(result.current.data).toBe("second"));
    expect(result.current.refreshing).toBe(false);
  });

  it("drops data when the view changes", async () => {
    let next = deferred<string>();
    const { result, rerender } = renderHook(({ view }) => useApi(() => next.promise, [view]), {
      initialProps: { view: "a" },
    });
    await act(async () => next.resolve("a-data"));
    await waitFor(() => expect(result.current.data).toBe("a-data"));
    next = deferred<string>();
    rerender({ view: "b" });
    expect(result.current.data).toBe(null);
    expect(result.current.pending).toBe(true);
  });
});
