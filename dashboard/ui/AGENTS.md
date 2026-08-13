# Dashboard UI

## Architecture

- Clean-room React/TypeScript SPA built with the e-INFRA design system, TanStack Router, and TanStack Query.
- `app/` assembles global configuration and providers; `routes/` contains thin file-based route adapters; `features/` owns product capabilities; `api/` contains generated contract code and transport policy; `shared/` contains proven cross-feature code.
- Imports flow `app/routes -> features -> api/shared`. Lower layers never import upper layers, and feature cycles are forbidden.
- `dashboard/api/openapi.yaml` is the API contract. Generate clients and schemas with Orval; never edit generated files manually or recreate generated types.
- Keep feature UI, forms, Query policy, derived state, and tests together. Add shared abstractions only after real reuse is demonstrated.
- Use React Hook Form and Zod for forms, URL state for shareable UI state, local state for transient interactions, and TanStack Query for server state.
- Use only e-INFRA components and semantic tokens for application UI. Follow the design-mock workflow for missing design-system capabilities.
