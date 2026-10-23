# Hub image and custom UI

## Mission

The in-repo JupyterHub image (`mddash-hub`) powers MDDash's hub. It combines stock `quay.io/jupyterhub/k8s-hub` with the MDDash-branded interface (`hub/ui/`) baked in. No runtime ConfigMaps are used. It also carries the `egi-notebooks-hub` authenticator package that provides EGI Check-in and the `/hub/jwt_login` endpoint used by `scripts/jwt_*.py`.

## Structure

- `Dockerfile` runs a multi-stage build. Node with pnpm builds `ui/`. The runtime stage is `quay.io/jupyterhub/k8s-hub:4.4.2` with pinned `egi-notebooks-hub` (git commit `4ffff9e`, matching the previously used `eginotebooks/hub` image).
- `ui/` is a Vite, React 19, Tailwind v4, and `@e-infra/design-system` multi-page app. It has one HTML entry per JupyterHub template (`login`, `home`, `spawn`, `spawn_pending`, `stop_pending`, `not_running`, `token`, `admin`, `oauth`, `logout`, `error`, `404`).
- `Makefile` builds and pushes the image (same pattern as `landing/`).

## Patterns

- **One entry per upstream template name.** JupyterHub looks templates up by exact filename in `c.JupyterHub.template_paths` (`/opt/jupyterhub/custom-templates`, set in `values.yaml.tmpl`). Built HTML goes there; built assets go to `/usr/local/share/jupyterhub/static/hub-ui/` (Vite `base: /hub/static/hub-ui/`).
- **`window.appConfig` injection.** Each entry HTML has an inline `<script>` with Jinja `| tojson` expressions that JupyterHub renders per request. It MUST be a plain inline script (no `type=`) so Vite preserves it verbatim. In `vite dev` the script is invalid JS (Jinja braces) and `window.appConfig` stays undefined. Pages fall back to production-realistic defaults from `src/lib/config.ts`.
- **Data flow.** Pages call the Hub REST API (`/hub/api/…`) with the rendered `xsrf` token in the `X-XSRFToken` header; spawn progress uses `EventSource` on `progress_url` with bounded reconnect/backoff (`src/lib/progress.ts`). The OAuth consent page is a plain HTML form POST (the hub consumes form data).
- **Build validation.** `pnpm run build` also runs `scripts/validate-build.mjs`, which asserts all 12 entries exist in `dist/`, carry the appConfig injection, and reference assets only under `/hub/static/hub-ui/`.
- **Page chrome is shared, never inlined.** Status pages compose their hero markup from `ui/src/components/Hero.tsx` and card pages from `IconCard.tsx`. Duplicating that markup in a page is forbidden. Extend the shared components instead.
- **`not_running` is a dispatcher, not the stopped-server page.** The hub's Python handlers always render `not_running.html` for `/user/:name` with no server, so the stopped state can't be a hub route. Our template client-side redirects to `/hub/home` and only renders the two states home can't model (failed spawn, implicit-spawn countdown).
- **`/hub/home?stop` is the dashboard's stop entry point.** The dashboard UI can't call the hub API (the `_xsrf` cookie is path-scoped to `/hub/`, unreadable from `/user/:name/dash/`), so its server-bar button navigates here and the home page auto-triggers the existing stop flow (mirroring the hub's own action-on-GET `/hub/spawn/:name`). Keep the param honored in `ui/src/pages/home.tsx`; the stopping transition routes to `spawn-pending/:name`, which renders `stop_pending.html` while the server stops.

## Non-obvious gotchas

- **Design-system compliance is mandatory** (same rule as `landing/`). Use `@e-infra/design-system` components/tokens; never raw hex or generic Tailwind colors.
- **Entry filenames are load-bearing.** Renaming `spawn_pending.html` breaks the hub.
- **Dev vs prod templates.** Un-replaced upstream templates (`page.html`, `accept-share.html`) fall back to stock. They are unreachable in MDDash (default servers only, no sharing).
- **`egiauthenticator` short name** in `config.edc.yaml` resolves through the package's `jupyterhub.authenticators` entry point. It must stay installed in the image.
- The hub pod runs as **UID 1000** (z2jh default `containerSecurityContext`); `pip install` in the Dockerfile therefore runs under an explicit `USER root` before the final `USER 1000`.
