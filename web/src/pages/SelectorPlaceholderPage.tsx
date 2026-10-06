import { useParams } from "react-router";

// Placeholder for R4 (the flow overview page): the index's rows link here today, so the
// route resolves to a named page rather than the router's default error screen.
export default function SelectorPlaceholderPage() {
  const { project, sel } = useParams();
  return (
    <section>
      <h1 className="font-mono text-[18px] font-semibold">
        {project} · {sel?.slice(0, 12)}
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        the overview page lands in R4
      </p>
    </section>
  );
}
