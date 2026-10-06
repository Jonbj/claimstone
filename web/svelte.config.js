// SvelteKit static SPA: no Node server in production (design §1.2, option E).
import adapter from "@sveltejs/adapter-static";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      fallback: "index.html",
    }),
    // The SPA's bootstrap is an inline <script>. With mode "hash" SvelteKit puts a CSP <meta>
    // carrying that script's hash into index.html, so no 'unsafe-inline' is ever needed.
    // nginx adds only what a <meta> CSP cannot carry (frame-ancestors) — see design §4.3.
    csp: {
      mode: "hash",
      directives: {
        "default-src": ["none"],
        "script-src": ["self"],
        "style-src": ["self"],
        "img-src": ["self", "data:"],
        "font-src": ["self"],
        "connect-src": ["self"],
        "base-uri": ["none"],
        "form-action": ["none"],
      },
    },
  },
};

export default config;