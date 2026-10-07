// R5.4: the profile-diff panel — an audit view that concludes nothing. The
// entries render verbatim (claim, evidence_quote, stance, source class, the
// removed entry's recorded reason, the changed entry's from → to pairs), the
// counts are labelled a count, not a strength, no verdict word appears, and
// the API's 400/404 refusals render as named states with the envelope message
// verbatim. The empty diff is the committed fixture (from==to). Input and
// click go through `fireEvent`: `@testing-library/user-event` is not a
// dependency of this project and installing one is outside R5's scope.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import type { ProfileDiff } from "@/lib/api-types";
import ProfileDiffPanel from "@/components/ProfileDiffPanel";
import emptyDiff from "./fixtures/projects/example-news-and-returns/flows/0df548e3743689e1a0dd099da697aee4842e8a573f1225a8da13fec128a248cd/questions/Q02.profile-diff.from-7056ff48a8e45f615aadc993d51035ac4add9a7686d5190f3fee1703f759f9c5&to-7056ff48a8e45f615aadc993d51035ac4add9a7686d5190f3fee1703f759f9c5.json";

// A payload shaped as `portal_state.profile_diff` builds it: one added, one
// removed (carrying the ledger's recorded reason), one changed (a re-worded
// claim), and a diff-level reason naming the instrument version that moved.
const fullDiff: ProfileDiff = {
  api_version: 1,
  project: "example-news-and-returns",
  selector: { manifest_only: false, round: "r1" },
  id: "Q02",
  from: {
    profile_sha256: "aaaa0000000000000000000000000000000000000000000000000000000000aa",
    built_at: "2026-10-05T10:00:00+00:00",
    claim_gate_version: 4,
    decision_contract_version: 1,
    registry_version: 2,
  },
  to: {
    profile_sha256: "bbbb1111111111111111111111111111111111111111111111111111111111bb",
    built_at: "2026-10-06T10:00:00+00:00",
    claim_gate_version: 5,
    decision_contract_version: 1,
    registry_version: 2,
  },
  reason: "claim_gate_version 4 → 5",
  summary: { added: 1, removed: 1, changed: 1 },
  added: [
    {
      result_id: "c9",
      reason: null,
      result: {
        claim_id: "c9", source_id: "S03", source_class: "ACA", stance: "SUPPORTS",
        claim: "News tone has a small effect.",
        evidence_quote: "news tone has an effect",
      },
    },
  ],
  removed: [
    {
      result_id: "c1",
      reason: "review OVERSTATED: The quote reports a mean, not predictive power.",
      result: {
        claim_id: "c1", source_id: "S01", source_class: "ACA", stance: "SUPPORTS",
        claim: "News tone has an effect.",
        evidence_quote: "news tone has an effect",
      },
    },
  ],
  changed: [
    {
      result_id: "c2",
      reason: null,
      fields: { claim: { from: "News tone has an effect.", to: "News tone has a large effect." } },
    },
  ],
  counts: {
    from: { by_class: { for: { ACA: 1 }, against: {} }, direction_count: { SUPPORTS: 1 } },
    to: { by_class: { for: { ACA: 1 }, against: {} }, direction_count: { SUPPORTS: 1 } },
  },
} as unknown as ProfileDiff;

const CURRENT_SHA =
  "7056ff48a8e45f615aadc993d51035ac4add9a7686d5190f3fee1703f759f9c5";

vi.mock("@/lib/api", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...real,
    api: {
      ...real.api,
      profileDiff: vi.fn(async () => fullDiff),
    },
  };
});

const { api } = await import("@/lib/api");
const profileDiff = vi.mocked(api.profileDiff);

function renderPanel(currentSha: string | null = CURRENT_SHA) {
  return render(
    <MemoryRouter>
      <ProfileDiffPanel
        project="example-news-and-returns"
        kind="f"
        sel="0df548e3743689e1a0dd099da697aee4842e8a573f1225a8da13fec128a248cd"
        qid="Q02"
        currentProfileSha256={currentSha}
      />
    </MemoryRouter>,
  );
}

function askForDiff(toSha: string, fromSha?: string) {
  const inputs = screen.getAllByRole("textbox") as HTMLInputElement[];
  // First textbox is `from`, second is `to` (DOM order).
  fireEvent.change(inputs[0], { target: { value: fromSha ?? inputs[0].value } });
  fireEvent.change(inputs[1], { target: { value: toSha } });
  fireEvent.click(screen.getByRole("button", { name: "compare" }));
}

beforeEach(() => {
  profileDiff.mockResolvedValue(fullDiff as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("R5.4: ProfileDiffPanel", () => {
  it("does not fetch until the compare action asks for a diff", async () => {
    renderPanel();
    expect(profileDiff).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "compare" }));
    // The button is disabled with an empty `to`: no call, no fetch.
    expect(profileDiff).not.toHaveBeenCalled();
    askForDiff("bbbb1111");
    await waitFor(() => expect(profileDiff).toHaveBeenCalledTimes(1));
  });

  it("prefills from with the question's current profile hash", () => {
    renderPanel(CURRENT_SHA);
    const inputs = screen.getAllByRole("textbox") as HTMLInputElement[];
    expect(inputs[0].value).toBe(CURRENT_SHA);
  });

  it("leaves the from input empty when the page holds no profile hash", () => {
    renderPanel(null);
    const inputs = screen.getAllByRole("textbox") as HTMLInputElement[];
    expect(inputs[0].value).toBe("");
  });

  it("renders the diff-level reason and every entry verbatim, with lineage links", async () => {
    const { container } = renderPanel(CURRENT_SHA);
    askForDiff("bbbb1111");
    await waitFor(() => expect(container.textContent).toContain("claim_gate_version 4 → 5"));

    // The three labelled summary counts.
    expect(container.textContent).toContain("added 1 · removed 1 · changed 1");

    // Added: claim text, verbatim quote, stance, source class, lineage link.
    expect(screen.getByText("News tone has a small effect.")).toBeTruthy();
    // The quote appears verbatim in both the added and the removed entry.
    expect(screen.getAllByText("news tone has an effect").length).toBe(2);
    expect(screen.getAllByText("SUPPORTS").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ACA").length).toBeGreaterThan(0);
    const addedLink = screen.getByText("c9");
    expect(addedLink.getAttribute("href")).toContain("/claim/c9");

    // Removed: the ledger's recorded reason, verbatim — never a narrative.
    expect(
      screen.getByText("review OVERSTATED: The quote reports a mean, not predictive power."),
    ).toBeTruthy();

    // Changed: per-field from → to values, verbatim.
    expect(
      screen.getByText('"News tone has an effect." → "News tone has a large effect."'),
    ).toBeTruthy();
    const changedLink = screen.getByText("c2");
    expect(changedLink.getAttribute("href")).toContain("/claim/c2");
  });

  it("labels the counts as a count, not a strength", async () => {
    const { container } = renderPanel(CURRENT_SHA);
    askForDiff("bbbb1111");
    await waitFor(() => expect(container.textContent).toContain("counts — a count, not a strength"));
    expect(container.textContent).toContain("for: ACA 1");
    expect(container.textContent).toContain("SUPPORTS 1");
  });

  it("renders no verdict word anywhere", async () => {
    const { container } = renderPanel(CURRENT_SHA);
    askForDiff("bbbb1111");
    await waitFor(() => expect(container.textContent).toContain("added 1 · removed 1 · changed 1"));
    const text = container.textContent ?? "";
    for (const verdict of ["SUPPORTED", "CONTRADICTED", "CONTESTED_IN_LITERATURE",
                           "UNANSWERED_IN_LITERATURE", "NEVER_ASKED"]) {
      expect(text).not.toContain(verdict);
    }
  });

  it("renders the committed empty-diff fixture: no entries, no reason, counts equal", async () => {
    profileDiff.mockResolvedValue(emptyDiff as never);
    const { container } = renderPanel(CURRENT_SHA);
    askForDiff(CURRENT_SHA);
    await waitFor(() => expect(container.textContent).toContain("added 0 · removed 0 · changed 0"));
    expect(container.textContent).not.toMatch(/\breason\s/);
    // No entry sections: the only h3 is the counts heading.
    const entryHeadings = [...container.querySelectorAll("h3")]
      .map((h) => h.textContent)
      .filter((t) => t === "added" || t === "removed" || t === "changed");
    expect(entryHeadings).toEqual([]);
    // from and to sides carry the same hash.
    expect(
      (container.textContent ?? "").match(
        /7056ff48a8e45f615aadc993d51035ac4add9a7686d5190f3fee1703f759f9c5/g,
      )?.length,
    ).toBe(2);
  });

  it("renders a 404 with its code named and the envelope message verbatim", async () => {
    profileDiff.mockRejectedValue(new ApiError(
      "NOT_FOUND",
      "from profile 0000000000000000000000000000000000000000000000000000000000000000 not in the ledger for question Q02",
    ));
    const { container } = renderPanel(CURRENT_SHA);
    askForDiff("bbbb1111");
    await waitFor(() => expect(container.textContent).toContain("NOT_FOUND"));
    expect(container.textContent).toContain(
      "not in the ledger for question Q02",
    );
  });

  it("renders a 400 with its code named and the envelope message verbatim", async () => {
    profileDiff.mockRejectedValue(new ApiError(
      "BAD_REQUEST",
      "query parameter 'from' is required",
    ));
    const { container } = renderPanel(CURRENT_SHA);
    askForDiff("bbbb1111");
    await waitFor(() => expect(container.textContent).toContain("BAD_REQUEST"));
    expect(container.textContent).toContain("query parameter 'from' is required");
  });
});