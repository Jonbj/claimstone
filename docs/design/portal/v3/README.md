# Portal look and feel v3 — "Assay" (D137)

Chosen on 2026-10-18 from three directions (A Assay, B Carta, C Banco). The three `A-*.html` files are
the reference mockups: static, 1280 px, light theme, real figures of a small throwaway project of public
literature. **They show intent, not markup to copy**: the portal keeps its React components, router, i18n,
tests and behaviour; only structure and style change.

## Principles
1. **Identity of the website**: slate and amber, Schibsted Grotesk and IBM Plex Mono (self-hosted).
2. **Amber is the one primary action** on a screen (Authorize, Sign, Plan). Never decoration, never two.
3. **Every state has a word and a symbol**, never colour alone: ● waits for you (amber), ◐ Claimstone acting
   (teal), ✓ done (green), ▲ partial (amber ink), ■ blocked (rose), ○ not started (grey).
4. **Waits / acts / changed** is the first structure of the home screen and the top of every flow screen.
5. **A blocked flow is principled, not broken**: a dark panel stating that no verdict was produced and why,
   with the rate against the floor on a bar with the floor marked, and the recovery actions beside it.
6. **A count is labelled a count.** The signing block says an agent does not sign, lists the five verdicts
   (NEVER_ASKED is signable only on a second, explicit attestation and records that basis — D156), and
   states the profile hash being signed.
7. **Technical detail is collapsed by default** (hashes, ledgers, operation ids); on first view people read
   sentences, not identifiers. Identifiers are monospace, truncated, with the full value on demand.
8. **Light and dark are both first class**; phone width works (16 px gutters, no horizontal page scroll).

## Tokens
Already in `web/src/index.css` (`:root` and `[data-theme="dark"]`): `--background`, `--card`, `--border`,
`--primary` (amber) and the state families `--waits`, `--acting`, `--done`, `--provisional`, `--not-obtained`,
`--contradicts`, `--neutral` (each with `-soft` and `-ink`), `--rail-*`. Use them through the Tailwind names
(`bg-card`, `text-muted-foreground`, `bg-waits-soft text-waits-ink`, …). Do not introduce a raw hex or a
Tailwind palette colour (teal-600, violet-500, …) in a component.

Type: titles 600 weight, tight tracking (`h1` is already set); section labels 12–13 px, uppercase, 0.08 em
tracking, coloured by meaning; body 14–15 px; identifiers `font-mono`.
Shape: cards `rounded-xl border bg-card`, buttons `min-h-11 rounded-lg`, chips are pills.
