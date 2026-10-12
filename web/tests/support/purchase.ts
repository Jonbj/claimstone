// A page of the scheduler offers no purchase. Two catalog sentences say so in as many words (the
// copy policy's and the local mandate's "what it does not permit"); they are asserted present and then
// taken out, and the REST of the text must contain no word of buying, paying or ordering.
import { expect } from "vitest";
import { CATALOGS } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n";

const WORDS = /\b(buy|buys|bought|purchase|purchases|pay|pays|payment|price|prices|subscribe|subscription|checkout|order|orders|acquisto|acquisti|acquista|acquistare|prezzo|prezzi|abbonamento|compra|compri|comprare|paga|paghi|pagamento)\b/i;

export function expectNoPurchaseWording(text: string, locale: Locale, denials: Array<"sched.policy.forbids" | "sched.mandate.forbids"> = []) {
  let rest = text;
  for (const key of denials) {
    const sentence = CATALOGS[locale][key];
    expect(rest).toContain(sentence);
    rest = rest.replace(sentence, "");
  }
  expect(rest).not.toMatch(WORDS);
}
