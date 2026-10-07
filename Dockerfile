# The engine. One stage, because there is nothing to build: the package is pure Python and its three
# dependencies are wheels. A multi-stage build would add a layer to copy artifacts that do not exist.
FROM python:3.13-slim

# `requires-python = ">=3.11"`, pinned to one minor here. The version is part of what produced a figure,
# like the GROBID image and `chunk_version`: a different interpreter is a different instrument, and
# `:slim` without a minor would drift under us between rebuilds.

# Non-root, and the UID is a build argument. The store and the projects are bind-mounted from the host,
# so a container running as root would leave root-owned rows in an append-only ledger the operator then
# could not read with grep — which is the property that ledger format was chosen for.
ARG UID=1000
ARG GID=1000
# The code identity the portal shows: `.git` is not in the image, so the build records the revision it
# was built from (portal.sh passes `git rev-parse HEAD`, suffixed `-dirty` for an unclean tree).
ARG CLAIMSTONE_CODE_REVISION=unknown
ENV CLAIMSTONE_CODE_REVISION=${CLAIMSTONE_CODE_REVISION}
# Where `tools/` and `docs/` live, so the portal's instrument check finds them (the package itself is
# installed into site-packages).
ENV CLAIMSTONE_ROOT=/app
RUN groupadd --gid "${GID}" claimstone \
 && useradd --uid "${UID}" --gid "${GID}" --create-home --shell /usr/sbin/nologin claimstone

WORKDIR /app

# `pdftotext` reads an uploaded copy's first pages for the identity check (B7b, D102), the extraction the
# L02 inspection used (D80). It is the only system package the engine calls.
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils \
 && rm -rf /var/lib/apt/lists/*

# Dependencies before the source, so editing a module does not reinstall numpy.
COPY pyproject.toml README.md ./
COPY claimstone ./claimstone
RUN pip install --no-cache-dir . \
 && pip install --no-cache-dir pytest

# Tests and tools travel with the image: `docker compose run --rm claimstone` must be able to run the
# suite and re-derive a corpus figure, or the production node cannot check itself.
COPY tests ./tests
COPY tools ./tools
COPY docs ./docs

USER claimstone

# Logs go to stdout and stderr and nowhere else: progress on stderr, the summary on stdout. Nothing here
# writes a log file, so the host's log driver is the only collector and there is no second place to look.
ENTRYPOINT ["claimstone"]
CMD ["--help"]
