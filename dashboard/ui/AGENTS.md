# MDDash UI

## Mission

React + TypeScript wizard-driven web interface for creating, configuring, and managing molecular dynamics experiments. The compiled SPA is embedded as static assets in the proxy container image.

## Core Practices

- All fetching/mutations go through TanStack Query hooks in `src/hooks/` (polling via `refetchInterval`). Use the configured `api` instance in `lib/http.ts`, never raw `axios`; call `api.get/post/patch/delete(path).then(r => r.data)` directly (no wrapper functions).
- Manual route tree in `src/router.tsx` with `basepath: BASE_PATH` (no file-based routing).
- Backend returns resources directly — `r.data` is the payload (no envelope); the axios error interceptor builds an `ApiError` from RFC 9457 problem-details responses (`{type, title, detail[, solution]}` with `Content-Type: application/problem+json`). `error.message` is the toast line (`solution ?? detail ?? title`) so `toast.error(error.message)` works unchanged and shows the actionable line when a `solution` is present. `type` is the support-reportable error code. A React `ErrorBoundary` wraps the app root for render-time crashes.

## Non-Obvious Gotchas

- **Runtime config**: `window.MDDASH_CONFIG` is injected by Caddy via `config.js` in production; `DEBUG` is `true` when undefined. `BASE_PATH`/`API_BASE` come from runtime config, not build time (dev defaults `API_BASE` to `/dash/api`).
- **ShadCN + Tailwind v4**: don't `@apply` CSS-var utilities (e.g. `border-border`) unless the `@theme` registration exists. `Select` requires non-empty string values — use `SELECT_NONE = "__none__"` (`util/const.ts`) for "none" options.
- **Theme/FOUC**: initial mode is applied synchronously before first render to prevent FOUC. Sonner reads `ThemeContext` (not `next-themes`).
- **Notifications**: call `sonner` `toast.*()` directly — no context/hook (the old `NotificationContext`/`useNotification()` is removed).
- **Wizard state lives in the URL** (`/$id/wizard?tab=<simulation name>&step=<0-4>`, validated by the route's `validateSearch`); tab `_new` is the create-mode sentinel. Each `.simulation.json` owns its step — the API infers `step`/`status` per manifest (jobs filtered by `simulation_path`); the experiment only inherits its latest setup's step (publishing stays experiment-level). `WizardStepper` is a pure URL-driven shell: tabs wrap the stepper, steps receive `{ experiment, simulation, goToStep }`, and the shell polls `useSimulations` (5 s) instead of the old `/experiments/{id}/step` endpoint + `useExperimentStep` (the endpoint survives as a deprecated shim for stale cached bundles — remove one release later). The Publish step is reachable once any setup finished MD (the experiment-level published/publishing override kept), so a fresher setup never hides a completed one's Publish. `DEBUG` mode shows a "DEBUG: next step" button.
- **MolStar cleanup is manual**: call `plugin.dispose()` and `root.unmount()` on unmount; use `isMountedRef` to guard post-unmount state. Resolve formats via `resolveStructureFormat()`/`resolveCoordsFormat()` (`src/util/molstar-formats.ts`). `loadStructureWithCoordinates` treats both trajectory (PDB, GRO) and topology (PRMTOP, PSF, TOP) formats as structure sources.
