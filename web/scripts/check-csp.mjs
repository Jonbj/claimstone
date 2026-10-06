// §8.4: a Vite build has no inline script and no style attribute — the CSP can be a
// plain header. This runs after `vite build` and fails the build if either appears,
// because behind `script-src 'self'` / `style-src 'self'` the page would break.
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../dist/index.html", import.meta.url), "utf8");
const problems = [];
const inlineScripts = (html.match(/<script(?![^>]*\bsrc=)[^>]*>/g) || []).length;
if (inlineScripts) problems.push(`${inlineScripts} inline <script> in dist/index.html`);
if (/\sstyle="/.test(html)) problems.push("inline style attribute in dist/index.html");
if (problems.length) {
  console.error("check-csp: " + problems.join("; "));
  process.exit(1);
}
console.log("check-csp: ok (no inline script, no style attribute)");
