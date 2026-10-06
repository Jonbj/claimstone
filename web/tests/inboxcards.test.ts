// F7: `InboxCards` preserves server order. The UI does not sort, rank or filter inbox
// cards (§4.2 rule 6): the order the API sent is the order on screen. The fixture is
// the committed inbox payload the API serves.
import { render } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";
import InboxCards from "$lib/components/InboxCards.svelte";
import inbox from "./fixtures/projects/example-news-and-returns/flows/0df548e3743689e1a0dd099da697aee4842e8a573f1225a8da13fec128a248cd/inbox.json";

const cards = inbox.cards;

describe("F7: InboxCards preserves server order", () => {
  it("renders the cards in the order the API sent them", () => {
    const { container } = render(InboxCards, { cards });
    const rendered = [...container.querySelectorAll("[data-card-index]")].map((el) =>
      Number(el.getAttribute("data-card-index")),
    );
    expect(rendered).toEqual(cards.map((_, i) => i));
  });

  it("renders category, subject and cause verbatim", () => {
    const { container } = render(InboxCards, { cards });
    const text = container.textContent!;
    for (const card of cards.slice(0, 3)) {
      expect(text).toContain(card.category);
      expect(text).toContain(card.subject);
      expect(text).toContain(card.cause);
    }
  });

  it("shows a named empty state, never an empty page", () => {
    const { container } = render(InboxCards, { cards: [] });
    expect(container.textContent).toContain("nothing open in this scope");
  });
});