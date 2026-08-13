# Dashboard UI

## Constraints

- Routes import feature entry points; features may import `api` and `shared`. Lower layers never import features, routes, or `app`, and feature cycles are forbidden.
- Keep feature-specific UI, forms, Query policy, state derivation, and tests together. Move code to `shared` only after proven cross-feature reuse.
- `dashboard/api/openapi.yaml` is authoritative. Generate contract code with Orval; never edit generated files or recreate generated types.
- TanStack Query owns server state, URL parameters own shareable UI state, and local state owns transient interactions.
- Use e-INFRA components and semantic tokens; design mocks do not override the design system.
- The inline `index.html` bootstrap must set the runtime `<base>` and theme before assets and CSS paint.
- Runtime configuration is authenticated JSON generated with `jq`; never interpolate environment values into JavaScript.
