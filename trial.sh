#!/usr/bin/env bash
# Local Docker Compose trial: parser, read-only portal and approved-work scheduler.
set -euo pipefail
cd "$(dirname "$0")"

case "${1:-up}" in
  up)
    if [[ ! -f .env ]]; then
      echo "no .env — set CLAIMSTONE_CONTACT_EMAIL first" >&2
      exit 2
    fi
    revision="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
    if [[ "$revision" != unknown ]] && ! { git diff --quiet && git diff --cached --quiet; } 2>/dev/null; then
      revision="${revision}-dirty"
    fi
    export CLAIMSTONE_CODE_REVISION="$revision"
    docker compose --profile portal --profile trial up -d --build --wait grobid api web scheduler
    echo "Claimstone trial: http://127.0.0.1:${CLAIMSTONE_PORTAL_PORT:-8788}/"
    echo "The scheduler executes only already authorized operations for alembic-s4-lungo."
    ;;
  status)
    docker compose --profile portal --profile trial ps
    ;;
  down)
    docker compose --profile trial rm --stop --force scheduler
    echo "Trial scheduler stopped; portal and GROBID were left running."
    ;;
  *)
    echo "usage: ./trial.sh [up|status|down]" >&2
    exit 2
    ;;
esac
