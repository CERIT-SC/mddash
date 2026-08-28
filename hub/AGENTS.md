# Hub — JupyterHub image + custom UI

## Mission

The in-repo JupyterHub image (`mddash-hub`) powering MDDash's hub: stock `quay.io/jupyterhub/k8s-hub` plus the MDDash-branded interface (`hub/ui/`) baked in — no runtime ConfigMaps. Also carries the `egi-notebooks-hub` authenticator package that provides EGI Check-in and the `/hub/jwt_login` endpoint used by `scripts/jwt_*.py`.

## Structure

- `Dockerfile` — multi-stage: Node + pnpm builds `ui/`, runtime stage is `quay.io/jupyterhub/k8s-hub:4.4.0` + pinned `egi-notebooks-hub` (git commit `4ffff9e`, matching the previously used `eginotebooks/hub` image).
- `ui/` — Vite + React 19 + Tailwind v4 + `@e-infra/design-system` multi-page app: one HTML entry per JupyterHub template (`login`, `home`, `spawn`, `spawn_pending`, `stop_pending`, `not_running`, `token`, `admin`, `oauth`, `logout`, `error`, `404`).
- `Makefile` — image build/push (same pattern as `landing/`).

## Patterns

- **One entry per upstream template name**: JupyterHub looks templates up by exact filename in `c.JupyterHub.template_paths` (`/opt/jupyterhub/custom-templates`, set in `values.yaml.tmpl`). Built HTML goes there; built assets go to `/usr/local/share/jupyterhub/static/hub-ui/` (Vite `base: /hub/static/hub-ui/`).
- **`window.appConfig` injection**: each entry HTML has an inline `<script>` with Jinja `| tojson` expressions that JupyterHub renders per request. It MUST be a plain inline script (no `type=`) so Vite preserves it verbatim. In `vite dev` the script is invalid JS (Jinja braces) and `window.appConfig` stays undefined — pages fall back to production-realistic defaults from `src/lib/config.ts`.
- **Data flow**: pages call the Hub REST API (`/hub/api/…`) with the rendered `xsrf` token in the `X-XSRFToken` header; spawn progress uses `EventSource` on `progress_url` with bounded reconnect/backoff (`src/lib/progress.ts`). The OAuth consent page is a plain HTML form POST (the hub consumes form data).
- **Build validation**: `pnpm run build` also runs `scripts/validate-build.mjs`, which asserts all 12 entries exist in `dist/`, carry the appConfig injection, and reference assets only under `/hub/static/hub-ui/`.
- **Page chrome is shared, never inlined**: status pages compose their hero markup from `ui/src/components/Hero.tsx` and card pages from `IconCard.tsx`. Duplicating that markup in a page is forbidden — extend the shared components instead.
- **`not_running` is a dispatcher, not the stopped-server page**: the hub's Python handlers always render `not_running.html` for `/user/:name` with no server, so the stopped state can't be a hub route — our template client-side redirects to `/hub/home` and only renders the two states home can't model (failed spawn, implicit-spawn countdown).
- **`/hub/home?stop` is the dashboard's stop entry point**: the dashboard UI can't call the hub API (the `_xsrf` cookie is path-scoped to `/hub/`, unreadable from `/user/:name/dash/`), so its server-bar button navigates here and the home page auto-triggers the existing stop flow (mirroring the hub's own action-on-GET `/hub/spawn/:name`). Keep the param honored in `ui/src/pages/home.tsx`; the stopping transition routes to `spawn-pending/:name`, which renders `stop_pending.html` while the server stops.

## Non-Obvious Gotchas

- **Design-system compliance is mandatory** (same rule as `landing/`): use `@e-infra/design-system` components/tokens; never raw hex or generic Tailwind colors.
- **Entry filenames are load-bearing** — renaming `spawn_pending.html` breaks the hub.
- **Dev vs prod templates**: un-replaced upstream templates (`page.html`, `accept-share.html`) fall back to stock — they are unreachable in MDDash (default servers only, no sharing).
- **`egiauthenticator` short name** in `config.edc.yaml` resolves through the package's `jupyterhub.authenticators` entry point — it must stay installed in the image.
- The hub pod runs as **UID 1000** (z2jh default `containerSecurityContext`); `pip install` in the Dockerfile therefore runs under an explicit `USER root` before the final `USER 1000`.
