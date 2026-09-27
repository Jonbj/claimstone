#!/usr/bin/env bash
# The documented commands, unchanged, against the container set.
#
# Every document in this repository says `.venv/bin/claimstone <command>`, and on a production node the
# invocation is `docker compose run --rm claimstone <command>`. Rewriting a dozen documents and 559 tests to
# say the second would be the larger change and the worse one, so this is the bridge.
#
#   ./claimstone.sh validate --all-projects
#   ./claimstone.sh normalize projects/alembic-s4
#
# It starts `grobid` only for the commands that need it. `compose run` waits on the healthcheck, so nothing
# here sleeps or polls.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "no .env — copy .env.example and set CLAIMSTONE_CONTACT_EMAIL." >&2
  echo "The APIs require an address and the code refuses to guess one." >&2
  exit 2
fi

# The image carries the code — `compose.yaml` bind-mounts `store/` and `projects/` and nothing else — so a
# working tree that has moved since the last build is not what runs. Measured the hard way: a fix to
# `html_doc.py` was invisible through this script, the run re-appended its previous output, and the figure
# it produced was the old one. The build is cached and costs a second when nothing changed, which is the
# right price for never reasoning about a stale image again.
docker compose build --quiet claimstone

# Only `normalize` reaches GROBID, and only for a PDF whose TEI is not already on disk. Bringing the parser
# up for `report` or `extract --harvest` would spend 3.6 GB and ninety seconds on nothing.
needs_grobid=0
case "${1:-}" in
  normalize) needs_grobid=1 ;;
esac

if [[ $needs_grobid -eq 1 ]]; then
  docker compose up -d --wait grobid
fi

exec docker compose run --rm --no-deps claimstone "$@"
