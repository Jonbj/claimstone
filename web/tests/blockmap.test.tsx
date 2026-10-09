// The strip of six tiles: server order and words as received, the selection in the URL, and the
// default rule (the first block that waits for you or is blocked, otherwise Pipeline).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import BlockMap, { BLOCK_KEYS, defaultBlock } from "@/components/BlockMap";
import type { BlockKey, JourneyBlock } from "@/components/BlockMap";

function tile(key: BlockKey, status: JourneyBlock["status"], figure = "fig " + key): JourneyBlock {
  const titles: Record<BlockKey, string> = {
    protocol: "Protocol", pipeline: "Pipeline", selection: "Source selection",
    intake: "Manual intake", execution: "Execution", reading: "Human reading",
  };
  return { key, title: titles[key], status, figure };
}

const calm: JourneyBlock[] = [
  tile("protocol", "done"), tile("pipeline", "partial"), tile("selection", "advisory"),
  tile("intake", "idle"), tile("execution", "idle"), tile("reading", "not_started"),
];

const panels = Object.fromEntries(
  BLOCK_KEYS.map((key) => [key, <p key={key}>panel {key}</p>]),
) as Record<BlockKey, ReactNode>;

function Probe() {
  const location = useLocation();
  return <output data-testid="loc">{location.search}</output>;
}

function mount(blocks: JourneyBlock[], at = "/p/demo/f/x") {
  render(
    <MemoryRouter initialEntries={[at]}>
      <BlockMap blocks={blocks} panels={panels} />
      <Probe />
    </MemoryRouter>,
  );
}

describe("defaultBlock", () => {
  it("is Pipeline when nothing waits for you or is blocked", () => {
    expect(defaultBlock(calm)).toBe("pipeline");
  });

  it("is the first block, in strip order, that waits for you or is blocked", () => {
    const blocks = calm.map((b) => b.key === "reading" ? { ...b, status: "waits_for_you" as const }
      : b.key === "selection" ? { ...b, status: "blocked" as const } : b);
    expect(defaultBlock(blocks)).toBe("selection");
  });
});

describe("BlockMap", () => {
  afterEach(cleanup);

  it("renders the six tiles in server order with the server's status word and figure", () => {
    mount(calm);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.getAttribute("data-block"))).toEqual([...BLOCK_KEYS]);
    expect(tabs[0].textContent).toContain("Protocol");
    expect(tabs[0].textContent).toContain("done");
    expect(tabs[0].textContent).toContain("fig protocol");
    expect(tabs[2].textContent).toContain("advisory");
    expect(tabs[1].getAttribute("data-status")).toBe("partial");
  });

  it("opens on Pipeline by default and shows exactly one panel", () => {
    mount(calm);
    expect(screen.getByRole("tab", { name: /^Pipeline/ }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
    expect(screen.getByRole("tabpanel").textContent).toBe("panel pipeline");
  });

  it("opens on the block that waits for you", () => {
    mount(calm.map((b) => b.key === "reading" ? { ...b, status: "waits_for_you" as const } : b));
    expect(screen.getByRole("tabpanel").textContent).toBe("panel reading");
    expect(screen.getByRole("tab", { name: /^Human reading/ }).textContent).toContain("waits for you");
  });

  it("reads the block from the URL", () => {
    mount(calm, "/p/demo/f/x?block=selection");
    expect(screen.getByRole("tabpanel").textContent).toBe("panel selection");
  });

  it("falls back to the default for an unknown block", () => {
    mount(calm, "/p/demo/f/x?block=nonsense");
    expect(screen.getByRole("tabpanel").textContent).toBe("panel pipeline");
  });

  it("clicking a tile switches the panel and writes the URL, keeping other parameters", () => {
    mount(calm, "/p/demo/f/x?details=1");
    fireEvent.click(screen.getByRole("tab", { name: /^Manual intake/ }));
    expect(screen.getByRole("tabpanel").textContent).toBe("panel intake");
    expect(screen.getByTestId("loc").textContent).toBe("?details=1&block=intake");
  });

  it("keeps every panel in the document, hidden, so the page's content is not lost", () => {
    mount(calm);
    expect(document.querySelectorAll("[data-panel]")).toHaveLength(6);
  });

  it("inactive panels are hidden and the open one is not", () => {
    mount(calm);
    const panelsEls = Array.from(document.querySelectorAll<HTMLElement>("[data-panel]"));
    for (const el of panelsEls) {
      expect(el.hasAttribute("hidden")).toBe(el.getAttribute("data-panel") !== "pipeline");
    }
  });

  it("each tab controls a panel that is labelled by it", () => {
    mount(calm);
    for (const tab of screen.getAllByRole("tab")) {
      const panel = document.getElementById(tab.getAttribute("aria-controls") ?? "");
      expect(panel).not.toBeNull();
      expect(panel!.getAttribute("aria-labelledby")).toBe(tab.id);
    }
  });

  it("uses a roving tabindex", () => {
    mount(calm);
    const idx = screen.getAllByRole("tab").map((t) => t.getAttribute("tabindex"));
    expect(idx).toEqual(["-1", "0", "-1", "-1", "-1", "-1"]);
  });

  it("arrow keys, Home and End move selection, focus and the URL", () => {
    mount(calm);
    const tab = (name: RegExp) => screen.getByRole("tab", { name });
    fireEvent.keyDown(tab(/^Pipeline/), { key: "ArrowRight" });
    expect(screen.getByRole("tabpanel").textContent).toBe("panel selection");
    expect(screen.getByTestId("loc").textContent).toBe("?block=selection");
    expect(document.activeElement).toBe(tab(/^Source selection/));
    fireEvent.keyDown(tab(/^Source selection/), { key: "Home" });
    expect(screen.getByRole("tabpanel").textContent).toBe("panel protocol");
    fireEvent.keyDown(tab(/^Protocol/), { key: "ArrowLeft" });
    expect(screen.getByRole("tabpanel").textContent).toBe("panel reading");
    expect(document.activeElement).toBe(tab(/^Human reading/));
    fireEvent.keyDown(tab(/^Human reading/), { key: "ArrowRight" });
    expect(screen.getByRole("tabpanel").textContent).toBe("panel protocol");
    fireEvent.keyDown(tab(/^Protocol/), { key: "End" });
    expect(screen.getByRole("tabpanel").textContent).toBe("panel reading");
  });

  it("an unknown status renders its words without throwing", () => {
    mount(calm.map((b) => b.key === "intake" ? { ...b, status: "brand_new" as never } : b));
    expect(screen.getByRole("tab", { name: /^Manual intake/ }).textContent).toContain("brand new");
  });

  it("only the selected tile shows the cue", () => {
    mount(calm);
    const cued = screen.getAllByRole("tab").filter((t) => t.textContent?.includes("▾"));
    expect(cued).toHaveLength(1);
    expect(cued[0].getAttribute("data-block")).toBe("pipeline");
  });

  it("the advisory mark is not the partial mark", () => {
    mount(calm);
    const mark = (key: string) =>
      document.querySelector(`[data-block="${key}"] [aria-hidden="true"].rounded-full`)?.className;
    expect(mark("selection")).toBeTruthy();
    expect(mark("selection")).not.toBe(mark("pipeline"));
  });
});
