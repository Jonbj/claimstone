// F6: `CommandBlock` copies text and has no execute affordance; the adjudicate
// placeholder <ONE_OF_FIVE> survives rendering.
import { cleanup, render, screen } from "@testing-library/svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import CommandBlock from "$lib/components/CommandBlock.svelte";

const COMMAND = "claimstone adjudicate --project demo --question q1 --verdict <ONE_OF_FIVE> --signature <YOUR_NAME>";

describe("F6: CommandBlock", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows the command with the <ONE_OF_FIVE> placeholder intact", () => {
    render(CommandBlock, { command: COMMAND });
    const code = screen.getByText(COMMAND, { exact: false });
    expect(code).toBeTruthy();
    expect(code.textContent).toContain("<ONE_OF_FIVE>");
  });

  it("copies the command to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(globalThis, "navigator", {
      value: { clipboard: { writeText } },
      configurable: true,
      writable: true,
    });
    render(CommandBlock, { command: COMMAND });
    await screen.getByRole("button", { name: "copy command to clipboard" }).click();
    await vi.waitFor(() => expect(writeText).toHaveBeenCalledWith(COMMAND));
  });

  it("has no execute affordance — the only button inside the block copies", () => {
    const { container } = render(CommandBlock, { command: COMMAND });
    const buttons = container.querySelectorAll("button");
    expect(buttons).toHaveLength(1);
    expect(buttons[0].textContent?.trim()).toBe("copy");
  });
});