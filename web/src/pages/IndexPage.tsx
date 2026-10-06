// Minimal index page so the router has a route and the build has a page; the lazy
// per-selector index is R3's deliverable (§8.3 "Index").
export default function IndexPage() {
  return (
    <main className="mx-auto max-w-[1360px] px-8 py-7">
      <h1 className="text-[22px] font-semibold text-gray-900">Projects</h1>
      <p className="mt-1 text-sm text-gray-500">the per-selector summaries land in R3</p>
    </main>
  );
}
