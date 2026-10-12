// The scheduler's own refresh: a visible-tab interval, and a reload that never starts while the same
// read is in flight and, for the expensive dossier, not more than once per minimum gap.
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DOSSIER_MIN_MS, REFRESH_MS, useIdleReload, useNow, useVisibleInterval } from "@/hooks/useSchedulerRefresh";

function visibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { value: state, configurable: true });
}

beforeEach(() => { vi.useFakeTimers(); visibility("visible"); });
afterEach(() => { vi.useRealTimers(); visibility("visible"); });

describe("useVisibleInterval", () => {
  it("ticks every 15 s while the tab is visible", () => {
    const fn = vi.fn();
    renderHook(() => useVisibleInterval(fn, REFRESH_MS));
    act(() => { vi.advanceTimersByTime(14_999); });
    expect(fn).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(1); });
    expect(fn).toHaveBeenCalledTimes(1);
    act(() => { vi.advanceTimersByTime(30_000); });
    expect(fn).toHaveBeenCalledTimes(3);
  });
  it("does nothing while the tab is hidden and resumes when visible", () => {
    const fn = vi.fn();
    renderHook(() => useVisibleInterval(fn, REFRESH_MS));
    visibility("hidden");
    act(() => { vi.advanceTimersByTime(60_000); });
    expect(fn).not.toHaveBeenCalled();
    visibility("visible");
    act(() => { vi.advanceTimersByTime(15_000); });
    expect(fn).toHaveBeenCalledTimes(1);
  });
  it("stops on unmount", () => {
    const fn = vi.fn();
    const { unmount } = renderHook(() => useVisibleInterval(fn, REFRESH_MS));
    unmount();
    act(() => { vi.advanceTimersByTime(60_000); });
    expect(fn).not.toHaveBeenCalled();
  });
});

describe("useIdleReload", () => {
  it("does not reload while the same read is in flight", () => {
    const reload = vi.fn();
    const { result, rerender } = renderHook(({ busy }) => useIdleReload(reload, busy), { initialProps: { busy: true } });
    result.current();
    expect(reload).not.toHaveBeenCalled();
    rerender({ busy: false });
    result.current();
    expect(reload).toHaveBeenCalledTimes(1);
  });
  it("throttles: at most one reload per minimum gap, the initial read counting as one", () => {
    const reload = vi.fn();
    const { result } = renderHook(() => useIdleReload(reload, false, DOSSIER_MIN_MS));
    act(() => { vi.advanceTimersByTime(15_000); });
    result.current();
    act(() => { vi.advanceTimersByTime(15_000); });
    result.current();
    expect(reload).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(15_000); });
    result.current();
    expect(reload).toHaveBeenCalledTimes(1);
    act(() => { vi.advanceTimersByTime(44_000); });
    result.current();
    expect(reload).toHaveBeenCalledTimes(1);
    act(() => { vi.advanceTimersByTime(1_000); });
    result.current();
    expect(reload).toHaveBeenCalledTimes(2);
  });
});

describe("useNow", () => {
  it("moves on every interval", () => {
    const { result } = renderHook(() => useNow(30_000));
    const first = result.current;
    act(() => { vi.advanceTimersByTime(30_000); });
    expect(result.current - first).toBeGreaterThanOrEqual(30_000);
  });
});
