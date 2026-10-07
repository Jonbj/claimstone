import { useState } from "react";
import type { FormEvent } from "react";
import ErrorState from "@/components/ErrorState";
import { ControlError, VERDICTS, control } from "@/lib/control";
import type { Row, Verdict } from "@/lib/control";

// The signature panel (spec v2.1 F4). A PERSON signs here; nothing in this file chooses,
// suggests, defaults or remembers a verdict (CLAUDE.md: an agent does not sign). The panel is
// keyed by question by its parent, so a choice cannot travel from one question to the next, and
// nothing is written to storage.
//
// The hash a signature binds to is the one **displayed**: it is pinned when the panel appears.
// If the page later learns of a newer profile, the pinned hash is not swapped silently: the
// panel says the evidence changed and blocks signing until the operator takes the new one.
// The definitions are the verdict contract's table (2026-09-25-verdict-contract-design.md §4),
// shortened without changing what they say.
export const MIN_RATIONALE_CHARS = 120;

const DEFINITIONS: Record<Verdict, { name: string; means: string }> = {
  SUPPORTED: {
    name: "Supported",
    means: "the profile persuades on the evidence, and the rationale says why",
  },
  CONTRADICTED: { name: "Contradicted", means: "the profile persuades the other way" },
  CONTESTED_IN_LITERATURE: {
    name: "Contested in literature",
    means: "the literature speaks and disagrees irreducibly",
  },
  UNANSWERED_IN_LITERATURE: {
    name: "Unanswered in literature",
    means: "the corpus was read and does not settle it",
  },
  NEVER_ASKED: {
    name: "Never asked",
    means: "nobody asked, established by screening rather than inferred from silence",
  },
};

const card = "rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800";
const banner = "rounded-lg border border-amber-400 bg-amber-50 p-3 text-sm text-amber-950 dark:bg-amber-950/30 dark:text-amber-100";

/** Characters as the server counts them (code points, after trimming). */
export const trimmedLength = (text: string): number => [...text.trim()].length;

export default function SignaturePanel({
  project,
  flowId,
  qid,
  operatorName,
  latestHash,
  onReload,
  onCompare,
  onSigned,
}: {
  project: string;
  flowId: string;
  qid: string;
  operatorName: string;
  /** The hash of the profile the page currently holds. */
  latestHash: string;
  /** Re-reads the question and its stored profiles. */
  onReload: () => void;
  /** Asks the diff panel to compare two stored profiles. */
  onCompare: (from: string, to: string) => void;
  /** Called once a signature is stored. */
  onSigned: (row: Row) => void;
}) {
  const [shownHash, setShownHash] = useState(latestHash);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [rationale, setRationale] = useState("");
  const [attest, setAttest] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<ControlError | Error | null>(null);
  const [staleSeen, setStaleSeen] = useState(false);
  const [signed, setSigned] = useState<Row | null>(null);

  const changed = shownHash !== latestHash;
  const count = trimmedLength(rationale);
  const blocked = changed || staleSeen;
  const canSign = verdict !== null && count >= MIN_RATIONALE_CHARS && attest && !running && !blocked;

  function adopt() {
    setShownHash(latestHash);
    setStaleSeen(false);
    setAttest(false);
    setError(null);
  }

  async function sign(event: FormEvent) {
    event.preventDefault();
    if (!canSign || verdict === null) return;
    setRunning(true);
    setError(null);
    try {
      const reply = await control.adjudicate(project, flowId, qid, {
        verdict,
        rationale,
        profile_sha256: shownHash,
        attest: true,
      });
      setSigned(reply.adjudication);
      onSigned(reply.adjudication);
    } catch (cause) {
      const failure = cause instanceof Error ? cause : new Error(String(cause));
      setError(failure);
      if (failure instanceof ControlError && failure.code === "STALE_PROFILE") {
        setStaleSeen(true);
        onReload();
      }
    } finally {
      setRunning(false);
    }
  }

  if (signed) {
    return (
      <section className={card} aria-label="Signed verdict">
        <h2 className="text-lg">Signed</h2>
        <p className="mt-1 text-sm">
          The stored row: verdict <span className="font-mono">{String(signed.verdict)}</span>,
          adjudicated by <span className="font-semibold">{String(signed.adjudicated_by)}</span>, bound
          to profile <span className="break-all font-mono text-xs">{String(signed.profile_sha256)}</span>.
        </p>
      </section>
    );
  }

  return (
    <form className={`${card} flex flex-col gap-4`} aria-label="Sign the verdict" onSubmit={sign}>
      <div>
        <h2 className="text-lg">Your verdict on {qid}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Bound to profile <span className="font-mono" title={shownHash}>{shownHash.slice(0, 12)}</span>.
          If the evidence changes later, your signature is marked stale, never silently kept.
        </p>
      </div>

      {changed || staleSeen ? (
        <div className={banner} role="alert" data-testid="evidence-changed">
          <p className="font-semibold">The evidence changed</p>
          <p className="mt-1">
            {changed
              ? `The page now holds profile ${latestHash.slice(0, 12)}; you were reading ${shownHash.slice(0, 12)}. Your text is kept. Signing is blocked until you take the current profile.`
              : "Your text is kept. Signing is blocked until you reload the profile."}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {changed ? (
              <>
                <button type="button" className="rounded border border-border px-3 py-1" onClick={() => onCompare(shownHash, latestHash)}>
                  Compare with the current profile
                </button>
                <button type="button" className="rounded bg-primary px-3 py-1 text-primary-foreground" onClick={adopt}>
                  Use the current profile
                </button>
              </>
            ) : (
              <button type="button" className="rounded bg-primary px-3 py-1 text-primary-foreground" onClick={onReload}>
                Reload the profile
              </button>
            )}
          </div>
        </div>
      ) : null}

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-semibold">
          Verdict · {verdict ? DEFINITIONS[verdict].name : "none selected"}
        </legend>
        {VERDICTS.map((v) => (
          <label key={v} className="flex gap-3 rounded-lg border border-border p-3">
            <input
              type="radio"
              name="verdict"
              value={v}
              checked={verdict === v}
              onChange={() => setVerdict(v)}
              className="mt-1"
            />
            <span>
              <b>{DEFINITIONS[v].name}</b>
              <br />
              <span className="text-xs text-muted-foreground">{DEFINITIONS[v].means}</span>
            </span>
          </label>
        ))}
      </fieldset>

      <label className="flex flex-col gap-1 text-sm font-semibold">
        Your reasoning
        <textarea
          rows={6}
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          placeholder="Why this verdict, on this evidence, within this scope"
          className="rounded-lg border border-border bg-card p-3 text-sm font-normal"
        />
        <span className="text-xs font-normal text-muted-foreground" data-testid="char-count">
          {count} characters · at least {MIN_RATIONALE_CHARS}, not counting spaces at the ends
        </span>
      </label>

      <label className="flex items-start gap-3 text-sm">
        <input
          type="checkbox"
          checked={attest}
          onChange={(e) => setAttest(e.target.checked)}
          className="mt-1"
        />
        <span>
          I have read the evidence profile this verdict binds to (hash{" "}
          <span className="font-mono" title={shownHash}>{shownHash.slice(0, 12)}</span>)
        </span>
      </label>

      <ul aria-label="Signing requirements" className="flex flex-col gap-1 rounded-lg bg-muted/40 p-3 text-sm">
        <li>{verdict ? "✓" : "○"} A verdict chosen</li>
        <li>{count >= MIN_RATIONALE_CHARS ? "✓" : "○"} Reasoning of at least {MIN_RATIONALE_CHARS} characters</li>
        <li>{attest ? "✓" : "○"} Your reading attestation</li>
        <li>✓ Signed in as {operatorName}</li>
      </ul>

      {error ? <ErrorState error={error} context="signing" /> : null}

      <button
        type="submit"
        disabled={!canSign}
        className="min-h-12 rounded-lg bg-primary px-4 text-[15px] font-semibold text-primary-foreground disabled:opacity-50"
      >
        {running ? "Signing…" : `Sign as ${operatorName}`}
      </button>
    </form>
  );
}
