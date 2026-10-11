import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import ExplainPanel from "@/components/wizard/ExplainPanel";
import WizardShell from "@/components/wizard/WizardShell";
import { LocaleProvider } from "@/lib/i18n";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

function media(wide: boolean) {
  vi.stubGlobal("matchMedia", () => ({ matches: wide, addEventListener() {}, removeEventListener() {} }));
}

describe("ExplainPanel", () => {
  it("wide: the three moments are plain sections, all visible, with the server's figures", () => {
    media(true);
    render(<LocaleProvider><ExplainPanel step={1} figures={{ topics: 2, terms: 5, searches_per_index: 5, searches_all_indexes: 15 }} /></LocaleProvider>);
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(3);
    expect(document.querySelectorAll("details")).toHaveLength(0);
    expect(screen.getByText(/topics: 2, terms: 5, searches per index: 5/)).toBeTruthy();
    expect(screen.getByText(/with all three indexes: 15/)).toBeTruthy();
  });

  it("narrow: the three moments are an accordion, the first one open", () => {
    media(false);
    render(<LocaleProvider><ExplainPanel step={2} figures={{}} /></LocaleProvider>);
    const panels = [...document.querySelectorAll("details")];
    expect(panels).toHaveLength(3);
    expect(panels.map((d) => d.open)).toEqual([true, false, false]);
  });

  it("an unknown figure is a dash, not 0", () => {
    media(true);
    render(<LocaleProvider><ExplainPanel step={2} figures={{}} /></LocaleProvider>);
    expect(screen.getByText(/Questions: — \(literature: —, operational: —\)/)).toBeTruthy();
    expect(screen.queryByText(/Questions: 0/)).toBeNull();
  });

  it("explains step 3 with the INSUFFICIENT_ACQUISITION token untouched", () => {
    media(true);
    render(<LocaleProvider><ExplainPanel step={3} figures={{ acquisition_floor: 0.8 }} /></LocaleProvider>);
    expect(screen.getByText(/INSUFFICIENT_ACQUISITION/)).toBeTruthy();
    expect(screen.getByText(/floor 0\.80/)).toBeTruthy();
  });

  it("quotes the supplied-copies policy as its label, with the canonical token beside it", () => {
    media(true);
    render(<LocaleProvider><ExplainPanel step={3} figures={{ supplied_copies: "separate" }} /></LocaleProvider>);
    expect(screen.getByText(/separate — read, but reported apart from the floor/)).toBeTruthy();
  });
});

describe("WizardShell", () => {
  it("marks the current step and the saved ones, with words as well as marks", () => {
    media(true);
    render(
      <MemoryRouter>
        <LocaleProvider>
          <WizardShell draftId="d1" current={2} saved={[1]} explain={<p>panel</p>}>
            <p>form</p>
          </WizardShell>
        </LocaleProvider>
      </MemoryRouter>,
    );
    const rail = screen.getByRole("navigation", { name: "Steps" });
    const items = within(rail).getAllByRole("link");
    expect(items).toHaveLength(4);
    expect(items[1].getAttribute("aria-current")).toBe("step");
    expect(within(items[0]).getByText("done")).toBeTruthy();
    expect(items[0].getAttribute("href")).toBe("/new/d1/1");
    expect(screen.getByText("form")).toBeTruthy();
    expect(screen.getByText("panel")).toBeTruthy();
  });

  it("keeps the rail from widening the page below 900 px", () => {
    // Seen in a real browser (documentElement.scrollWidth > clientWidth at 420 px): a grid child
    // does not shrink without min-w-0, and the sr-only mark escapes an overflow container unless
    // the container is positioned. jsdom cannot measure layout, so the two classes are pinned.
    media(false);
    render(
      <MemoryRouter>
        <LocaleProvider>
          <WizardShell draftId="d1" current={4} saved={[1, 2, 3]} explain={<p>panel</p>}>
            <p>form</p>
          </WizardShell>
        </LocaleProvider>
      </MemoryRouter>,
    );
    const rail = screen.getByRole("navigation", { name: "Steps" });
    expect(rail.className).toContain("min-w-0");
    expect(rail.querySelector("ol")!.className).toContain("relative");
  });
});
