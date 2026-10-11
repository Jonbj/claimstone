# Ephemeral worker liveness

`scheduler worker PROJECT` publishes the key `operations`;
`scheduler auto-worker PROJECT MANDATE_ID` publishes that exact mandate ID.
The sidecar lives at `store/<project>/runtime/workers/<key>.json`, is replaced
atomically every three seconds by a separate heartbeat thread, and is **not**
an evidence ledger. The process holds an advisory lock for its key until exit,
so a second worker for the same mandate refuses to start. A normal exit writes
`STOPPED`; a kill leaves the last heartbeat and becomes `STALE` after 15
seconds. Missing is `NOT_STARTED`; malformed/unreadable is `UNKNOWN`.

`scheduler worker-status PROJECT KEY` and the authenticated project scheduler
index return `{worker_key, state, last_seen_at, phase, age_seconds}`. `phase`
is `IDLE`, `DRIVING` or `STOPPED`. `ALIVE` proves only that a worker process
recently updated its sidecar. `DRIVING` means it is attempting a pass, not
that a request succeeded. The append-only operation, query, acquisition,
model and dossier ledgers remain the authority for completed work. A stopped
or stale sidecar does not repair an interrupted operation. This is a
single-machine deployment signal, not a cross-host lease protocol.
