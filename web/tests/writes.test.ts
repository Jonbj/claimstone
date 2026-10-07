// F1: writes go through one module (spec v2.1 §1 rules 5 and 6). A source scan of `src/` finds:
// a non-GET `method:` only in `lib/control.ts`; `fetch` only in `lib/api.ts` (GET only) and
// `lib/control.ts`; and every `<form` with an `onSubmit` (the CSP has `form-action 'none'`, so
// a native submit would be blocked). Comments are stripped before matching, so a grep-able
// comment cannot make the scan lie (HANDOFF's "grep matches the comment" lesson).
import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const SRC = join(__dirname, "..", "src");

function stripComments(source: string): string {
  // Block comments and line comments. Strings are left intact:
  // a `method: "POST"` inside a string is exactly what this scan must find.
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

const rel = (path: string) => path.replace(SRC, "");

describe("F1: writes go through lib/control.ts only", () => {
  const files = sources(SRC).map((path) => ({
    path,
    code: stripComments(readFileSync(path, "utf-8")),
  }));

  it("scans a non-empty src tree", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it("has a non-GET `method:` only in src/lib/control.ts", () => {
    const where = new Set<string>();
    for (const { path, code } of files) {
      for (const match of code.matchAll(/method\s*:\s*["'`]([A-Za-z]+)["'`]/g)) {
        if (match[1].toUpperCase() !== "GET") where.add(rel(path));
      }
    }
    expect([...where]).toEqual(["/lib/control.ts"]);
  });

  it("has no `method:` that is not a string literal outside control.ts", () => {
    // `fetch(url, { method })` or `method: verb` would hide a verb from the scan above.
    const offenders = files
      .filter(({ path }) => !rel(path).endsWith("/lib/control.ts"))
      .filter(({ code }) => /\bmethod\s*:\s*[^\s"'`]/.test(code) || /[{,]\s*method\s*[,}]/.test(code))
      .map(({ path }) => rel(path));
    expect(offenders).toEqual([]);
  });

  it("calls fetch only from src/lib/api.ts and src/lib/control.ts", () => {
    const callers = files.filter(({ code }) => /\bfetch\s*\(/.test(code)).map((f) => rel(f.path));
    expect(callers.sort()).toEqual(["/lib/api.ts", "/lib/control.ts"]);
  });

  it("keeps src/lib/api.ts GET only", () => {
    const api = files.find(({ path }) => rel(path) === "/lib/api.ts")!;
    const verbs = [...api.code.matchAll(/method\s*:\s*["'`]([A-Za-z]+)["'`]/g)].map((m) => m[1]);
    expect(verbs.length).toBeGreaterThan(0);
    expect(verbs.every((v) => v.toUpperCase() === "GET")).toBe(true);
  });

  it("gives every <form> an onSubmit", () => {
    const offenders: string[] = [];
    for (const { path, code } of files) {
      for (const match of code.matchAll(/<form\b([^>]*)>/gi)) {
        if (!/\bonSubmit\s*=/.test(match[1])) offenders.push(rel(path));
      }
    }
    expect(offenders).toEqual([]);
  });
});
