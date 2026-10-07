# `exports/<export_id>/` — the contract

Written by `claimstone export PROJECT FLOW_ID`; checked by `claimstone export-verify DIR`. An
export is a **verifiable snapshot of one flow**: every ledger frozen at a byte boundary, and
every output file derived from the frozen bytes alone, so a third party can check both that the
ledgers still begin with what was exported and that the outputs still recompute.

Exports are allowed only for flows. A legacy selector must be bound with `flow create` first,
because an export is a claim about a protocol as well as about bytes; a non-CURRENT flow can be
exported, and its binding state is written into the manifest and the report.

## The snapshot

Stage writers share no lock with the exporter (review F5), so the export never assumes a
quiescent file. It takes the one lock that exists — `.flows.lock`, the flow writers' lock —
briefly around the byte snapshot, cuts every covered ledger at its last `\n` (a torn tail is
excluded and recorded), and releases. Covered files: `store/<project>/*.jsonl` and
`store/<project>/calls/**/*.jsonl`. `audits/`, `exports/` and `exports.jsonl` are never
snapshotted: none of them is evidence for the outputs, and the exports ledger is bookkeeping
whose growth must not change an export's identity.

Each prefix records `{path, bytes, rows, sha256}` relative to the project store root.

## Identity

`export_id = sha256(canonical_json({flow_id, selector, prefixes, export_version,
instrument_versions, protocol_sha256, registry_sha256}))`. Canonical JSON is `sort_keys=True,
ensure_ascii=False, separators=(",", ":"), default=str`, and the prefixes are sorted by path.
`protocol_sha256` and `registry_sha256` are the **live** project's at export time.

The same bytes read by a different instrument version or under a changed live protocol are a
different export. Before the 2026-10-06 implementation review the id hashed only the flow,
selector and prefixes, so a re-export after a gate change answered `exists` with outputs the
current code no longer produced.

`created_at` and `created_by` are excluded from the id and from verification, because a
timestamp is not evidence. Exporting the same flow over unchanged ledgers, instruments and
protocol re-derives the same id, prints `exists <export_id>` and writes nothing. In that case the
append to `exports.jsonl` happens only once.

Each ledger prefix is consistent on its own. Prefixes of **different** ledgers are cut one after
another, with no stage writer locked out, so they can straddle a multi-ledger write. A harvest that
appends to `claims.jsonl` and then to `rejections.jsonl` while the snapshot runs is one example.
The export is still exactly recomputable from what it froze. It is not guaranteed to be a moment
the store was ever in. A shared writer lock (review F5, phase P3) is what would close this gap.

## Files

| file | content |
|---|---|
| `manifest.json` | `export_version` (1), the flow's created row, `binding_state`, `selector`, `prefixes`, `torn_tails`, `code_revision`, `code_dirty`, `instrument_versions` (as the portal's admin page lists them), `protocol_sha256`, `registry_sha256`, `created_at`, `created_by` |
| `profiles.json` | `synthesize.verdicts(...)` for the selector, `sort_keys=True, indent=1, default=str` |
| `floor.json` | `admissibility.admit(...)` for the selector |
| `questions.csv` | the portal's question matrix rows, one per registry question |
| `claims.csv` | scoped current claims: `claim_id`, `question_id`, `source_id`, `source_class`, `stance`, `evidence_quote`, `chunk_id`, `generation_sha256`, `html_parser_version`, `jats_parser_version`, `acquisition_sha256`, `licence`, `review_verdict`, `quote_found` |
| `rejections.csv` | scoped current rejections: `claim_id`, `source_id`, `failure`, `detail` |
| `acquisition.csv` | one row per scoped candidate: key, `source_id`, class, counted acquired, `failure_class` (raw stored code), `failure_display` (F19 display text), `provenance`, `licence` |
| `report.md` | binding state, floor panel text and deficit sentences, the question matrix as a table, and the fixed disclosures: no verdict unless signed, `NO_VERIFIED_CLAIM` ≠ `NEVER_ASKED`, the F1 project-wide-reads disclosure, and "no controlled family-wise error rate across N questions" |

CSV rules: the `csv` module, `lineterminator="\n"`, UTF-8, rows sorted by the first column then
the second. No raw bytes, no PDFs, no receipts, nothing from `audits/` ever enters an export.

`quote_found` in `claims.csv` is recomputed at export time — `evidence_quote in chunk text` —
because invariant 1 is a check, not a memory.

## `claimstone export-verify DIR [--projects-dir projects]`

1. Load `manifest.json`.
2. For each prefix, the live file must still exist, be at least `bytes` long, and its first
   `bytes` bytes must hash to `sha256`. Anything else reports `PREFIX_CHANGED <path>`: this is
   what detects rewritten history in an append-only ledger.
3. Rebuild a temporary store from the recorded prefixes, recompute every output file except
   `manifest.json` under the live project, and compare byte-for-byte. A difference reports
   `OUTPUT_DIFFERS <file>`.
4. Exit 0 when everything matches, 5 otherwise, printing one line per problem.

The recomputation reads the **live** project — that is deliberate. Floors and registry come from
the project exactly as every CLI command reads them (review F4: a snapshot never supplies a
value), so an export verifies only while the instruments and the protocol still agree with it.
A `PROJECT_NOT_FOUND` line means the verifier cannot see the project the export names.

After a successful export, one row `{"export_id", "flow_id", "path", "created_at"}` is appended
to `store/<project>/exports.jsonl` under the same `.flows.lock`.

## Copies and the operator (B10, D105)

`export(…, include_copies=True)` adds the held copies of the flow's candidates whose recorded
licence is one of `cc0`, `cc-by`, `cc-by-sa`, `cc-by-nd`, `pd` or `public-domain`. They go under
`copies/`. One copy per candidate: the collapsed acquisition row the floor reads. Every other held
copy is listed in `manifest.copies.excluded` with its reason:
- an unknown licence is excluded;
- a non-commercial or publisher-specific licence is excluded, because whether a use is
  non-commercial is not something this code can know.

The option enters the export identity **only when set**: every export made without it keeps the id
it always had, and `export_version` stays 1. `verify` checks each included copy against its recorded
hash (`COPY_DIFFERS`). No filesystem path appears in the manifest's `copies` section.

An export requested through the control server carries `actor` (the operator id) in its manifest and
in its `exports.jsonl` row. `created_by` keeps its meaning: the OS user of the process.
