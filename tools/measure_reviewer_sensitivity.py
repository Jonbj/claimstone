"""Does a candidate reviewer catch a claim that is known to overstate its quote?

Stage 5's whole value is `OVERSTATED`, and a reviewer that says `SUPPORTED` to everything is worse than
no reviewer: it flatters the extractor and adds a column of false reassurance to every figure downstream.
The review rate alone cannot tell the two apart, because a high `SUPPORTED` share is what a good extractor
and a lenient reader both produce.

So this measures against a ground truth the store already holds — but a narrower one than the obvious
choice. A record rejected for `NUMBER_NOT_IN_QUOTE` passed the quote check and then asserted a figure the
quoted span does not contain, which sounds like overstatement established mechanically. It is not clean:
the gate checks the figure against the **quote**, while stage 5's prompt asks the reviewer to judge in the
context of the **whole passage**, so a reviewer who finds the figure two sentences later and says
`SUPPORTED` is answering the question it was asked. Measuring leniency that way charges the reviewer for
the gate's stricter standard. First run of this tool did exactly that and reported 0.15 for a reviewer
that may simply have been reading the passage.

So the set is narrowed to records asserting a figure absent from **the whole chunk**. Those are
unambiguous under either standard — the number appears nowhere the reviewer can see it — and a reviewer
that reads them as `SUPPORTED` is not reviewing.

The accepted claims from the same chunks are run beside them, because sensitivity alone is cheap: a
reviewer that answers `OVERSTATED` to everything scores perfectly on the first set and is equally useless.

Usage:
    tools/measure_reviewer_sensitivity.py <project> [--backend B] --model <tag> [--n 30]
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import sys
from typing import Any
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from claimstone import chunk_sets
from claimstone import claimgate, config, model_call, review  # noqa: E402
from claimstone import runners  # noqa: E402
from claimstone.store import Store  # noqa: E402

# Anything but SUPPORTED counts as caught. A reviewer calling an absent figure `AMBIGUOUS` has still
# declined to pass it, which is what stage 6 needs of it.
CAUGHT = ("OVERSTATED", "AMBIGUOUS", "NOT_APPLICABLE")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--model", required=True)
    parser.add_argument("--backend", default="ollama-cloud",
                        help="which backend serves the candidate; a reviewer is a (backend, model) pair")
    parser.add_argument("--n", type=int, default=30, help="how many of each set")
    parser.add_argument("--seed", type=int, default=0)
    # A cap fitted to one model is not a fair test of another (D31). Stage 5 ships 400.
    parser.add_argument("--max-output", type=int, default=review.MAX_OUTPUT_TOKENS)
    args = parser.parse_args()

    project = config.load_project(args.project)
    store = Store(pathlib.Path(args.project).name)
    questions = {q.id: q for q in project.questions}
    chunks = chunk_sets.current(store)

    def still_overstates(row: dict) -> bool:
        """Re-judged under the gate as it is now, and the figure absent from the whole passage.

        The stored `failure` and `detail` are **not** trusted. A rejection ledger keeps the label it was
        written with, and the gate has three rule sets: an earlier run of this tool scored reviewers
        against rows whose figures the current gate does not consider asserted at all — `89-91%` read as
        minus 91, a per-cent sign the quote left implicit — and a reviewer calling those `SUPPORTED` was
        right while this tool counted it wrong. So every candidate row is put back through `check`.
        """
        record = row.get("record") or {}
        chunk = chunks.get(str(row.get("chunk_id")))
        if chunk is None:
            return False
        text = str(chunk["text"])
        verdict = claimgate.check(record, chunk=text, questions=project.questions,
                                  lane=str(row.get("lane") or ""))
        if verdict.failure != "NUMBER_NOT_IN_QUOTE":
            return False
        # Absent from the passage, not merely from the quote: the reviewer is asked to judge in context,
        # so a figure two sentences away is one it may legitimately rely on.
        figures = [f for f in claimgate._asserted_numerals(str(record.get("claim") or ""))
                   if not claimgate._figure_present(f, text)]
        return bool(figures)

    overstating = [r for r in store.read("rejections.jsonl")
                   if r.get("record") and still_overstates(r)]
    honest = list(store.read("claims.jsonl"))

    rng = random.Random(args.seed)
    rng.shuffle(overstating)
    rng.shuffle(honest)

    def unit(question_id: str, claim: dict, chunk_id: str) -> str | None:
        chunk = chunks.get(chunk_id)
        question = questions.get(question_id)
        if chunk is None or question is None:
            return None
        return review.review_unit(question, claim, str(chunk["text"]))

    work: list[tuple[str, str]] = []   # (which set, user prompt)
    for row in overstating:
        if len([w for w in work if w[0] == "overstating"]) >= args.n:
            break
        # A rejection row keeps the question id inside `record`, where a claim row has it at the top.
        user = unit(str(row["record"].get("question_id")), row["record"], str(row.get("chunk_id")))
        if user:
            work.append(("overstating", user))
    for row in honest:
        if len([w for w in work if w[0] == "honest"]) >= args.n:
            break
        user = unit(str(row.get("question_id")), row, str(row.get("chunk_id")))
        if user:
            work.append(("honest", user))

    options: dict[str, Any] = {"model": args.model}
    if args.backend == "ollama-cloud":
        # The two settings the extraction lane runs under, so this measures the same configuration.
        options |= {"think": False, "enforce_schema": True}
    runner = runners.build(args.backend, **options)
    print(f"{len(work)} calls on {runner.name}/{args.model} at a {args.max_output}-token "
          f"cap, {runner.max_concurrency} at a time", flush=True)

    def ask(item: tuple[str, str]) -> tuple[str, str, str]:
        which, user = item
        answer = runner.run({
            "system": review.SYSTEM, "user": user,
            "max_output_tokens": args.max_output,
            "response_schema": review.SCHEMA,
        })
        if answer.failure_class or not answer.body:
            return which, f"({answer.failure_class or 'NO_BODY'})", ""
        # Through `unfence`, as the real pipeline does: a model that wraps its object in a ```json
        # fence is not a model that failed to answer, and an earlier version of this tool called two
        # candidates unusable on 40 of 40 calls because it parsed the body raw.
        body = model_call.unfence(answer.body.decode("utf-8", "replace").strip())
        try:
            parsed = json.loads(body)
        except ValueError:
            return which, "(NOT_JSON)", body[:70].replace("\n", " ")
        return which, str(parsed.get("verdict") or "(NO_VERDICT)"), str(parsed.get("reason") or "")

    tally: dict[str, collections.Counter] = {
        "overstating": collections.Counter(), "honest": collections.Counter()}
    reasons: list[tuple[str, str, str]] = []
    with ThreadPoolExecutor(max_workers=runner.max_concurrency) as pool:
        for which, verdict, reason in pool.map(ask, work):
            tally[which][verdict] += 1
            reasons.append((which, verdict, reason))

    rates: dict[str, float] = {}
    for which, label in (("overstating", "claims the gate proved overstate their quote"),
                         ("honest", "claims the gate accepted")):
        counts = tally[which]
        answered = sum(v for k, v in counts.items() if not k.startswith("("))
        caught = sum(counts[v] for v in CAUGHT)
        print(f"\n{label}: {sum(counts.values())} asked, {answered} answered")
        for verdict, n in counts.most_common():
            print(f"   {verdict:18} {n}")
        if answered:
            name = "sensitivity" if which == "overstating" else "flagged anyway"
            rates[which] = caught / answered
            print(f"   {name}: {rates[which]:.2f}  ({caught} of {answered} not SUPPORTED)")

    if len(rates) == 2:
        # The quantity that decides. A reviewer saying SUPPORTED to everything scores 0 on the first
        # set; one saying OVERSTATED to everything scores 1 on both. Only the gap is information.
        #
        # The second rate is **not** a false-positive rate: stage 5 exists because a gate-passed claim
        # can still overstate its quote, and the spec's own reference corpus had 25.7% of them doing
        # so. So the ceiling on this gap is about 0.74, not 1.0, and a reviewer near zero carries no
        # information whichever direction it leans.
        print(f"\ndiscrimination: {rates['overstating'] - rates['honest']:+.2f}"
              f"   (sensitivity {rates['overstating']:.2f} - flagged-anyway {rates['honest']:.2f})")

    print("\nreasons given on the overstating set, which is where the judgement shows:")
    for which, verdict, reason in reasons:
        if which == "overstating":
            print(f"   {verdict:16} {reason[:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
