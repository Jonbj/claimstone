#!/usr/bin/env python
"""Derive the pilot corpus's reading list from its own discovery ledger.

A curated source list is what the manifest mechanism is for, and curating one by hand would mean writing
identifiers from memory — which for a project whose whole method is "a number names the command that
produced it" is the wrong way round. So the list is derived, by a rule stated here, from rows the APIs
actually returned.

**The rule.** A candidate is admitted when it carries a DOI and either OpenAlex reports it open access, or
its class is one whose venues are free by construction (a preprint server). Nothing else: no ranking by
citations, no topic judgement, no hand-picking. The point of the pilot is to find out whether a corpus of
genuinely obtainable sources clears an 0.80 floor, and choosing the ones most likely to be obtainable is
the experiment rather than a thumb on the scale — stated so a reader can discount it.

**Why a cap, and why round-robin.** 107 candidates qualify and acquiring all of them is a lot of requests
against publishers who did not ask for them, so the cap is a politeness limit. It is filled **round-robin
across classes** rather than by sorted key: sorting by key first admitted 28 journal articles and no
preprints at all, and a single-class corpus exercises neither invariant 6 nor any verdict rule that weighs
by class — which is one of the three reasons this field was chosen. Deterministic either way, so the same
run gives the same list.

Run from the repository root:

    .venv/bin/python tools/build_pilot_manifest.py pilot-screen-time 28

It writes `projects/<name>/manifest.tsv` and prints what it selected and what it left out.
"""

from __future__ import annotations

import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from claimstone.store import Store  # noqa: E402

# Classes whose venues are free by construction: a preprint is on a server that serves it.
FREE_BY_CONSTRUCTION = frozenset({"WP"})


def main(project_name: str = "pilot-screen-time", cap: int = 28) -> int:
    store = Store(project_name)
    candidates = list(store.latest_by("candidates.jsonl", "candidate_key").values())
    if not candidates:
        print(f"no candidates in store/{project_name}/ — run `claimstone discover` first.")
        print("Nothing is derived. This is not the same as deriving an empty list.")
        return 1

    admitted = []
    left_out: collections.Counter[str] = collections.Counter()
    for row in sorted(candidates, key=lambda r: str(r.get("candidate_key"))):
        klass = str(row.get("source_class") or "")
        if not klass:
            left_out["no class: acquire would refuse it"] += 1
            continue
        if not row.get("doi"):
            left_out["no DOI: nothing to resolve an open copy from"] += 1
            continue
        if not (row.get("is_oa") or klass in FREE_BY_CONSTRUCTION):
            left_out["not reported open access"] += 1
            continue
        admitted.append(row)

    # Round-robin across the classes present, so the cap does not silently produce a single-class corpus.
    queues: dict[str, list[dict]] = {}
    for row in admitted:
        queues.setdefault(str(row["source_class"]), []).append(row)
    chosen: list[dict] = []
    while len(chosen) < cap and any(queues.values()):
        for klass in sorted(queues):
            if len(chosen) >= cap:
                break
            if queues[klass]:
                chosen.append(queues[klass].pop(0))
    if len(admitted) > len(chosen):
        left_out[f"beyond the politeness cap of {cap}"] = len(admitted) - len(chosen)

    path = pathlib.Path("projects") / project_name / "manifest.tsv"
    lines = ["source_id\tclass\tformat\turl\ttitle"]
    per_class: collections.Counter[str] = collections.Counter()
    for row in chosen:
        klass = str(row["source_class"])
        per_class[klass] += 1
        # A stable id from the class and its position, so the same derivation gives the same ids and a
        # round-over-round figure keeps its meaning.
        source_id = f"{klass}{per_class[klass]:03d}"
        title = " ".join(str(row.get("title") or "").split()).replace("\t", " ")
        lines.append(f"{source_id}\t{klass}\tpdf\thttps://doi.org/{row['doi']}\t{title}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"{project_name}: {len(chosen)} sources written to {path}")
    for klass, n in sorted(per_class.items()):
        print(f"  {klass:8s} {n}")
    print(f"\n  from {len(candidates)} candidates; {len(admitted)} met the rule")
    for reason, n in left_out.most_common():
        print(f"    {n:>4} left out — {reason}")
    print()
    print("  The rule admits a candidate with a DOI that OpenAlex reports open access, or whose class is")
    print("  free by construction. Choosing obtainable sources is the experiment — whether such a corpus")
    print("  clears an 0.80 floor — and not a thumb on the scale, but a reader should discount it knowingly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*(sys.argv[1:3] and [sys.argv[1], int(sys.argv[2])] or [])))
