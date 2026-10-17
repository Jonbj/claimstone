import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import LineageView from "@/components/Lineage";
import type { Lineage } from "@/lib/api-types";

const base = (reviewedBy: unknown): Lineage => ({
  api_version: 1, claim_id: "c1", project: "demo", selector: { manifest_only: false, round: null },
  source_id: "S1",
  steps: {
    acquisition: null, acquisition_candidate_key: null, candidate: null, chunk: null,
    claim: { claim: "x", stance: "QUALIFIES", question_id: "Q01", source_class: "ACA",
      claim_gate_version: "4", gate_revision: "1", backend: "b", model: "m", harness_version: "h",
      evidence_quote: "q" },
    document: null, document_pdf_instrument: null,
    review: { verdict: "SUPPORTED", reason: "ok", review_version: 2, reviewed_by: reviewedBy },
  },
});

describe("lineage reviewer", () => {
  afterEach(cleanup);

  it("renders a reviewer recorded as an object (backend, model, harness) instead of crashing", () => {
    render(<MemoryRouter><LineageView lineage={base({ backend: "ollama-cloud", model: "mistral-large-3:675b",
      harness_version: "h2" })} sourceHref={() => "/s"} /></MemoryRouter>);
    expect(screen.getByText(/ollama-cloud\/mistral-large-3:675b \(h2\)/)).toBeTruthy();
  });

  it("still renders a reviewer recorded as a plain string, and none at all", () => {
    render(<MemoryRouter><LineageView lineage={base("reader-a")} sourceHref={() => "/s"} /></MemoryRouter>);
    expect(screen.getByText(/reader-a/)).toBeTruthy();
    cleanup();
    render(<MemoryRouter><LineageView lineage={base(null)} sourceHref={() => "/s"} /></MemoryRouter>);
    expect(screen.getByText(/review v2/)).toBeTruthy();
  });
});
