// Rounds from a cadence, and the early checks the server repeats (claimstone/periodic.py `plan`).
// All times are UTC midnight. The server stays the authority: its refusal is shown verbatim.
export type Cadence =
  | { kind: "monthly"; start: string; count: number }
  | { kind: "weekly"; start: string; count: number }
  | { kind: "days"; start: string; every: number; count: number };

/** An instant the server accepts: UTC, with a time and a Z (or +00:00). */
export const isUtcInstant = (text: string): boolean => UTC_ISO.test(text) && !Number.isNaN(Date.parse(text));

export interface RoundDraft { round: string; title: string; not_before: string; expires_at: string }
export type ProblemCode =
  "COUNT" | "FORMAT" | "NAME" | "TITLE" | "PAST" | "ORDER" | "OVERLAP" | "DUPLICATE" | "KNOWN" | "TOO_FAR" | "WINDOW";
export interface RoundProblem { index: number; code: ProblemCode }

const DAY = 86_400_000;
// What the server accepts as an instant: UTC, with a time and a Z (or +00:00).
const UTC_ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$/;
const iso = (d: Date) => `${d.toISOString().slice(0, 19)}Z`;
const parseDay = (s: string) => new Date(`${s}T00:00:00Z`);

function addMonths(start: Date, months: number): Date {
  const y = start.getUTCFullYear(), m = start.getUTCMonth() + months, day = start.getUTCDate();
  const last = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();   // last day of the target month
  return new Date(Date.UTC(y, m, Math.min(day, last)));
}

function boundaries(c: Cadence): Date[] {
  const start = parseDay(c.start);
  const out: Date[] = [];
  for (let i = 0; i <= c.count; i += 1) {
    out.push(c.kind === "monthly" ? addMonths(start, i)
      : new Date(start.getTime() + i * (c.kind === "weekly" ? 7 : c.every) * DAY));
  }
  return out;
}

const slug = (text: string) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
  .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "round";

/** One window per step, each ending exactly where the next begins (the server allows end == next start). */
export function generateRounds(c: Cadence, titlePrefix: string): RoundDraft[] {
  const b = boundaries(c);
  const unit = c.kind === "monthly" ? 7 : 10;                  // YYYY-MM or YYYY-MM-DD
  return b.slice(0, c.count).map((from, i) => {
    const label = iso(from).slice(0, unit);
    return { round: `${slug(titlePrefix)}-${label}`, title: `${titlePrefix} ${label}`,
             not_before: iso(from), expires_at: iso(b[i + 1]) };
  });
}

/** Early messages only. `knownRounds` are the rounds that already have candidates. The server's refusal is shown verbatim when it differs. */
export function checkRounds(rounds: RoundDraft[], knownRounds: Set<string>, now: Date): RoundProblem[] {
  const problems: RoundProblem[] = [];
  if (rounds.length < 1 || rounds.length > 32) problems.push({ index: -1, code: "COUNT" });
  const seen = new Set<string>();
  let lastStart = -Infinity, lastEnd = -Infinity;
  rounds.forEach((r, index) => {
    if (!/^[A-Za-z0-9_-]{1,80}$/.test(r.round)) problems.push({ index, code: "NAME" });
    if (seen.has(r.round)) problems.push({ index, code: "DUPLICATE" });
    if (knownRounds.has(r.round)) problems.push({ index, code: "KNOWN" });
    seen.add(r.round);
    if (!r.title.trim()) problems.push({ index, code: "TITLE" });
    if (!isUtcInstant(r.not_before) || !isUtcInstant(r.expires_at)) {
      problems.push({ index, code: "FORMAT" });
      return;
    }
    const start = Date.parse(r.not_before), end = Date.parse(r.expires_at);
    if (!(start < end)) problems.push({ index, code: "WINDOW" });
    if (start <= now.getTime()) problems.push({ index, code: "PAST" });
    if (end > now.getTime() + 366 * DAY) problems.push({ index, code: "TOO_FAR" });
    if (start <= lastStart) problems.push({ index, code: "ORDER" });
    else if (start < lastEnd) problems.push({ index, code: "OVERLAP" });
    lastStart = start; lastEnd = end;
  });
  return problems;
}
