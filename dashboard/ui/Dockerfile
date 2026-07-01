# UI build image - outputs static files to /dist
# This image is used as a build stage for the proxy container

FROM node:26-slim AS build

WORKDIR /app

RUN npm install -g pnpm@11.9.0 --quiet
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm run build

# Final stage - just the static files for copying
FROM scratch AS export
COPY --from=build /app/dist /dist
