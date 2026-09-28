# Documentation map

Which file answers which question. *In italiano: [README.it.md](README.it.md).*

## Start here

| I want to… | read |
|---|---|
| know what this project is, in two minutes | [`../README.md`](../README.md) |
| run a round and understand what comes out | [`GUIDE.md`](GUIDE.md) |
| know what is running and what is pending right now | [`HANDOFF.md`](HANDOFF.md) |
| work on the code as an agent | [`../CLAUDE.md`](../CLAUDE.md), then [`../AGENTS.md`](../AGENTS.md) |
| argue with an architectural choice | [`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md) — find its entry first |
| write to a ledger, or read one | [`contracts/`](contracts/) — one file per ledger |
| know what a stage was supposed to do | [`superpowers/specs/`](superpowers/specs/) — one design per stage |

## The design record

[`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md) is 44 numbered decisions in ~2,000 lines, each carrying **the
measurement that decided it**. It is not meant to be read front to back.

Its purpose is narrow and worth stating: **so that a choice is not relitigated from first principles.** Most
entries exist because something plausible was tried, measured, and found wrong. Several record a prediction
of mine that the measurement falsified — those are the most useful ones, because they say which instincts
this corpus punishes.

To argue with a decision, find its entry and argue with its measurement. If the measurement no longer holds,
that is a new dated entry, not an edit to the old one: two figures produced under different instruments are
not comparable, and erasing the first hides that.

## The data contracts

One file per ledger, describing every field and why it exists. Read the one for the ledger you are about to
write to — several fields exist to prevent a specific defect and look optional until you know which.

| file | ledger |
|---|---|
| [`contracts/candidates.md`](contracts/candidates.md) | what discovery found, and through which channel |
| [`contracts/acquisitions.md`](contracts/acquisitions.md) | every fetch attempt, its licence, and why it failed |
| [`contracts/normalize.md`](contracts/normalize.md) | documents and chunks |
| [`contracts/claims.md`](contracts/claims.md) | a claim, its quote, and the engine's converted values |
| [`contracts/reviews.md`](contracts/reviews.md) | a second reader's verdict on one claim |
| [`contracts/model_calls.md`](contracts/model_calls.md) | the file boundary every model-using stage crosses |

## The stage designs

[`superpowers/specs/`](superpowers/specs/) holds one design per stage, each marked implemented or not, plus
two that are not stages:

- **the verdict contract** — the five verdict states, why `operational` questions get none, and the two-layer
  split that makes every verdict a person's. Read this before touching stage 5 or 6.
- **the dashboard** — specified, deliberately built last, and not built. Its value needs data in every stage.

A spec says what was intended. The design record says what was measured afterwards, and where they disagree
the record wins.

## Language

The reader-facing documents are in **English and Italian**: this map, the top-level README, and the guide.

Everything else is **English only**: the design record, the data contracts, the stage specs, and the code
comments. That is a deliberate choice, not an omission. Those files change on almost every commit, and two
copies of a rule drift — the copy that drifts is the one that misleads someone. This repository already pins
`cli.BACKENDS` against `runners.available()` with a test for exactly that reason, and three tests written in
one day had to be fixed because they matched the *prose of a comment* rather than the code it described.

So: bilingual where it is stable and read occasionally, one language where it is worked on.
