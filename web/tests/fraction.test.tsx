// F4: `Fraction` with `null` renders "—", never "0"; `Pending` shows its label.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import Fraction from "@/components/Fraction";
import Pending from "@/components/Pending";

describe("F4: Fraction and Pending", () => {
  afterEach(cleanup);

  it("renders a number as itself", () => {
    render(<Fraction numerator={3} denominator={7} />);
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("3").textContent).not.toContain("0");
  });

  it("renders null as — with the not-knowable title, never 0", () => {
    const { container } = render(<Fraction numerator={null} />);
    const el = container.querySelector(".fraction");
    expect(el?.textContent).toBe("—");
    expect(el?.textContent).not.toContain("0");
    expect(el?.getAttribute("title")).toBe("not knowable");
  });

  it("renders Pending with the computing… label", () => {
    render(<Pending />);
    expect(screen.getByText("computing…")).toBeTruthy();
  });

  it("renders Pending with a custom label", () => {
    render(<Pending label="fetching summary…" />);
    expect(screen.getByText("fetching summary…")).toBeTruthy();
  });
});
