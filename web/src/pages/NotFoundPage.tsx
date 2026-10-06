import { Link } from "react-router";

// The catch-all: an unknown address is a named state, never a blank screen (§4.2
// rule 1's spirit; there is no API call to make for an address that is not a route).
export default function NotFoundPage() {
  return (
    <section>
      <h1 className="text-[22px] font-semibold">Not found</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        no page at this address —{" "}
        <Link to="/" className="text-blue-600 hover:underline dark:text-blue-400">
          back to the index
        </Link>
      </p>
    </section>
  );
}
