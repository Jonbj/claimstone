# Contributing

## The one rule that is not negotiable

**No claim enters the evidence base without a verbatim quote that is verified, in code, to
be an exact substring of the source text it is attributed to.** Every number and every
inequality appearing in a claim must also appear in that quote.

A pull request that weakens, bypasses or makes optional this gate will be declined,
however convenient the output looks. The gate is the reason the project exists; without it
this is a plausible-sounding pile.

## Three states that must stay distinct

`CONTRADICTED`, `UNANSWERED_IN_LITERATURE` and `NEVER_ASKED` are different answers.
Collapsing them — reporting "no evidence found" as "no effect" — is the error this project
is built to prevent. Similarly, a round that could not obtain enough of what it found
reports `INSUFFICIENT_ACQUISITION` and produces no verdicts; that path must not be made
overridable by a flag.

## Things that belong in a project's config, not in the code

Topics, questions and admissible source classes are input data. If something domain
specific is creeping into `claimstone/`, it belongs in a project directory instead. The
test of whether the engine is still general: a second project in an unrelated field must
be expressible without touching the package.

## Adding a question to a registry

A dated registry bump, never a silent insert — otherwise every round-over-round figure and
every multiplicity correction loses its meaning.

## Acquisition

Respect `robots.txt`. Honour the per-domain failure budget: a host that returned 403 is not
re-requested outside a named campaign. Never add a route through a shadow library; the
excluded hosts list is deliberate.

## Statistics

Vote counting is not a synthesis method. Pooling happens across a file boundary in R, and
publication-bias correction is not optional.
