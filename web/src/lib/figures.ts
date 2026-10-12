// Request figures for a series, from the topics and the chosen sources. A preview: the server's
// `max_total_requests` is the figure that counts.
export const HOST_FOR: Record<string, string> = {
  openalex: "api.openalex.org", crossref: "api.crossref.org", arxiv: "export.arxiv.org" };
export const SOURCES = ["openalex", "crossref", "arxiv"] as const;

export const queryCount = (topics: Array<{ terms: string[] }>, apis: string[]): number =>
  topics.reduce((n, t) => n + t.terms.length, 0) * new Set(apis).size;

export const hostsFor = (apis: string[]): string[] =>
  [...new Set(apis.map((a) => HOST_FOR[a]).filter(Boolean))].sort();

export function figures(i: { topics: Array<{ terms: string[] }>; apis: string[]; maxRequestsEach: number; rounds: number }) {
  const searchesPerRound = queryCount(i.topics, i.apis);
  return { searchesPerRound, searchesTotal: searchesPerRound * i.rounds,
           requestsPerRound: searchesPerRound * i.maxRequestsEach,
           requestsTotal: searchesPerRound * i.maxRequestsEach * i.rounds,
           minUnitsEach: searchesPerRound };
}
