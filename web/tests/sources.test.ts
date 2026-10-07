// F10 (§8.5): a source scan of `src/` (comments stripped) finds no
// `dangerouslySetInnerHTML`, no `<style`, no `components/ui/chart`, no non-GET
// `fetch` outside lib/control.ts and no `<form` without an onSubmit. Behind the §8.4 header CSP (`style-src 'self'`,
// `script-src 'self'`, `form-action 'none'`) any of these would break the page
// or the read-only guarantee. Comments are stripped before matching so a
// grep-able comment cannot make the scan lie (HANDOFF's lesson).
import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const SRC = join(__dirname, "..", "src");

function stripComments(source: string): string {
  // Block comments and line comments. Strings are left intact: a
  // `dangerouslySetInnerHTML` inside a string is exactly what this scan must find.
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

function sources(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...sources(full));
    else if (/\.(ts|tsx|js|jsx)$/.test(entry.name)) out.push(full);
  }
  return out;
}

describe("F10: the sources stay inside the §8.4 CSP", () => {
  const files = sources(SRC).map((path) => ({
    path,
    code: stripComments(readFileSync(path, "utf-8")),
  }));

  it("scans a non-empty src tree", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it("has no dangerouslySetInnerHTML", () => {
    const offenders = files.filter(({ code }) => code.includes("dangerouslySetInnerHTML"));
    expect(offenders.map((f) => f.path.replace(SRC, ""))).toEqual([]);
  });

  it("has no <style element or style tag in a string", () => {
    const offenders = files.filter(({ code }) => code.includes("<style"));
    expect(offenders.map((f) => f.path.replace(SRC, ""))).toEqual([]);
  });

  it("does not use the shadcn chart component (its ChartStyle injects a <style>)", () => {
    const offenders = files.filter(({ code }) => code.includes("components/ui/chart"));
    expect(offenders.map((f) => f.path.replace(SRC, ""))).toEqual([]);
  });

  it("has no non-GET fetch", () => {
    const offenders: string[] = [];
    for (const { path, code } of files) {
      for (const match of code.matchAll(/method\s*:\s*["'`]([A-Za-z]+)["'`]/g)) {
        // v2.1: lib/control.ts is the one module allowed to write (tests/writes.test.ts).
        if (match[1].toUpperCase() !== "GET" && !path.endsWith("/lib/control.ts")) {
          offenders.push(`${path}: ${match[0]}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("has no <form> element without an onSubmit", () => {
    // v2.1: forms exist, but `form-action 'none'` blocks a native submit, so each handles it.
    const offenders = files.filter(({ code }) =>
      [...code.matchAll(/<form\b([^>]*)>/gi)].some((m) => !/\bonSubmit\s*=/.test(m[1])));
    expect(offenders.map((f) => f.path.replace(SRC, ""))).toEqual([]);
  });
});
