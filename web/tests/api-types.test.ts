// F8: `api-types.ts` is up to date with the schema — `gen:types` produces no diff.
// The committed file must equal what regenerating from docs/contracts/portal-api.schema.json
// produces, so a schema change that reaches the frontend is a build failure, not a silent
// type drift.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";

const webRoot = join(import.meta.dirname ?? ".", "..");

test("F8: api-types.ts equals the types regenerated from the committed schema", () => {
  const generated = execFileSync(
    process.execPath,
    [join(webRoot, "node_modules/json-schema-to-typescript/dist/src/cli.js"),
     join(webRoot, "../docs/contracts/portal-api.schema.json")],
    { encoding: "utf-8", cwd: webRoot },
  );
  const committed = readFileSync(join(webRoot, "src/lib/api-types.ts"), "utf-8");
  expect(generated).toBe(committed);
});