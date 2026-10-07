# Local Docker Compose trial

This trial runs the current portal, API, GROBID and one scheduler worker on this
machine. The only published listener is `127.0.0.1:8788`; it is for local use.
The worker reads the append-only operation ledger for `alembic-s4-lungo` and runs
only operations that were already authorized. Starting the stack does not plan
or authorize discovery, acquisition, model calls, purchases or verdicts.

```bash
./trial.sh up       # build and wait for all four services
./trial.sh status   # container status
./trial.sh down     # stop the worker; leave portal and GROBID running
```

Open <http://127.0.0.1:8788/>. The read-only API is proxied under `/api/v1/`;
`/api/v1/meta` and `/api/v1/projects` are useful smoke checks. The current L02
flow is bound to round `s4-l02-repository-copies-2026-10-06-v2`. Its scheduler
preview can be checked inside the container:

```bash
docker compose --profile trial exec -T scheduler claimstone scheduler-preview \
  projects/alembic-s4-lungo \
  ec6025eff94d39c25429eccc072decdeda5c2aa3ae59330abed12cb42e987700 \
  --store store
```

The preview currently reports zero candidates and `PREVIEW_ONLY`. This is a
real running stack, but it is not yet an end-to-end automated research run:
controlled candidate intake, authenticated portal commands and human decisions
are still pending. A new network campaign requires a frozen plan and the
operator's authorization before it can run. The current portal API is read-only.

Before moving this stack to a VM, complete the portal control API and its
authentication, run at least one bounded flow through its stages locally, and
exercise the operator decisions in the web interface. Then prepare VM-specific
secrets, backups of `store/`, HTTPS and authenticated access. Do not expose this
local read-only portal or the current control plane directly on a public port.

The legacy `alembic-s4` project's `manifest.tsv` is a local symlink into the
separate Alembic repository. In this Compose trial that target is absent, so
the API reports a `ConfigError` for that project while the other projects and
the L02 flow remain available. A portable project manifest must replace that
machine-specific dependency before migrating that project to a VM.
