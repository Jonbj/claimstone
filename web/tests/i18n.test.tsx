// i18n: the catalogs agree, a missing key shows itself, the choice survives blocked storage.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LocaleSwitch from "@/components/LocaleSwitch";
import {
  CATALOGS, LocaleProvider, STORAGE_KEY, flatten, initialLocale, translate, useLocale,
} from "@/lib/i18n";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("catalogs", () => {
  it("have exactly the same keys in both locales", () => {
    expect(Object.keys(CATALOGS.it).sort()).toEqual(Object.keys(CATALOGS.en).sort());
  });

  it("use the same placeholders in both locales", () => {
    for (const key of Object.keys(CATALOGS.en)) {
      expect([key, placeholders(CATALOGS.it[key])]).toEqual([key, placeholders(CATALOGS.en[key])]);
    }
  });

  it("have no empty text", () => {
    for (const locale of ["en", "it"] as const) {
      for (const [key, text] of Object.entries(CATALOGS[locale])) {
        expect([locale, key, text.trim().length > 0]).toEqual([locale, key, true]);
      }
    }
  });
});

describe("translate", () => {
  it("fills placeholders and leaves an unknown one visible", () => {
    expect(translate("en", "shell.language")).toBe("Language");
    expect(flatten({ a: { b: "x" } })).toEqual({ "a.b": "x" });
    expect(translate("en", "no.such.key")).toBe("no.such.key"); // never an invented label
  });
});

describe("initialLocale", () => {
  it("follows the browser, English by default", () => {
    vi.stubGlobal("navigator", { language: "it-IT" });
    expect(initialLocale()).toBe("it");
    vi.stubGlobal("navigator", { language: "fr-FR" });
    expect(initialLocale()).toBe("en");
  });

  it("prefers the remembered choice", () => {
    vi.stubGlobal("navigator", { language: "en-US" });
    localStorage.setItem(STORAGE_KEY, "it");
    expect(initialLocale()).toBe("it");
  });

  it("survives blocked storage", () => {
    vi.stubGlobal("navigator", { language: "it" });
    vi.stubGlobal("localStorage", { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } });
    expect(initialLocale()).toBe("it");
  });
});

function Probe() {
  const { t, locale } = useLocale();
  return <p data-testid="probe">{locale}:{t("shell.language")}</p>;
}

describe("LocaleProvider and LocaleSwitch", () => {
  it("switches the language, the html lang and the remembered choice", () => {
    vi.stubGlobal("navigator", { language: "en-US" });
    render(<LocaleProvider><LocaleSwitch /><Probe /></LocaleProvider>);
    expect(screen.getByTestId("probe").textContent).toBe("en:Language");
    fireEvent.click(screen.getByRole("button", { name: "IT" }));
    expect(screen.getByTestId("probe").textContent).toBe("it:Lingua");
    expect(document.documentElement.lang).toBe("it");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("it");
    expect(screen.getByRole("button", { name: "IT" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("works without a provider, in English", () => {
    render(<Probe />);
    expect(screen.getByTestId("probe").textContent).toBe("en:Language");
  });
});

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

describe("t() is only ever called with a literal key", () => {
  // A variable first argument could carry what a person typed. Literal keys (including template
  // literals with a fixed prefix) cannot.
  const roots = [join(__dirname, "..", "src", "components", "wizard"), join(__dirname, "..", "src", "pages")];
  const files = roots.flatMap((root) =>
    readdirSync(root).filter((f) => /\.tsx?$/.test(f)).map((f) => join(root, f)));

  it("scans the wizard sources", () => {
    expect(files.length).toBeGreaterThan(5);
  });

  it("never passes an identifier as the key", () => {
    const offenders = files.filter((file) =>
      /\bt\(\s*[A-Za-z_]/.test(readFileSync(file, "utf-8")));
    expect(offenders).toEqual([]);
  });
});
