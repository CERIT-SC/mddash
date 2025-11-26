# UI build image - outputs static files to /dist
# This image is used as a build stage for the proxy container

FROM node:24-slim AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Final stage - just the static files for copying
FROM scratch AS export
COPY --from=build /app/dist /dist
