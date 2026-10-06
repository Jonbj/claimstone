// Run after `vite build`: the built SPA must carry its own hash-based CSP and nothing that
// needs 'unsafe-inline'. nginx can only add what a <meta> CSP cannot carry (frame-ancestors);
// if this check fails, the page would be blank behind the production headers.
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../build/index.html", import.meta.url), "utf8");
const meta = html.match(/<meta http-equiv="content-security-policy" content="([^"]+)">/);
const problems = [];
if (!meta) problems.push("no CSP <meta> in build/index.html (svelte.config.js kit.csp)");
const policy = meta ? meta[1] : "";
if (policy.includes("unsafe-inline")) problems.push("CSP allows 'unsafe-inline'");
const inlineScripts = (html.match(/<script(?![^>]*\bsrc=)[^>]*>/g) || []).length;
if (inlineScripts && !/script-src[^;]*'sha256-/.test(policy)) {
  problems.push(`${inlineScripts} inline <script> without a sha256 source in script-src`);
}
if (/\sstyle="/.test(html)) problems.push("inline style attribute in index.html");
if (problems.length) {
  console.error("check-csp: " + problems.join("; "));
  process.exit(1);
}
console.log(`check-csp: ok (${inlineScripts} inline script(s), hashed)`);
