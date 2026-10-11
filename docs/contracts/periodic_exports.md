# Packaged cumulative dossier export

Only a `READY_FOR_HUMAN_READING` periodic dossier with a current, persisted
`finalized_dossier_id` may be packaged. `scheduler periodic-export PROJECT
SCHEDULE_ID --dossier-id ID` and the authenticated control route both require
that exact ID. An unfinished or stale dossier is refused. Packaging performs
no research request, model call, purchase or verdict action.

The exporter holds the project writer lock while it freezes the complete
newline-terminated prefix of each evidence ledger. It reconstructs a
temporary store from those bytes and recomputes the cumulative dossier. The
content-addressed ID hashes the schedule and dossier IDs, protocol/registry
digests, instrument versions and all prefix hashes. Human signatures, if
present, are in the frozen dossier and change the package identity. The
export ledger `periodic_exports.jsonl` is append-only bookkeeping and is
excluded from the frozen evidence, so repeating the same export is
idempotent. A crash after the directory was written but before the ledger
append is repaired by repeating the create command.

`store/<project>/periodic_exports/<export_id>/` contains `manifest.json`,
`dossier.json`, `questions.csv` and `report.md`. No PDF or raw source bytes
are included. The manifest records the frozen prefix lengths/hashes, output
hashes, the actor and creation time. Its byte hash is recorded in the
append-only export ledger. The browser downloads those four files
as a ZIP. `scheduler periodic-export-verify PROJECT EXPORT_ID` or the control
verify route checks that live ledgers still begin with the frozen prefixes,
recomputes the dossier from them under the current instruments and protocol,
and compares every output. Later append-only evidence does not invalidate an
old package; rewritten history or altered outputs do. A later dossier may
make an earlier package outdated for current reading without making its
historical contents unverifiable.
