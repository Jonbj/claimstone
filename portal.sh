#!/usr/bin/env bash
# The research portal in containers: the read-only API and the nginx-served frontend (D84).
#
#   ./portal.sh                   build if needed, start `api`, `control` and `web`, wait until healthy
#   ./portal.sh down              stop and remove those three containers (GROBID and the store stay)
#   ./portal.sh operator add ID --name "Display name"   record an operator; prompts for the password
#   ./portal.sh operator disable ID
#
# The build is always run, as in claimstone.sh: it is cached and costs seconds when nothing changed, and an
# image older than the working tree is the stale-instrument failure D42 recorded.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "no .env — copy .env.example and set CLAIMSTONE_CONTACT_EMAIL (and UID/GID)." >&2
  exit 2
fi

# The control server's state (operator accounts, markers, admin records) lives here, owner-only.
mkdir -p .claimstone && chmod 700 .claimstone

case "${1:-up}" in
  up) ;;
  down)
    # Not `compose down`: that would also remove GROBID, which belongs to the stages, not the portal.
    exec docker compose --profile portal rm --stop --force web control api
    ;;
  operator)
    # Interactive: the password is read by getpass inside the container, never passed as an argument.
    shift
    exec docker compose --profile portal run --rm --no-deps control operator "$@"
    ;;
  *)
    echo "usage: ./portal.sh [up|down|operator add ID --name NAME|operator disable ID]" >&2
    exit 2
    ;;
esac

# The revision the portal shows in its header. `.git` is not in the image, so it is passed at build time,
# and marked dirty when the tree differs from HEAD: a figure computed by uncommitted code says so.
revision="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
if [[ "$revision" != unknown ]] && ! { git diff --quiet && git diff --cached --quiet; } 2>/dev/null; then
  revision="${revision}-dirty"
fi
export CLAIMSTONE_CODE_REVISION="$revision"

docker compose --profile portal up -d --build --wait api control web

port="${CLAIMSTONE_PORTAL_PORT:-8788}"
echo "claimstone portal — http://127.0.0.1:${port}/  (writes need an operator: ./portal.sh operator add; ./portal.sh down to stop)"
