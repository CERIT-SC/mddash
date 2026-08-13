# UI build image - outputs static files to /dist
# This image is used as a build stage for the proxy container

FROM node:26-slim AS build

WORKDIR /app

RUN npm install -g pnpm@11.13.0 --quiet
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY dashboard/ui/package.json dashboard/ui/package.json
COPY landing/package.json landing/package.json
COPY hub/ui/package.json hub/ui/package.json
RUN pnpm install --frozen-lockfile --filter dash...

COPY dashboard/ui/ dashboard/ui/
RUN pnpm --filter dash build

# Final stage - just the static files for copying
FROM scratch AS export
COPY --from=build /app/dashboard/ui/dist /dist
