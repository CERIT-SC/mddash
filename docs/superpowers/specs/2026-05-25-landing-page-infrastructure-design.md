# Landing Page Infrastructure Design

**Date:** 2026-05-25
**Branch:** landing-page

## Goal

Add a public landing page served at `/` on the same domain as the app (e.g. `mddash.dyn.cloud.e-infra.cz`), replacing the default JupyterHub redirect at the root path. The landing page links to the hub at `/hub/`. No authentication required. The page is a minimal React + TypeScript SPA used to validate the deployment pipeline; real content comes later.

---

## Architecture

### Routing

JupyterHub's ingress currently owns the entire domain with `pathType: Prefix /`. A second NGINX ingress resource with `pathType: Exact /` takes priority for the root path only. All other paths (`/hub/`, `/user/`, `/hub/static/`, etc.) continue to route to JupyterHub unchanged.

JupyterHub does not functionally need `/` — it just redirects to `/hub/` when hit directly. Intercepting `/` with the landing page has no impact on hub operation.

The landing page links to the hub via `<a href="/hub/">`.

### Asset Strategy

`vite-plugin-singlefile` inlines all JS and CSS into a single `index.html`. No `/assets/` requests are ever made by the browser, so no additional ingress rules are needed.

**SEO note:** This produces a client-rendered SPA. Acceptable for infrastructure validation. When real content is written, evaluate SSR (e.g. Astro) for production SEO.

---

## Components

### 1. Landing Page App — `landing/`

New directory at repo root, same level as `dashboard/`, `mdrun-api/`, `notebook/`.

```
landing/
  src/
    main.tsx        # React entry point
    App.tsx         # Blank page: reactive counter button + "Go to Hub" link
  index.html
  package.json      # dependencies: vite, react, react-dom, typescript, vite-plugin-singlefile
  tsconfig.json
  vite.config.ts    # vite-plugin-singlefile configured
  Dockerfile
  Caddyfile
  .dockerignore
  Makefile
```

No TanStack, ShadCN, or other heavy dependencies. Minimal React only.

### 2. Dockerfile — `landing/Dockerfile`

Two-stage build: Node build stage → Caddy runtime stage. Mirrors `dashboard/proxy/Dockerfile` for consistency.

```dockerfile
FROM node:24-slim AS build
WORKDIR /app
RUN corepack enable pnpm
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm run build
# dist/ contains a single index.html

FROM caddy:2.10-alpine AS runtime

# Drop privileged port binding — container runs as non-root on port 8080
RUN apk add --no-cache libcap curl && setcap -r /usr/bin/caddy

RUN mkdir -p /config/caddy /data/caddy && \
    chown -R 1000:1000 /config /data

COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile

USER 1000

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8080/health || exit 1

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
```

### 3. Caddyfile — `landing/Caddyfile`

Trivial static file server, no auth, no routing logic. Port 8080 (non-privileged, matching non-root USER 1000):

```
{
    admin off
    auto_https off
}

:8080 {
    handle /health {
        respond "OK" 200
    }

    root * /srv
    encode zstd gzip
    file_server
}
```

### 4. Helm Chart — `helm/charts/mddash/templates/landing-page.yaml`

New `templates/` directory (first templates in this chart). Contains three resources:

- **Deployment** — 1 replica, Caddy container, non-root (UID 1000), image from values, resource limits from values.
- **Service** — ClusterIP on port 80, forwarding to container port 8080, selects landing page pods.
- **Ingress** — same host and TLS configuration as JupyterHub's ingress; `pathType: Exact`, path `/`; same nginx annotations (proxy-body-size, timeouts). Takes priority over JupyterHub's `pathType: Prefix /` for the root path only.

### 5. Helm Values — `helm/charts/mddash/values.yaml.tmpl`

New `landing` section:

```yaml
landing:
  image:
    repository: "{{ $registry }}/{{ $cfg.landing.image }}"
    tag: "{{ $imageTag }}"
    pullPolicy: "{{ if eq $env "dev" }}Always{{ else }}IfNotPresent{{ end }}"
  resources:
    requests:
      cpu: "50m"
      memory: "32Mi"
    limits:
      cpu: "100m"
      memory: "64Mi"
```

### 6. Config Files

Add to `config.yaml`, `config.dev.yaml`, and `config.edc.yaml`:

```yaml
landing:
  image: mddash-landing
```

### 7. Root Makefile

Add `build-landing` and `push-landing` targets; wire into top-level `build` and `push`:

```makefile
build: build-dashboard build-notebook build-mdrun-api build-landing
push:  push-dashboard  push-notebook  push-mdrun-api  push-landing

build-landing: ## Build landing page image
    @$(MAKE) -C landing build ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)

push-landing: ## Build and push landing page image
    @$(MAKE) -C landing push ENV=$(ENV) IMAGE_TAG=$(IMAGE_TAG)
```

`landing/Makefile` mirrors the `mdrun-api/Makefile` pattern: reads image name from config, builds and pushes with the correct tag.

### 8. CI/CD — `.github/workflows/cd.yml`

Two changes:

1. Add `landing` to the `dorny/paths-filter` block:
   ```yaml
   landing:
     - 'landing/**'
   ```

2. Add to the `all_components` JSON matrix:
   ```json
   {"name":"landing","path":"landing","context":"landing"}
   ```

Dev pushes rebuild only when `landing/**` changes. Prod pushes rebuild all components (existing behaviour).

---

## What Is NOT in Scope

- Actual landing page content and design (blank page with test button only)
- SEO optimisation (deferred until real content is written)
- Custom domain for the landing page
- Analytics, tracking, or cookies

---

## Validation Criteria

1. `make build-landing` succeeds locally.
2. Browsing to `/` serves the React page (not a JupyterHub redirect).
3. The counter button increments (proves JS reactivity).
4. Clicking "Go to Hub" navigates to `/hub/` and the hub loads normally.
5. Browsing to `/hub/` directly still works (JupyterHub unaffected).
6. CD pipeline on `dev` push detects changes in `landing/` and builds/pushes `mddash-landing:dev`.
