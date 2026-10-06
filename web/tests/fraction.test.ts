// F4: `Fraction` with `null` renders "—", never "0"; `Pending` shows its label.
import { render, screen } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";
import Fraction from "$lib/components/Fraction.svelte";
import Pending from "$lib/components/Pending.svelte";

describe("F4: Fraction and Pending", () => {
  it("renders a number as itself", () => {
    render(Fraction, { numerator: 3, denominator: 7 });
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("3").textContent).not.toContain("0");
  });

  it("renders null as — with the not-knowable title, never 0", () => {
    const { container } = render(Fraction, { numerator: null });
    const el = container.querySelector(".fraction");
    expect(el?.textContent).toBe("—");
    expect(el?.textContent).not.toContain("0");
    expect(el?.getAttribute("title")).toBe("not knowable");
  });

  it("renders Pending with the computing… label", () => {
    render(Pending);
    expect(screen.getByText("computing…")).toBeTruthy();
  });

  it("renders Pending with a custom label", () => {
    render(Pending, { label: "fetching summary…" });
    expect(screen.getByText("fetching summary…")).toBeTruthy();
  });
});