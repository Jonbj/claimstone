import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StepSources from "@/components/wizard/StepSources";
import { setCsrfToken } from "@/lib/control";
import type { DraftState } from "@/lib/control";
import { LocaleProvider } from "@/lib/i18n";

const template = {
  id: "general", label: "General", default_floor: 0.8,
  classes: [
    { id: "ACA", name: "peer-reviewed academic", weight_hint: "highest", notes: "version of record" },
    { id: "WP", name: "working paper", weight_hint: "high", notes: "not refereed" },
  ],
  excluded_hosts: ["sci-hub.se", "libgen.is"],
  notation_presets: [{ id: "none", label: "No special notation" }, { id: "health", label: "Health" }],
};
const draft: DraftState = {
  draft_id: "d1", revision: 4, status: "open", steps: {}, advanced: {}, figures: {}, project: null,
  last_failure: null, started_at: "t", updated_at: "t",
};

let calls: Array<{ url: string; body: unknown }>;
beforeEach(() => {
  setCsrfToken("tok");
  calls = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
    const body = url.includes("/new-templates/") ? template : { revision: 5, data: {}, figures: { classes: ["ACA"] } };
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setCsrfToken(null);
});

const mount = (onSaved = vi.fn()) => {
  render(<LocaleProvider><StepSources draftId="d1" draft={draft} onSaved={onSaved} /></LocaleProvider>);
  return onSaved;
};

describe("StepSources", () => {
  it("lists the template's classes with their ids, ticks none, and shows the fixed hosts", async () => {
    mount();
    expect(await screen.findByLabelText(/ACA/)).toBeTruthy();
    expect((screen.getByLabelText(/ACA/) as HTMLInputElement).checked).toBe(false);
    expect(screen.getByText(/Always excluded: sci-hub.se, libgen.is/)).toBeTruthy();
    expect((screen.getByLabelText(/^Acquisition floor/) as HTMLInputElement).value).toBe("0.80");
    expect((screen.getByLabelText(/Count toward the floor/) as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText(/Read them, but report them separately/) as HTMLInputElement).checked).toBe(false);
  });

  it("sends the declarations exactly as chosen", async () => {
    const onSaved = mount();
    fireEvent.click(await screen.findByLabelText(/ACA/));
    fireEvent.change(screen.getByLabelText(/^Acquisition floor/), { target: { value: "0.9" } });
    fireEvent.change(screen.getByLabelText(/Why this floor/), { target: { value: "Set before the first measured round." } });
    fireEvent.click(screen.getByLabelText(/Read them, but report them separately/));
    fireEvent.change(screen.getByLabelText(/Hosts never to contact/), { target: { value: "example.org\n\n" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const post = calls.find((c) => c.url.endsWith("/steps/3"))!;
    expect(post.body).toEqual({ base_revision: 4, data: {
      template: "general", classes: ["ACA"], acquisition_floor: 0.9,
      floor_rationale: "Set before the first measured round.", supplied_copies: "separate",
      notation: "none", custom_value_labels: [], extra_excluded_hosts: ["example.org"] } });
  });

  it("a custom notation sends its own list", async () => {
    mount();
    await screen.findByLabelText(/ACA/);
    fireEvent.change(screen.getByLabelText(/How this field writes/), { target: { value: "custom" } });
    fireEvent.change(await screen.findByLabelText(/Notation, one per line/), { target: { value: "Sharpe\nalpha" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/steps/3"))).toBe(true));
    const data = (calls.find((c) => c.url.endsWith("/steps/3"))!.body as { data: Record<string, unknown> }).data;
    expect(data.notation).toBe("custom");
    expect(data.custom_value_labels).toEqual(["Sharpe", "alpha"]);
  });

  it("accepts an Italian decimal comma in the floor", async () => {
    const onSaved = mount();
    fireEvent.click(await screen.findByLabelText(/ACA/));
    fireEvent.change(screen.getByLabelText(/^Acquisition floor/), { target: { value: "0,9" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const data = (calls.find((c) => c.url.endsWith("/steps/3"))!.body as { data: Record<string, unknown> }).data;
    expect(data.acquisition_floor).toBe(0.9);
  });
});
