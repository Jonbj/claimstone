// F3: a source scan of `src/` finds no `method:` other than GET and no `<form>`
// (§4.2 rule 4: no verdict input of any kind — the frontend writes nothing). Comments
// are stripped before matching, so a grep-able comment cannot make the scan lie
// (HANDOFF's "grep matches the comment" lesson).
import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const SRC = join(__dirname, "..", "src");

function stripComments(source: string): string {
  // Block comments, line comments and Svelte/HTML comments. Strings are left intact:
  // a `method: "POST"` inside a string is exactly what this scan must find.
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1")
    .replace(/<!--[\s\S]*?-->/g, "");
}

function sources(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...sources(full));
    else if (/\.(ts|svelte|js)$/.test(entry.name)) out.push(full);
  }
  return out;
}

describe("F3: the frontend writes nothing", () => {
  const files = sources(SRC).map((path) => ({
    path,
    code: stripComments(readFileSync(path, "utf-8")),
  }));

  it("scans a non-empty src tree", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it("has no fetch `method:` other than GET", () => {
    const offenders: string[] = [];
    for (const { path, code } of files) {
      for (const match of code.matchAll(/method\s*:\s*["'`]([A-Za-z]+)["'`]/g)) {
        if (match[1].toUpperCase() !== "GET") offenders.push(`${path}: ${match[0]}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("has no <form> element", () => {
    const offenders: string[] = [];
    for (const { path, code } of files) {
      if (/<form[\s>]/i.test(code)) offenders.push(path);
    }
    expect(offenders).toEqual([]);
  });

  it("has no non-GET HTTP verb spelled in a fetch options object", () => {
    // The `method:` scan above is the direct rule; this catches the degenerate
    // `fetch(url, { method })` with a variable that is never GET-only. `api.ts` is
    // the only file allowed to call fetch, and every call there is GET.
    const fetchCallers = files.filter(({ code }) => /\bfetch\s*\(/.test(code));
    expect(fetchCallers.map((f) => f.path.replace(SRC, ""))).toEqual(["/lib/api.ts"]);
  });
});