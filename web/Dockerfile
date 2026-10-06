# The portal frontend: a static SPA served by nginx. No Node process runs in production (spec §1.2).
#
# Built from the REPOSITORY ROOT (`context: .` in compose.yaml) because the TypeScript types are generated
# from `docs/contracts/portal-api.schema.json`, and the build refuses when the committed `api-types.ts`
# no longer matches that schema — a frontend compiled against a different contract than the API serves
# would render fields that are not there.
#
# Both base images are pinned by digest, like GROBID in compose.yaml: a tag can be re-pushed under the
# same name, so the tag being recorded is not the same as the build being recorded (D29).

FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS build
WORKDIR /src/web
# Dependencies first, so editing a component does not reinstall them. `.npmrc` keeps install scripts off.
COPY web/package.json web/package-lock.json web/.npmrc ./
RUN npm ci --ignore-scripts
COPY web/ ./
COPY docs/contracts/portal-api.schema.json /src/docs/contracts/portal-api.schema.json
# The contract check, then the same gates the repository runs: types, tests, build and the CSP check.
RUN cp src/lib/api-types.ts /tmp/api-types.committed.ts \
 && npm run gen:types \
 && cmp -s src/lib/api-types.ts /tmp/api-types.committed.ts \
    || { echo "api-types.ts is stale: run npm run gen:types and commit" >&2; exit 1; } \
 && npm run typecheck \
 && npm test \
 && npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine@sha256:65e3e85dbaed8ba248841d9d58a899b6197106c23cb0ff1a132b7bfe0547e4c0
COPY web/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY web/nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /src/web/dist /usr/share/nginx/html
# nginx-unprivileged listens on 8080 as a non-root user; compose publishes it on 127.0.0.1 only.
EXPOSE 8080
