#!/usr/bin/env python
"""Build one `extract`-lane batch for H02 by hand, so there are records to look at.

**This is not stage 4 and does not pretend to be.** D18 says stop specifying: three questions stay
blocked until real extraction records exist — what counts as an independent study, what magnitude is
material per question, and whether the gate's whole-record rejection is affordable — and none of them
is answerable from a document. So this script builds the smallest thing that produces those records.

Two parts of it are deliberately hand-made and will be replaced:

**Which chunks.** A keyword screen, listed below. Stage 4's rule for choosing chunks per question is
unwritten, and a screen that counts the word "sentiment" is not a candidate for it. What the screen
is good enough for is putting real passages about H02 in front of a model.

**The prompt.** One question per call, not the whole registry. That is the narrow-window shape D4
argues for, and with one question the instructions can be specific enough to argue with.

Run it, then drain with:

    .venv/bin/claimstone model-run projects/alembic-s4 extract --batch <name> \\
        --backend claude-cli --model claude-opus-5 --limit 2

`--limit` matters: every call spends real quota. Start at 2 and read them.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from claimstone import model_call  # noqa: E402
from claimstone.config import load_project  # noqa: E402
from claimstone.store import Store  # noqa: E402

QUESTION_ID = "H02"

# The hand screen. Counted case-folded over a chunk's text; the highest scores are taken.
TERMS = ("sentiment", "news", "abnormal return", "predict", "drift", "incremental")

# One claim per row, and the quote is the row's reason to exist. `additionalProperties: false` is
# what stops a model adding a confidence score nobody asked for and nobody would know how to weigh.
#
# There is no `maxItems`, and there was. The first drain of this batch put `maxItems: 8` on it and
# threw away a whole record for holding **nine** claims whose nine quotes were every one an exact
# substring of the chunk. A cap on item count is a cost bound dressed as a shape, and the cost bound
# already exists and is honest about itself: `max_output_tokens` is inside `call_id`, so raising it is
# a different call. What stops a model padding the array is the quote gate, which is the defence that
# actually reads what was written. See D22.
SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["question_id", "claim", "evidence_quote", "stance"],
        "properties": {
            "question_id": {"type": "string", "enum": [QUESTION_ID]},
            "claim": {"type": "string"},
            "evidence_quote": {"type": "string"},
            "stance": {"type": "string", "enum": ["SUPPORTS", "CONTRADICTS", "QUALIFIES"]},
        },
    },
}


def system_prompt(question_text: str) -> str:
    """The stable prefix. Identical for every call in this batch, which is what makes it cacheable.

    The last paragraph is the one that matters. A model asked "does this passage support the claim"
    will find a way to say yes, and an empty answer has to be as easy to give as a full one — the
    whole project exists because "we found no evidence" and "there is no effect" are different
    sentences.
    """
    return f"""You extract claims from one passage of one document. You judge nothing beyond what
the passage says.

The question, verbatim from a frozen registry:

  {QUESTION_ID}: {question_text}

Return a JSON array. Each element is one claim the passage makes that bears on {QUESTION_ID}:

  question_id      always "{QUESTION_ID}"
  claim            one sentence, in your words, stating what this passage asserts
  evidence_quote   a span copied EXACTLY from the passage, character for character, that
                   contains the assertion. Do not normalise spacing, fix typography, join
                   lines, or trim inside the span.
  stance           SUPPORTS, CONTRADICTS, or QUALIFIES with respect to {QUESTION_ID}

Two hard rules. Every number, percentage, t-statistic and inequality that appears in your `claim`
must also appear inside your `evidence_quote` — a claim carrying a figure its quote does not show is
discarded whole. And the quote must be a literal substring of the passage: it is checked in code,
and a paraphrase is discarded whole.

Return `[]` if the passage does not bear on {QUESTION_ID}. An empty array is a complete, correct and
expected answer, and most passages of most papers deserve one. It means "this passage does not
address the question" — it does not mean "there is no effect", and nothing downstream will read it
that way. Do not stretch a passage about something else into a claim about this question.

Output the JSON array and nothing else. No prose, no code fence, no explanation."""


def main(project_name: str = "alembic-s4", how_many: int = 12) -> int:
    project = load_project(pathlib.Path("projects") / project_name)
    question = next((q for q in project.questions if q.id == QUESTION_ID), None)
    if question is None:
        print(f"{QUESTION_ID} is not in {project_name}'s registry")
        return 1
    if question.kind != "effect":
        print(f"{QUESTION_ID} is kind={question.kind}, not effect — this probe is the effect lane")
        return 1

    store = Store(project.name)
    chunks = list(store.latest_by("chunks.jsonl", "chunk_id").values())
    if not chunks:
        print(f"no chunks in store/{project.name}/ — run `claimstone normalize` first.")
        return 1

    def score(text: str) -> int:
        low = text.lower()
        return sum(low.count(term) for term in TERMS)

    chosen = sorted(chunks, key=lambda c: (-score(c["text"]), c["chunk_id"]))[:how_many]
    system = system_prompt(question.text)

    batch = model_call.batch_name(registry_version=project.registry_version)
    queue = model_call.Queue(store, lane="extract", batch=batch)
    written = queue.write([
        model_call.work_unit(
            lane="extract",
            system=system,
            user=chunk["text"],
            response_schema=SCHEMA,
            # Eight claims of a sentence and a quote each. A cap that cannot hold the answer turns
            # a real answer into TRUNCATED, and a cap far above it is paid for in nothing.
            max_output_tokens=2000,
            registry_version=project.registry_version,
            source_id=chunk["source_id"],
            chunk_id=chunk["chunk_id"],
        )
        for chunk in chosen
    ])

    prompt_chars = sum(len(system) + len(c["text"]) for c in chosen)
    print(f"batch {batch}: {written} calls written to "
          f"store/{project.name}/calls/extract/{batch}/requests.jsonl")
    print(f"  question   {QUESTION_ID} ({question.kind}), registry v{project.registry_version}")
    print(f"  system     {len(system):,} chars, identical on every call")
    print(f"  chunks     {', '.join(c['chunk_id'] for c in chosen)}")
    print(f"  prompts    {prompt_chars:,} chars total ≈ {prompt_chars // 4:,} tokens in, "
          f"{written * 2000:,} capped out")
    print()
    print("  Every call spends real quota. Drain a couple first and read them:")
    print(f"    .venv/bin/claimstone model-run projects/{project.name} extract --batch {batch} \\")
    print("        --backend claude-cli --model claude-opus-5 --limit 2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
