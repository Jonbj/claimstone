import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";

// Minimal index so the shell resolves: the project names straight from `/projects`,
// verbatim. The lazy per-selector index (summary cards, skeletons) is R3's deliverable.
export default function IndexPage() {
  const projects = useApi(() => api.projects(), []);
  return (
    <section>
      <h1 className="text-[22px] font-semibold">Projects</h1>
      {projects.pending ? (
        <Pending label="fetching projects…" />
      ) : projects.error ? (
        <ErrorState error={projects.error} />
      ) : (
        <ul className="mt-2 list-inside list-disc text-sm text-gray-700">
          {projects.data?.projects.map((project) => (
            <li key={project.name}>{project.name}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
