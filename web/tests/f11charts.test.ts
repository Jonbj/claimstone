// F11 (§8.5): `DonutChart` and `BarList` are fed only from `question_state_counts`
// and `rejections_by_reason`; the overview has no client-side counting over
// question rows. Also §8.2: `recharts` is used only through the Tremor components.
import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const SRC = join(__dirname, "..", "src");

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

function sources(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...sources(full));
    else if (/\.(ts|tsx)$/.test(entry.name)) out.push(full);
  }
  return out;
}

describe("F11: the charts are fed by the server's own aggregate fields", () => {
  const files = sources(SRC).map((path) => ({
    path,
    code: stripComments(readFileSync(path, "utf-8")),
  }));

  it("counts nothing over `questions.rows` anywhere in src", () => {
    const offenders: string[] = [];
    for (const { path, code } of files) {
      for (const line of code.split("\n")) {
        if (/questions\.rows/.test(line) && /\.(filter|reduce)\(/.test(line)) {
          offenders.push(`${path}: ${line.trim()}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("feeds the DonutChart from question_state_counts, not from row counting", () => {
    const kpis = files.find(({ path }) => path.endsWith("OverviewKpis.tsx"))!;
    expect(kpis.code).toContain("question_state_counts");
  });

  it("feeds the BarList from rejections_by_reason", () => {
    const page = files.find(({ path }) => path.endsWith("FlowOverviewPage.tsx"))!;
    expect(page.code).toContain("rejections_by_reason");
  });

  it("imports recharts only inside the Tremor copies", () => {
    const offenders = files
      .filter(({ path, code }) => !path.includes(join("components", "tremor")) && /from "recharts"/.test(code))
      .map((f) => f.path.replace(SRC, ""));
    expect(offenders).toEqual([]);
  });
});
