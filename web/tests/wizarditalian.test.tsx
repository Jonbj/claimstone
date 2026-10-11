// The wizard in Italian: labels from the catalog, an engine error code as an Italian sentence, the
// engine's own message kept as written beneath it.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StepTopic from "@/components/wizard/StepTopic";
import { setCsrfToken } from "@/lib/control";
import type { DraftState } from "@/lib/control";
import { LocaleProvider, STORAGE_KEY } from "@/lib/i18n";

const draft: DraftState = {
  draft_id: "d1", revision: 3, status: "open", steps: {}, advanced: {}, figures: {}, project: null,
  last_failure: null, started_at: "t", updated_at: "t",
};

beforeEach(() => {
  setCsrfToken("tok");
  localStorage.setItem(STORAGE_KEY, "it");
  vi.stubGlobal("fetch", () => Promise.resolve(new Response(
    JSON.stringify({ error: { code: "DRAFT_CLOSED", message: "draft d1 is discarded" } }),
    { status: 409, headers: { "Content-Type": "application/json" } })));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  setCsrfToken(null);
});

describe("the wizard in Italian", () => {
  it("shows step 1 in Italian and an error code as an Italian sentence over the engine's message", async () => {
    render(<MemoryRouter><LocaleProvider><StepTopic draftId="d1" draft={draft} onSaved={vi.fn()} /></LocaleProvider></MemoryRouter>);
    expect(screen.getByLabelText("Nome del progetto")).toBeTruthy();
    expect(screen.getByRole("group", { name: "Argomento 1" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Salva e continua" }));
    await waitFor(() => expect(screen.getByText(/Questa bozza è chiusa/)).toBeTruthy());
    expect(screen.getByText("draft d1 is discarded")).toBeTruthy();
  });
});
