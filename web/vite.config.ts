import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [sveltekit()],
  resolve: {
    // Svelte 5 + Vitest: without "browser" the server build of svelte is loaded and
    // `mount()` is unavailable — components must run in the client bundle.
    conditions: ["browser"],
  },
  server: {
    proxy: {
      // Dev only: the API runs on the host at 127.0.0.1:8788 (design §4.1).
      "/api": "http://127.0.0.1:8788",
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.{test,spec}.ts"],
  },
});