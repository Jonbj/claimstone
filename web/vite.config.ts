import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";
import path from "node:path";

const webRoot = path.dirname(fileURLToPath(import.meta.url));

// §8.4: the CSP is a plain header, sent by nginx in production and by `vite preview`
// here — a Vite build has no inline script, so nothing needs a hash.
const CSP =
  "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; " +
  "font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; " +
  "frame-ancestors 'none'";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(webRoot, "src"),
    },
  },
  server: {
    proxy: {
      // Dev only: the API runs on the host at 127.0.0.1:8788 (design §4.1).
      "/api": "http://127.0.0.1:8788",
    },
  },
  preview: {
    headers: {
      "Content-Security-Policy": CSP,
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.{test,spec}.ts", "tests/**/*.{test,spec}.tsx"],
  },
});
