# Dashboard UI

## Architecture

One-way imports: `app/routes → features → api/shared`. Lower layers never import upper; feature cycles forbidden.

## Features

- A feature owns a product capability, not the page that renders it: notebook lifecycle, simulation manifests, and each implemented wizard step are their own features. Create features only with real behavior — no stubs.
- Cross-feature imports use the feature's `index.ts` (named re-exports only); deep paths into another feature are forbidden. Within a feature, import siblings directly; tests live beside their module.
- `shared/` accepts a module only after 2+ features use it or it is inherently app-wide; enum→label maps over generated types start in `shared/`.

## API

- `dashboard/api/openapi.yaml` is authoritative (`pnpm api:generate` regenerates; drift fails CI). Import only `@/api/generated/{client,models,schemas,mocks}`; never edit generated files or recreate generated types/enums.
- `fetch` only outside the Dashboard API; Dashboard endpoints go through the generated client only, never hand-built URLs.
- Query policy the contract can't express (polling, invalidation webs) lives in feature-local modules that never restate generated types.

## State

URL path/search owns shareable state; TanStack Query owns server state; local state owns transient interactions; context only for app-wide non-server values (runtime config, theme).

## Constraints

- Forms: React Hook Form + e-INFRA `Form` primitives + Zod at explicit runtime boundaries.
- Loading, stale, empty, and error are durable UI states, never toast-only.
- e-INFRA components and semantic tokens only; no parallel design system, no one-to-one DS wrappers; design mocks never override the design system.
- The inline `index.html` bootstrap sets the runtime `<base>` and theme before assets and CSS paint.
- Runtime configuration is authenticated JSON generated with `jq`; never interpolate environment values into JavaScript.
