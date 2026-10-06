import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";

// Admin (§4.1): credentials presence only — booleans, never values (§1.3: no secrets
// in the frontend; A-T1/A5). Configured and available backends and every instrument
// version, with the server's notes rendered verbatim (§4.2 rule 5).
export default function AdminPage() {
  const admin = useApi(() => api.admin(), []);
  if (admin.pending) {
    return (
      <section>
        <h1 className="text-[22px] font-semibold">Administration</h1>
        <Pending label="loading admin…" />
      </section>
    );
  }
  if (admin.error) {
    return (
      <section>
        <h1 className="text-[22px] font-semibold">Administration</h1>
        <ErrorState error={admin.error} />
      </section>
    );
  }
  const data = admin.data;
  if (!data) return null;
  const instruments = Object.entries(data.instruments).sort(([a], [b]) =>
    a.localeCompare(b),
  );
  return (
    <section className="flex flex-col gap-5">
      <h1 className="text-[22px] font-semibold">Administration</h1>

      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-semibold">credentials — presence only</h2>
        {Object.entries(data.credentials).map(([name, present]) => (
          <p key={name} className="mt-1 text-sm">
            <span className="font-mono text-xs">{name}</span>:{" "}
            {present ? "set" : "not set"}
          </p>
        ))}
        <p className="mt-2 text-xs text-muted-foreground">{data.key_rotation_note}</p>
      </section>

      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-semibold">model backends</h2>
        <p className="mt-1 text-sm">configured: {data.backends.configured.join(", ")}</p>
        <p className="mt-1 text-sm">available: {data.backends.available.join(", ")}</p>
        <p className="mt-2 text-xs text-muted-foreground">{data.backends_note}</p>
      </section>

      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-semibold">instrument versions</h2>
        {instruments.map(([name, version]) => (
          <p key={name} className="mt-1 font-mono text-xs">
            {name} {version}
          </p>
        ))}
        <p className="mt-2 text-xs text-muted-foreground">
          Every version the design record must acknowledge; the integrity panel reports
          whether it does.
        </p>
      </section>
    </section>
  );
}
