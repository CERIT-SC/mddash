# JupyterHub UI Redesign: e-INFRA Design System + In-Repo Hub Image

Date: 2026-07-29
Status: Approved

## Context

The JupyterHub UI is currently skinned with two Jinja overrides (`helm/charts/mddash/files/hub-templates/page.html`, `login.html`) — full copies of the upstream JupyterHub 5.3.0 templates with inline CSS hacks layered on top. They are shipped via a hand-created ConfigMap (`make -C helm hub-templates`), mounted at `/opt/jupyterhub/custom-templates`, enabled through `c.JupyterHub.template_paths`. Everything else (home, pending, token, admin, errors) is stock Bootstrap JupyterHub.

Goals:

- Make every user-visible JupyterHub page consistent with the landing page, which uses `@e-infra/design-system@0.1.8` (React 19 + Tailwind v4).
- Replace the template-fork + hand-ConfigMap mechanism with a maintainable, versionable pipeline.
- Own the hub image in-repo (built, tagged, and deployed like every other MDDash image), dropping the external `eginotebooks/hub` dependency while keeping the custom image's one feature we need: the `/hub/jwt_login` endpoint (EGI Check-in JWT login, used by `scripts/jwt_*.py`).

Key discovery: `eginotebooks/hub` is itself `FROM quay.io/jupyterhub/k8s-hub:4.4.0` + `pip install egi-notebooks-hub` ([their Dockerfile](https://github.com/EGI-Federation/egi-notebooks-hub/blob/main/Dockerfile)). `/jwt_login` is registered by the `EGICheckinAuthenticator` pip-package class via JupyterHub's standard `Authenticator.get_handlers()` extension point ([source](https://github.com/EGI-Federation/egi-notebooks-hub/blob/main/egi_notebooks_hub/egiauthenticator.py)) — it is a package feature, not an image feature. We can keep the authenticator while owning the image.

Inspiration: https://github.com/CERIT-SC/jh-frontend (colleagues' repo) — Vite multi-page React build + `@e-infra/design-system`, Jinja-injected `window.appConfig`, JupyterHub REST API + SSE progress from the browser, ConfigMap delivery. We adopt the pattern (minus their ConfigMap delivery and spawn-form/multi-server machinery, which we don't need) and readapt delivery to a baked-in image.

Constraints:

- MDDash users have exactly one (default) server. No spawn options form, no named servers. `singleuser.defaultUrl` is `/dash`.
- All containers run as non-root (UID 1000) for e-INFRA compliance.
- Never edit `helm/charts/mddash/values.yaml` (generated from `.tmpl`).
- `ENV` build/deploy conventions (`dev` tag vs SemVer) apply to the new image like all other images.

## Decision

Full-page replacement of every JupyterHub-template-driven page with a Vite multi-page React app using the e-INFRA design system, baked into a new in-repo `mddash-hub` image (`FROM quay.io/jupyterhub/k8s-hub:4.4.0`), with the EGI authenticator pip package retained for `/jwt_login` support. z2jh chart dependency 4.2.0 → 4.4.0 (JupyterHub 5.3.x → 5.5.x). ConfigMaps, the `hub-templates` Makefile target, and both template forks are deleted.

## References (authoritative sources for implementation)

- **Upstream stock templates (JH 5.5.x)**: https://github.com/jupyterhub/jupyterhub/tree/5.5.0/share/jupyterhub/templates — the implementing agent MUST read the corresponding upstream template before building each page and cover everything it renders (blocks, forms, hidden inputs, JS behavior, template variables); it defines the functional contract of each page.
- **JupyterHub template context documentation**: https://jupyterhub.readthedocs.io/en/stable/reference/templates.html — which variables each template receives.
- **jh-frontend reference implementations**: https://github.com/CERIT-SC/jh-frontend — REST API client conventions (`src/api/JupyterHubAPI.ts`), SSE progress hook (`src/hooks/useSpawnProgress.ts`), typed `appConfig` (`src/types/appConfig.ts`).
- **EGI authenticator (JWT login)**: https://github.com/EGI-Federation/egi-notebooks-hub/blob/main/egi_notebooks_hub/egiauthenticator.py and https://github.com/EGI-Federation/egi-notebooks-hub/blob/main/Dockerfile.
- **Hub REST API reference**: https://jupyterhub.readthedocs.io/en/stable/reference/rest-api.html.

## Architecture

### New `hub/` directory

The hub becomes a first-class in-repo service, mirroring the `dashboard/` layout (`dashboard/api`, `dashboard/ui`, …):

- `hub/Dockerfile` — the `mddash-hub` image (see below).
- `hub/ui/` — the custom JupyterHub UI package (Vite + React).
- Future hub-side Python (custom authenticator glue, extra handlers) also lives under `hub/` — this design doesn't add any, but the layout reserves the place for it.

### `hub/ui/` package

Mirrors `landing/` conventions (pnpm, `tsc -b && vite build`, prettier + tailwind plugin). **Multi-page** Vite build — one HTML entry per JupyterHub template, not an SPA:

| Entry (= upstream template name) | Function |
|---|---|
| `login.html` | DS card, "Sign in with {{ login_service }}" (OAuth-only; no password form) |
| `home.html` | single-server card: running → open + stop; stopped → start |
| `spawn.html` | no options form → auto-submitting start page with status |
| `spawn_pending.html` | progress page driven by SSE |
| `stop_pending.html` | stop progress page |
| `not_running.html` | server-not-running page with start action |
| `token.html` | API token list / create / revoke |
| `admin.html` | users table (server status, last activity), start/stop user servers, add/delete user |
| `oauth.html` | OAuth consent page |
| `logout.html` | logout confirmation |
| `error.html` | generic error (status code/message) |
| `404.html` | not found |

Entry filenames must match upstream template names exactly (`spawn_pending.html`, `stop_pending.html`, `not_running.html` — JupyterHub looks templates up by exact filename in `template_paths`).

Before implementing any page, read its upstream template (see References) and enumerate what it renders — every form field, JS behavior, and template variable with a functional purpose must have a DS equivalent in our page; purely presentational Bootstrap scaffolding is dropped.

Upstream templates intentionally **not** replaced: `page.html` (base; becomes unused once everything above is replaced), `accept-share.html` (server sharing is unreachable in our deployment — servers are default-only), `shutdown.html` if present. These fall back to stock, which is acceptable because they are unreachable or admin-internal.

Admin rebuild scope (explicit): users table, per-user server start/stop, add user, delete user, user admin flag toggle. Group/role editing and named-server management from the stock admin UI are intentionally omitted.

### Integration contract

- Each entry HTML contains `<div id="root">` and an inline `<script>window.appConfig = { …Jinja-rendered values… }</script>` block authored in the Vite entry HTML source. Vite preserves inline scripts in entry HTML verbatim; if minification ever mangles the Jinja braces, a tiny post-build injection step is the fallback (verified at implementation time).
- JupyterHub renders the built HTML as Jinja templates (same `template_paths` mechanism as today), injecting per-request values: `base_url`, `user.name`, `xsrf_token`, `login_service`, `authenticator_login_url`, `progress_url`, `status_code`/`status_message`, `admin_access`, `announcement`, etc. Exactly the template context each upstream template already receives.
- The React pages talk to the Hub REST API (`/hub/api/...`) directly: start/stop server, token CRUD, admin operations; `X-XSRFToken` header from `appConfig.xsrf` (fallback: read the `_xsrf` cookie). Spawn/stop progress via `EventSource` on `appConfig.progressUrl` with reconnect/backoff (ported from jh-frontend's `useSpawnProgress`/`JupyterHubAPI`, adapted to fetch — no axios dependency).
- Assets: Vite `base` is set to `/hub/static/hub-ui/` so hashed JS/CSS/font URLs in the built HTML need no Jinja. Asset files land in the image's static dir (served by the hub at `/hub/static/...`).
- CSP `<meta>` on every entry (mirroring jh-frontend): `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'`. `unsafe-inline` for scripts is required by the `appConfig` injection.
- Dark mode: `.dark` class toggle per the design-system skill; default follows `prefers-color-scheme`, toggle control in the header of authenticated pages.
- `window.appConfig` gets TypeScript types per page (ported + trimmed from jh-frontend's `src/types/appConfig.ts`). Dev mode: a `dev-setup.ts` module mocks `window.appConfig` when `import.meta.env.DEV`, so each page runs standalone under `vite dev`.

### New `hub/` image (`mddash-hub`)

Multi-stage Dockerfile:

1. Build stage: pnpm install + `vite build` of `hub/ui`.
2. Runtime stage: `FROM quay.io/jupyterhub/k8s-hub:4.4.0`:
   - `pip install --no-cache-dir egi-notebooks-hub==<pinned>` (brings `EGICheckinAuthenticator` with `/jwt_login` and `/token_revoke` handlers; version pinned; resolve the current version from `eginotebooks/hub:sha-4ffff9e` during implementation).
   - `COPY` built entry HTML → `/opt/jupyterhub/custom-templates/` (the exact path already referenced by `c.JupyterHub.template_paths` in `values.yaml.tmpl` — no chart config change needed for templates).
   - `COPY` built assets → `/usr/local/share/jupyterhub/static/hub-ui/`.
   - Final `USER 1000` (e-INFRA non-root compliance).

The authenticator value `egiauthenticator` in `config.edc.yaml` keeps working (this string resolves against the same package layout as in EGI's image); verification step confirms `/hub/jwt_login` responds. Fallback if resolution differs: set the full class path `egi_notebooks_hub.egiauthenticator.EGICheckinAuthenticator`.

The image is built, tagged (`dev` / SemVer), and pushed by the same CI pipeline as the other service images; `values.yaml.tmpl` switches `hub.image` to `{{ $registry }}/{{ $cfg.hub.image }}:{{ $imageTag }}` following the existing image wiring used by the sidecar images.

### Chart / repo deletions & changes

- Delete `helm/charts/mddash/files/hub-templates/` (`page.html` + `login.html` forks).
- Delete the `hub-templates` target in `helm/Makefile` and its uses in `install`/`upgrade`.
- Remove the `custom-templates` `extraVolumes`/`extraVolumeMounts` wiring in `helm/charts/mddash/values.yaml.tmpl`; keep the `customTemplates` extraConfig (path now image-contained).
- z2jh chart dependency `jupyterhub` 4.2.0 → 4.4.0 in `helm/charts/mddash/Chart.yaml`; review the z2jh/JupyterHub changelogs for in-between breaking changes (hub RBAC, config renames, KubeSpawner changes) as an explicit plan task.
- `hub.image` in `values.yaml.tmpl`: from `eginotebooks/hub:sha-4ffff9e` to the registry image with the standard `ENV`-driven tag. EGI's image also copies branding statics we don't use — dropped.
- Add `mddash-hub` to the image build wiring (Makefile/CI) used by the other services.

## Data flow (per page type)

- Login (anonymous): entry renders `window.appConfig = { loginService, loginUrl (authenticator_login_url), announcement }`; button navigates to `loginUrl`.
- Spawn pending: `appConfig = { userName, progressUrl, xsrf }`; `EventSource(progressUrl)`; on `ready`, redirect to the server URL (which lands on `/dash` per `defaultUrl`).
- Home: `appConfig = { userName, xsrf, serverUrl }` + `GET /hub/api/user` for live state; start via `POST /hub/api/users/{name}/server`, stop via `DELETE`.
- Token: `appConfig = { xsrf }`; list/create/revoke via `/hub/api/tokens` (+ `POST /hub/api/users/{name}/tokens`).
- Admin (`appConfig.adminAccess` gated): users via `GET /hub/api/users`; server actions via per-user server endpoints; add/delete user via `POST/DELETE /hub/api/users/{name}`.

## Error handling

- Hub API failures surface as DS `sonner` toasts with the response's `message` (Hub errors are JSON).
- SSE progress stream failures retry with exponential backoff (bounded), then fall back to polling a plain status message; terminal failure shows a DS error state with a retry action.
- `error.html` consumes `status_code`, `status_message`, `message`, `message_html` from the template context and renders them in a DS alert.
- 401/expired-session edge cases redirect to the login page.

## Testing

- `hub/ui`: `tsc` type-check, prettier/eslint, `vite build` artifact validation (assert every expected entry HTML exists and contains the `appConfig` script) wired into the repo's `make fix` / `make type-check` flows the same way `landing/` is.
- Dev harness: `dev-setup.ts` mocks `appConfig` per page for `vite dev`.
- Chart: `make validate-charts` must pass after the `values.yaml.tmpl` changes.
- Integration (manual, dev deployment): full login → spawn → dashboard flow; stop/restart; token page CRUD; admin actions; error page (force 404/500); dark mode.
- JWT acceptance: `scripts/jwt_spawn.py`, `scripts/jwt_create_experiment.py`, `scripts/jwt_wait_api.py` all succeed against the dev deployment with the new image (they exercise `/hub/jwt_login`).
- Repo gates before done: `make fix`, `make type-check`, `make test`, `make validate-charts`.

## Risks / open items resolved at implementation time

1. **Vite inline-script preservation**: verify the `appConfig` Jinja block survives `vite build`; fallback = post-build injection script.
2. **JH 5.3 → 5.5 + z2jh 4.2 → 4.4 migration**: changelog pass; the template context variables we rely on (`progress_url`, `authenticator_login_url`, `xsrf_token`) are stable across these versions (used by jh-frontend in production), but the pre-spawn hook and RBAC config must be re-verified.
3. **`egiauthenticator` short-name resolution**: confirm it resolves in our image exactly as in EGI's; otherwise switch `config.edc.yaml` to the full dotted class path.
4. **`egi-notebooks-hub` version pin**: identify the version inside `eginotebooks/hub:sha-4ffff9e` (inspect the running dev hub or the image manifest) and pin it in the Dockerfile.
5. **Admin page rebuild** is the largest new surface; it is admin-only and covered by manual integration testing against the dev deployment.

## Out of scope

- Applying the design system to the main dashboard (`dashboard/ui`) — separate effort.
- Spawn options form (image/resource selection) — MDDash has a single fixed singleuser environment.
- Named servers.
- Reimplementing the JWT login handler — the EGI pip package is kept.

## Docs to update

- Root `AGENTS.md`: hub UI section replaces any reference to the ConfigMap template flow; add the `hub/` service (image + `hub/ui/`) to the architecture description.
- `helm/charts/mddash/AGENTS.md`: remove `hub-templates` ConfigMap references after the mechanism is deleted.
