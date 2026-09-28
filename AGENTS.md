# AGENTS.md

**The instructions are in `CLAUDE.md`. Read it before anything else, and follow it exactly.**

This file exists because agents look for this name, and it deliberately does not restate what `CLAUDE.md`
says. Two places naming the same rule are two places to disagree — the reason this repository pins
`cli.BACKENDS` against `runners.available()` with a test, and the reason a copy of the invariants here
would drift from the ones that are enforced.

What is here is what `CLAUDE.md` does not cover: where to start reading, and what this machine needs.

## Read in this order

`docs/README.md` is the map — which file answers which question — if you would rather navigate than follow
a list.

1. **`CLAUDE.md`** — the seven invariants and the working conventions. Non-negotiable, and violating any
   of them silently destroys the value of everything downstream.
2. **`README.md`** — what this is, the six stages, and the current status. Two minutes.
3. **`docs/GUIDE.md`** — a whole round stage by stage, with what each number means and which commands
   re-judge what is already on disk without touching the network. Read this before running anything.
4. **`docs/HANDOFF.md`** — what is running, what is pending, and the decisions that are a person's.
5. **`docs/DESIGN_DECISIONS.md`** — 50 decisions, each with the measurement that decided it. It is 2,000
   lines and not meant to be read cold: `HANDOFF.md` names the decisions that matter for what happens next.
   **Do not relitigate a decision from first principles** — find its entry, and argue with the measurement.
6. **`docs/contracts/`** — one file per ledger, describing every field. Read the one for the ledger you
   are about to write.
7. **`docs/superpowers/specs/`** — one design per stage, each marked implemented or not.

## What this machine needs

- **`.env`** holds `CLAIMSTONE_CONTACT_EMAIL` and `OLLAMA_API_KEY`. It is gitignored and already present.
  Every scholarly API this project calls requires a contact address and the code refuses to guess one, so
  a command that makes requests fails without it.
- **`.venv/bin/claimstone`** is the CLI on the host. `./claimstone.sh <command>` is the same CLI inside the
  container set, which is what `normalize` needs — GROBID is on an internal network with no published
  port, so the host cannot reach it. The script builds the image first, because the image carries the code
  and `compose.yaml` mounts only `store/` and `projects/` (D42).
- **`store/`** holds fetched bytes and append-only ledgers, gitignored, and **not reproducible
  without re-fetching**. It is the record of every request this project has made. Do not delete it, and do
  not rewrite a ledger — they are append-only and `Store.read` is what makes a crash resumable.
- Run `.venv/bin/pytest -q` (886 passing) and `.venv/bin/claimstone validate --all-projects` before and
  after any change.
- `.venv/bin/python tools/check_instrument_versions.py` **must exit 0**. It refuses to pass when an
  instrument's version changed and `DESIGN_DECISIONS.md` does not say what changed. That refusal is the
  feature.

## Two things to be careful about

**Network requests leave this repository and are recorded forever.** `acquire` and `discover` make real
requests to publishers and scholarly APIs. Honour `robots.txt`, honour the per-domain failure budget, and
re-request a terminal failure only under a named `--campaign`. Ask the operator before a sweep of any size.

**`codex-cli` is one of this project's own model backends.** If you are Codex, you may be asked to drive a
lane that runs `codex exec`. That is fine and it is not recursion — the boundary is a JSONL file, not a
call — but record `harness_version` honestly and do not assume a result you produced interactively is
comparable to one from the batch path.
