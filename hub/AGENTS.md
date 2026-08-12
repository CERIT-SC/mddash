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
- **Shared status-page chrome lives in `ui/src/components/Hero.tsx`** (`PageHero`, `StatusIcon`, `HeroHeading`, `WaitHint`, `DetailsLog`, `LogEntry`, `SupportNote`, `START_HINT`): home, spawn_pending, stop_pending, and not_running all render the same hero structure from it. Never inline this markup in a page — duplicated hero chrome is forbidden.
- **`not_running` is a dispatcher, not the stopped-server page**: `/hub/home` owns the stopped state (icon + H1 + Start my server + caption). `not_running.tsx` client-side redirects to `${baseUrl}home` (`window.location.replace`) unless the hub hands it a state home can't model: `failed=true` (error icon + hub failure message + Retry) or `implicit_spawn_seconds > 0` (auto-restart countdown). The hub's Python handlers always render `not_running.html` for `/user/:name` with no server — the redirect lives in our template, no upstream override.

## Non-Obvious Gotchas

- **Design-system compliance is mandatory** (same rule as `landing/`): use `@e-infra/design-system` components/tokens; never raw hex or generic Tailwind colors.
- **Entry filenames are load-bearing** — renaming `spawn_pending.html` breaks the hub.
- **Dev vs prod templates**: un-replaced upstream templates (`page.html`, `accept-share.html`) fall back to stock — they are unreachable in MDDash (default servers only, no sharing).
- **`egiauthenticator` short name** in `config.edc.yaml` resolves through the package's `jupyterhub.authenticators` entry point — it must stay installed in the image.
- The hub pod runs as **UID 1000** (z2jh default `containerSecurityContext`); `pip install` in the Dockerfile therefore runs under an explicit `USER root` before the final `USER 1000`.
