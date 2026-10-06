// The SPA is client-rendered only: no Node server in production, no prerendering
// (design §1.2, option E; §4.1 `+layout.ts`).
export const ssr = false;
export const prerender = false;