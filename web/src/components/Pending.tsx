// The "computing…" state: a fetch that has not answered yet (§3.2). A zero is never
// shown for an unknown (§4.2 rule 1).
export default function Pending({ label = "computing…" }: { label?: string }) {
  return (
    <span className="pending" role="status">
      {label}
    </span>
  );
}
