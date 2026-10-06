// F5: `ErrorState` renders each §3.3 code with its message; LEDGER_CORRUPT is never
// an empty table. The samples are the API's fixed texts where §3.3 fixes them
// (MISDIRECTED, CROSS_ORIGIN) and representative texts otherwise, because the
// server-side texts are data the frontend renders verbatim.
import { render, screen } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";
import { ApiError } from "$lib/api";
import ErrorState from "$lib/components/ErrorState.svelte";

const SAMPLES: Array<[string, string]> = [
  ["BAD_REQUEST", "limit must be an integer: 'x'"],
  ["NOT_FOUND", "no such api route"],
  ["CONFIG_ERROR", "questions.yaml: 3 errors"],
  ["REGISTRY_DRIFT", "registry v2 differs from the frozen digest"],
  ["LEDGER_CORRUPT", "ledger rejections.jsonl line 4: damaged row"],
  ["MISDIRECTED", "the Host header does not name this server"],
  ["CROSS_ORIGIN", "the Origin header does not name this server"],
  ["INTERNAL", "KeyError"],
];

describe("F5: ErrorState renders every §3.3 code", () => {
  it.each(SAMPLES)("renders %s with its message", (code, message) => {
    const error = new ApiError(code as never, message);
    render(ErrorState, { error });
    expect(screen.getByText(code)).toBeTruthy();
    expect(screen.getByText(message)).toBeTruthy();
  });

  it("gives LEDGER_CORRUPT a named, non-empty state — never an empty table", () => {
    const error = new ApiError("LEDGER_CORRUPT", "ledger claims.jsonl line 12: no newline");
    const { container } = render(ErrorState, { error });
    expect(container.textContent).toContain("LEDGER_CORRUPT");
    expect(container.textContent).toContain("claims.jsonl line 12");
    expect(container.querySelector("[role='alert']")?.textContent?.trim().length ?? 0)
      .toBeGreaterThan(0);
  });

  it("renders a non-API error as UNREACHABLE, still a named state", () => {
    render(ErrorState, { error: new Error("fetch failed") });
    expect(screen.getByText("UNREACHABLE")).toBeTruthy();
    expect(screen.getByText("fetch failed")).toBeTruthy();
  });
});