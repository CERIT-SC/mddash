# Dashboard UI Architecture Design

**Date:** 2026-08-13
**Status:** Approved
**Scope:** Frontend workspace and greenfield Dashboard UI architecture

## Goal

Establish a clean-room architecture for a new Dashboard SPA of approximately the same product scale as the current UI. The architecture must keep related code close together, minimize manually maintained API code, use the e-INFRA design system, and make changes easy to understand and verify for both people and coding agents.

This design defines application boundaries, dependency direction, API integration, state ownership, quality tooling, and test strategy. It deliberately does not predict the Dashboard's feature decomposition or decide migration and release policy.

## Context

The current Dashboard UI is a React/Vite application of roughly 14,500 lines across more than 130 source files. It already uses TanStack Query and TanStack Router, but product behavior is distributed across global component, hook, utility, and type directories. API DTOs are handwritten, form validation is ad hoc, long-running operation state is interpreted in presentation components, and the UI has no automated frontend test suite.

The repository contains three active frontend applications:

- `dashboard/ui`: runtime-configured authenticated SPA served under a JupyterHub user base path.
- `landing`: public single-file Vite build.
- `hub/ui`: Jinja-aware multi-entry Vite build for JupyterHub templates.

They currently use independent pnpm roots and lockfiles. Landing and Hub use `@e-infra/design-system`; Dashboard does not. A committed prebuilt JupyterLab extension also contains JavaScript artifacts but is not an active frontend project and must remain outside workspace tooling.

The Flask Dashboard API has no OpenAPI document or automatic schema generation. It exposes approximately 50 operations with several contract-sensitive cases: multipart uploads, arbitrary binary downloads, JSON-string logs, redirects, RFC 9457 errors, engine-discriminated payloads, variable analysis results, and catch-all path parameters containing slashes.

## Locked Decisions

| Area | Decision |
|---|---|
| Rewrite boundary | Clean-room UI. Existing behavior and contracts are reference material; old components, hooks, and architecture are not copied. Proven framework-neutral algorithms may be rederived only after explicit review. |
| Architecture | Feature modules with thin file-based routes and centralized generated API infrastructure. |
| API contract ownership | `dashboard/api` owns the canonical OpenAPI document. It is handwritten initially and may be generated there later. |
| Contract coverage | The OpenAPI document covers the full current Dashboard API before feature implementation depends on it. |
| Contract authority | The contract defines the intended stable target. Implementation discrepancies are backend defects to resolve. |
| API generation | Orval generates contract-derived operations, DTOs, TanStack Query artifacts, Zod schemas, and MSW artifacts. Handwritten code supplies application policy only. |
| Generated output | Generated artifacts are committed, read-only, and checked for regeneration drift in CI. |
| Runtime validation | Orval generates Zod schemas as a separate documented output. Features invoke them explicitly at boundaries that require runtime parsing; automatic React Query response parsing is deferred until Orval officially supports that integration. |
| Server state | TanStack Query. |
| Routing | TanStack Router with thin file-based route modules and a generated route tree. |
| Forms | React Hook Form with the e-INFRA design system's RHF-aware form primitives. Zod supplies form schemas where appropriate. |
| Long-running state | Generated status types plus small feature-local pure state functions; no state-machine library. |
| Design system | e-INFRA components and tokens are mandatory and take priority over screenshots. |
| Frontend workspace | One root pnpm workspace and lockfile for the three active UIs, without shared application code. |
| TypeScript | Stable TypeScript 7.0 across the active workspace. |
| Linting | Type-aware Oxlint with the matching `oxlint-tsgolint`; independent TypeScript checking remains required. |
| Formatting | Keep Prettier initially. Evaluate Oxfmt later in an isolated tooling change. |
| Testing | Vitest unit tests, Testing Library/MSW integration tests, and a small Playwright E2E suite. |

## Considered Architecture Approaches

### 1. Feature modules with centralized generated API infrastructure

Thin route files select feature entry points. Each feature owns its components, forms, Query policy, derived state, and tests. Contract-derived code lives in a single generated boundary.

This is the selected approach because a change can usually be understood within one capability while transport definitions remain authoritative and reusable.

### 2. Route-centric slices

Most code would live beneath route directories. This makes navigation structure easy to inspect but couples product capabilities to URL structure. Domains used by multiple routes tend to be duplicated or moved into an increasingly broad shared layer.

### 3. Technical layers

Global `components`, `hooks`, `schemas`, `services`, and `utils` directories are initially familiar, but a feature change spans many distant folders. This resembles the current architecture's primary scaling problem and encourages unrelated catch-all modules.

## System Boundaries

The application has five top-level boundaries:

- `app`: composition root, providers, runtime configuration, router construction, global styling, and global failure handling.
- `routes`: URL parsing, route lifecycle, route boundaries, loading, and selection of feature entry points.
- `features`: product capabilities introduced only when their separately designed behavior requires them.
- `api`: generated transport code and the narrow handwritten policies that OpenAPI cannot express.
- `shared`: proven Dashboard-wide UI compositions, generic helpers, hooks, and test infrastructure.

Dependencies flow in one direction:

```text
app/routes -> features -> api/shared
```

Lower layers never import upper layers. `app` initializes lower-level modules by passing validated values into their public initialization functions; `api` and `shared` never import from `app`. Feature-to-feature imports use an explicit public entry point and are allowed only when one capability intentionally depends on another. Cycles are forbidden.

No cross-application React component package is introduced. Dashboard, Landing, and Hub have different runtime and build contracts. The e-INFRA package is their common visual foundation; the root workspace shares dependency policy and tooling, not application code. Shared application packages may be considered later only after stable, identical duplication is demonstrated.

## Generic Directory Structure

```text
dashboard/
├── api/
│   └── openapi.yaml                  # API-owned canonical contract
└── ui/
    ├── src/
    │   ├── app/
    │   │   ├── config/               # runtime configuration loading and validation
    │   │   ├── providers/            # application-wide React providers
    │   │   ├── styles/               # global CSS and design-system setup
    │   │   ├── router.tsx            # router construction and global context
    │   │   └── main.tsx              # browser entry point
    │   ├── routes/                    # thin TanStack file-based route modules
    │   ├── features/                  # capability modules created as needed
    │   ├── api/
    │   │   ├── generated/
    │   │   │   ├── client/           # generated operations and API types
    │   │   │   ├── query/            # generated Query keys/options/hooks
    │   │   │   ├── schemas/          # generated Zod schemas
    │   │   │   └── mocks/            # generated MSW handlers/factories
    │   │   ├── runtime.ts            # initialized runtime URL and request policy
    │   │   ├── errors.ts             # RFC 9457 normalization and ApiError
    │   │   └── index.ts              # stable handwritten API policy exports
    │   ├── shared/
    │   │   ├── ui/                   # reusable compositions of e-INFRA primitives
    │   │   ├── lib/                  # cohesive framework-neutral helpers
    │   │   ├── hooks/                # genuinely cross-feature React behavior
    │   │   └── testing/              # render harnesses, fixtures, and MSW setup
    │   ├── assets/                    # source-controlled static assets
    │   └── routeTree.gen.ts           # generated TanStack route tree
    ├── e2e/                           # cross-route Playwright workflows
    ├── orval.config.ts                # OpenAPI generation configuration
    ├── playwright.config.ts
    ├── vite.config.ts
    └── vitest.config.ts
```

This tree specifies architecture, not product features. `features/` is intentionally unexpanded. A feature starts flat and adds internal directories only when it contains independently understandable units. Empty ceremonial directories are not created.

### Placement Rules

- Start product code in the feature that owns the user capability.
- Keep feature-specific components, forms, Query policies, derived state, and tests together.
- Keep routes limited to URL concerns, route lifecycle, and feature entry-point selection.
- Keep tests beside the code they verify; reserve `e2e/` for workflows crossing route, browser, or deployment boundaries.
- Put code in `shared` only when reuse is demonstrated or the responsibility is inherently application-wide.
- `shared/ui` composes e-INFRA primitives; it does not mirror or replace the design system.
- `shared/lib` stays product-domain-neutral. Product rules stay in their owning feature.
- `shared/hooks` is not the default destination for hooks. A hook moves there only when it is feature-independent.
- Generated files are never manually edited.

Application code imports generated artifacts only through the generated public barrel for each artifact class: `@/api/generated/client`, `@/api/generated/query`, `@/api/generated/schemas`, or `@/api/generated/mocks`. Deep imports into generated files are forbidden. Handwritten API policy is imported through `@/api`. This keeps generation discoverable without manually recreating a second operation-by-operation facade.

## OpenAPI And Generated Client

### Contract ownership

`dashboard/api/openapi.yaml` is the canonical contract during the manual phase. Keeping it API-owned ensures that future Flask-side generation replaces the production mechanism without moving authority to the UI or changing the consumer boundary.

The document covers the full Dashboard API and includes:

- Stable, intentional `operationId` values.
- Every success status and media type.
- Reusable RFC 9457 problem-details responses.
- Correct optionality and nullability.
- Multipart uploads and repeated file fields.
- Binary responses and JSON-string log responses.
- Browser redirects used by OAuth.
- Engine-discriminated request and response schemas.
- A typed catalog of every supported analysis-result payload.
- Authentication and runtime-base-URL constraints.

The contract is the target authority rather than a transcription of accidental behavior. Contract/implementation conflicts are fixed in the API before generated consumers rely on them.

### Executable contract

The contract is enforced as code:

- CI compares Flask's registered Dashboard API method/path inventory with OpenAPI and fails for a route missing from either side.
- Each documented status/media-type pair has a named API contract test that validates the response body when one exists.
- Runtime response validation in API tests prevents an exercised response from bypassing its documented schema.
- Contract validation runs before generation.
- CI regenerates committed artifacts and rejects a dirty diff.
- Strict TypeScript compiles all generated output.
- API-side contract tests validate structured JSON responses against OpenAPI. Empty, scalar, redirect, and binary responses are verified by status/media-type contract tests and transport integration tests.
- API changes update the contract first, then backend behavior and generated consumers in the same change.

### Orval

Orval is the selected development-time generator because it provides the broadest stable fit for the requirement not to handwrite inferable code. It generates:

- Request and response TypeScript types.
- Named operation functions.
- TanStack Query keys, option factories, and hooks.
- A separate Zod output containing request and response schemas.
- MSW handlers and data factories.

Orval is not a runtime architecture dependency outside its output. Its exact version is pinned. Generated files are committed, carry generated headers, and are replaceable as a unit. Feature and route architecture must not depend on Orval-specific internals beyond documented generated entry points.

Generation follows Orval's documented `Client with Zod` pattern with two outputs:

- A React Query client using Orval's built-in Fetch transport, ordinary generated TypeScript models, operations, query keys/options/hooks, and MSW artifacts.
- A separate `client: "zod"` output for generated request and response schemas.

The React Query output does not enable `override.fetch.runtimeValidation`. Orval 8.24 does not officially integrate automatic Fetch response validation with the React Query client and emits invalid imports for that combination. Generated Zod schemas are used explicitly by feature code only when untrusted data needs runtime parsing, such as form values, persisted browser data, imported files, or variable third-party payloads. Normal Dashboard API responses rely on API-side OpenAPI contract tests plus generated static types until Orval provides an officially supported automatic integration. Generated files are never post-processed or patched.

Alternative generators were considered. The `openapi-typescript` stack produces less generated code but leaves operation calls and multipart behavior handwritten. Hey API remains pre-1.0 and has a higher breaking-change risk. Kubb's stable and next-generation lines are in transition. Orval is a project-specific selection, not an industry standard.

### Handwritten API policy

Handwritten API modules own only behavior that cannot be reliably inferred from OpenAPI:

- `app` passes the validated API base URL to `api/runtime.ts` before any generated operation runs. Orval's runtime base-URL expression imports from this lower-level module, so generated code never imports `app/config`.
- Generated Fetch request options set same-origin cookie credentials centrally.
- Built-in Fetch rejects non-success responses. `api/errors.ts` converts its documented `{ info, status }` error envelope and network failures into the application `ApiError` whenever an error is presented or interpreted. Global Query callbacks use the same converter; application code never parses generator-specific errors itself.
- Generated URL helpers provide OAuth destinations; a feature controller owns the browser navigation action.
- Multipart, scalar, empty, and binary operations use generated behavior proven by transport integration tests.
- Legacy catch-all path serialization is isolated in an Orval operation override or generated URL customization, never in a feature.

Features do not construct endpoint URLs or call `fetch` directly.

The current `simulation_path` and file-path catch-all routes are non-standard OpenAPI edge cases because a single path parameter may contain `/`. The contract documents actual encoding requirements, and the transport boundary centralizes the workaround. A future API redesign should move opaque filesystem-like identifiers out of path parameters. No feature may depend directly on the workaround.

## Data And State Ownership

### Server state

TanStack Query exclusively owns server state. Features use generated Query artifacts directly when defaults are sufficient. A thin feature-local query module is allowed only for application policy that cannot be inferred from the contract, such as:

- Polling interval and terminal-state conditions.
- Cross-operation invalidation.
- Optimistic updates.
- Derived selectors.
- Route preloading policy.

Such modules must not restate generated request or response types.

Route loaders may call `queryClient.ensureQueryData` with generated query options. Routes and components therefore share one cache instead of passing loaded server payloads through deep prop chains.

### Client state

State ownership follows this order:

1. URL-addressable state belongs in TanStack Router path or validated search parameters.
2. Form and transient interaction state stays local.
3. Durable server truth stays in TanStack Query.
4. A narrowly scoped context is used only when many descendants need the same non-server value.

Runtime configuration and theme are valid application-level contexts. Feature state is not promoted globally by default. No general-purpose global state library is introduced.

### Long-running operations

Notebook, tuner, simulation, analysis, and publication lifecycles use generated status values plus small feature-local pure functions. These functions answer questions such as `isTerminal`, `canRetry`, `pollInterval`, and permitted actions.

TanStack Query owns synchronization. Pure state functions own interpretation. Presentation components do not accumulate repeated status conditionals, and no state-machine library is introduced.

## Forms And Validation

Forms use React Hook Form directly. The e-INFRA design system's `Form` components provide RHF-aware field composition but do not replace RHF state management.

Zod is used at explicit runtime boundaries:

- Generated Zod schemas validate untrusted values when a feature requires runtime parsing. They are not automatically applied to every Query response.
- Feature-local Zod schemas describe form rules that are stricter, conditional, or differently shaped from wire requests.

Generated request schemas are reused when a form and request have the same shape and user-facing validation semantics. UI schemas are not forced to mirror multipart payloads or transport details. Multipart conversion and request mapping occur at the submit boundary, not inside visual controls.

Backend validation remains authoritative. Recognized field errors are mapped into RHF. Non-field RFC 9457 errors use the application error presentation. Generated DTOs and schemas are never manually copied into feature type files.

## Design System And Components

The e-INFRA design system is the visual and interaction foundation. Its setup CSS, semantic tokens, typography, themes, and primitives are initialized once under `app/styles` and `app/providers`.

Application code imports e-INFRA primitives directly. A component enters `shared/ui` only when it composes primitives into a reusable application-wide interaction or accessibility pattern. One-to-one wrappers around design-system primitives are not created.

### Styling rules

- Prefer design-system components, variants, and semantic tokens.
- Use Tailwind utilities for responsive layout within the design-system vocabulary.
- Do not copy or fork e-INFRA primitives.
- Do not establish parallel color, typography, spacing, or component systems.
- Limit custom CSS to global integration, third-party library requirements, and behavior the design system cannot express.
- Initialize theme synchronously before React renders to prevent FOUC. The e-INFRA documented theme keys and behavior are the single persistence contract; the application must not create a competing theme store or key set.

### Design mock workflow

Security, correctness, accessibility, and explicitly approved supported behavior are invariants; no visual priority can override them. Within those invariants, each supplied design mock follows this priority for visual and interaction decisions:

1. e-INFRA design system.
2. Explicit user direction.
3. Runtime bug fixes discovered during the UI pass.
4. The mock's layout, hierarchy, and visual language.
5. Existing visual treatment for behavior not addressed by the mock.

A screenshot is design input, not a complete specification. Existing supported behavior cannot be silently dropped even though it is visually lower priority. Loading, failure, empty, retry, cancellation, polling, and other reachable states must be designed in the same visual language. Each mock receives an analyze-and-approve pass before implementation. UI work loads both the `e-infra-design-system` and `ui-ux` workflows.

If a design requires a missing component, variant, token, accessibility fix, or responsive behavior, first verify the gap against the pinned package and documentation. A generally useful gap is handled through a minimal upstream issue or PR to `CERIT-SC/design-system` following the repository's design-mock implementation workflow. If upstream contribution is not appropriate, the mock's design approval records why. A local workaround is allowed only when project-specific or when upstream delivery would block work; it must be narrow, reference the upstream issue/PR when one exists, state the package-version removal trigger, and be removed after that release. Known upstream issues must not receive conflicting local overrides.

### Component responsibilities

- Route and feature entry components orchestrate.
- Leaf components render and emit user intent.
- Network calls, navigation, and cache mutation remain in feature-level hooks or controllers, not generic UI components.
- Prop contracts express application intent rather than passing whole API payloads unnecessarily.
- Loading, stale, empty, unavailable, and error states are durable UI states rather than toast-only fallbacks.
- Imperative visualization libraries are isolated behind focused adapters with explicit input contracts and deterministic cleanup.

Accessibility remains an application responsibility even when primitives are accessible. Tests cover landmarks and headings, labels, keyboard operation, focus restoration, live announcements, reduced motion, responsive behavior, and meaningful error presentation.

## Cohesive Reuse

The architecture avoids duplication without creating global dumping grounds. Shared code is placed at the narrowest common owner.

Files named `constants.ts`, `formatters.ts`, `types.ts`, or `hooks.ts` are allowed when scoped to one cohesive feature or concept. They are not allowed to collect unrelated exports merely because those exports share a TypeScript category.

Examples:

- Runtime URLs and deployment values belong in `app/config`, not a global constants file.
- API enum-like values come from generated types rather than handwritten constants.
- Feature-wide constants may live beside that feature.
- Application-wide formatters may live under a clearly named `shared/lib/format` module.
- A reusable status chip composed from e-INFRA primitives belongs in `shared/ui`.
- Job-status-to-semantic-variant mapping used across multiple capabilities is defined and tested once against generated job status types.
- A pod- or upload-specific status component remains feature-local until reuse or a stable shared status-display concept is demonstrated.

The placement test is:

1. Does the module have one coherent responsibility?
2. Does it have a clear owner?
3. Is reuse demonstrated rather than predicted?
4. Can it be found through product or technical vocabulary?
5. Would the new export reduce the module's cohesion?

## Runtime And Build

The Dashboard remains a static Vite SPA served by the proxy under an arbitrary JupyterHub user base path. Deployment-specific URLs and user identity are not build-time variables.

A runtime configuration schema validates `window.MDDASH_CONFIG` before application providers are created and exposes one immutable configuration object. Missing production fields fail visibly. Local development uses an explicit development configuration rather than interpreting absent configuration as a general-purpose debug flag. The composition root initializes `api/runtime.ts` with the validated API URL; the API layer never reads application configuration directly.

Development mode and test mode must not implicitly enable product behavior. Any future product capability flag requires its own feature specification and an explicit runtime-config field.

The composition root establishes these concerns in order:

1. Synchronous application of the e-INFRA documented theme preference before React render.
2. Validated runtime configuration.
3. OpenAPI transport client.
4. TanStack Query client and global Query policy.
5. TanStack Router with runtime base path and Query context.
6. Global render-error, route-error, notification, and accessibility infrastructure.

The application defines durable global states for invalid runtime configuration, route not found, route load failure, unexpected render failure, and offline/network failure. When an RFC 9457 body supplies a `type`, that support identifier is displayed in the durable error details.

Route-level lazy loading provides natural bundle boundaries. Large visualization dependencies load only where used. Manual chunk maps are introduced only after measurement demonstrates a problem.

## Workspace And Tooling

### pnpm workspace

The three active UIs become one root pnpm workspace with one lockfile:

- `dashboard/ui`
- `landing`
- `hub/ui`

Each remains independently buildable. The workspace centralizes dependency versions, installation, scripts, and quality policy without introducing shared React code. The committed prebuilt JupyterLab extension is excluded.

Node and pnpm versions are pinned consistently across local development, CI, and container builds. Root commands run checks recursively or through explicit package filters. CI uses the same commands as local development.

### TypeScript 7

The active workspace standardizes on stable TypeScript 7.0. The current `@typescript/native-preview` dependency and `tsgo` scripts are replaced by the stable `typescript` package and `tsc` executable.

The existing React/Vite configurations are compatible in principle: they use bundler module resolution, React JSX, and no removed `baseUrl`. The migration must add direct Node typings for configuration files and make ambient type inclusion explicit because TypeScript 7 defaults `types` to an empty list.

Vite and Vitest transpilation do not replace project type checking. Strict `tsc --noEmit` or project-build verification remains an independent required gate.

### Oxlint

Oxlint replaces Dashboard ESLint and becomes the linter for all three active UIs. Ordinary Oxlint uses Oxc's Rust parser and does not depend on TypeScript's missing JavaScript compiler API. Type-aware linting uses the matching `oxlint-tsgolint`, built on TypeScript's native Go implementation, and therefore does not wait for the planned TypeScript 7.1 API.

The exact Oxlint and `oxlint-tsgolint` versions are pinned and aligned with the selected TypeScript release. The migrated rule inventory must preserve the current Hooks, React Refresh, equality, and type-import behavior while adding one consistent workspace policy. Type-aware rule coverage and diagnostics are verified before removing ESLint.

Oxlint does not replace `tsc`. Its compiler-diagnostic mode is not used as the sole type-check gate.

### Formatting

Prettier remains the workspace formatter initially. It preserves the repository's current no-semicolon, double-quote, width, import-ordering, and Tailwind class-ordering policy.

Oxfmt is deferred to a separate formatting-only evaluation because it remains beta and does not exactly reproduce the current `@ianvs/prettier-plugin-sort-imports` behavior. Future adoption requires accepted import grouping, Tailwind v4 sorting, complete file coverage, idempotent output, and a reviewable one-time migration. Oxlint and Oxfmt are not coupled decisions.

### Generated code

Generator-owned files compile but are excluded from manual lint fixes or other transformations that rewrite generated output. CI verifies:

- OpenAPI validity.
- Orval regeneration drift.
- TanStack route-tree regeneration drift.
- Strict compilation.
- Dependency and lockfile consistency.
- Forbidden imports and cycles.
- Unused exports and dependencies where the selected tooling can enforce them reliably.

## Testing Strategy

The test suite follows a pyramid: many unit tests, more focused integration tests, and few E2E tests.

### Unit tests

Vitest verifies pure logic without rendering React, including:

- Derived operation states.
- Form/request transformations.
- Route search schemas.
- Runtime-configuration parsing.
- RFC 9457 conversion.
- Formatters and semantic status mappings.

### Integration tests

Vitest, Testing Library, and MSW carry most UI behavior coverage. Tests render routes or feature entry points with realistic application providers. Generated MSW handlers provide contract-shaped defaults; scenario behavior and assertions remain handwritten.

Integration tests cover forms, Query behavior, invalidation, polling termination, routing interactions, and loading, stale, empty, failure, and retry states. Tests query by semantic role and accessible name rather than implementation details or CSS classes.

### End-to-end tests

Playwright covers only critical user journeys and browser/deployment behavior that lower levels cannot prove, including:

- Representative multi-step workflows.
- Runtime base paths.
- Refresh and back/forward URL restoration.
- File upload and download behavior.
- OAuth browser navigation.
- Responsive behavior.
- Representative accessibility and focus flows.

Playwright tests follow these rules:

- Every test creates or resets its own data and can run independently and in parallel.
- Prefer `getByRole` and `getByLabel`; use `data-testid` only when no stable user-facing locator exists.
- Never select by CSS class or DOM position.
- Assert user-visible outcomes, not React, Query, or API internals.
- Never use fixed sleeps; wait for observable UI, URL, response, or state transitions.
- Use fixtures for repeated environment and data setup.
- Introduce small page/component objects only when they remove meaningful interaction duplication.
- Mock external and expensive nondeterministic services.
- Keep a small real Dashboard API suite against the demo/test environment.
- Do not duplicate the complete OpenAPI contract suite in browser tests.
- Collect traces, screenshots, and videos on CI failure or retry.
- Treat retries as diagnostic evidence, not a solution to flaky tests.
- Run critical flows at desktop and mobile widths; add cross-browser coverage where platform behavior matters.

API contract compliance is tested API-side against OpenAPI, not through E2E tests.

## Agentic-First Maintainability

Agentic-first means reducing the context required to make a correct change, not increasing abstraction.

- A route points to one feature public entry point.
- Feature behavior, UI, forms, Query policy, pure state derivation, and tests stay close together.
- API operations and schemas are discoverable through stable OpenAPI `operationId` values.
- Generated files have clear headers and are never manually edited.
- Root commands provide one canonical path for generation, formatting, linting, type checking, tests, and builds.
- Dependency boundaries are enforced by lint/import rules, not documentation alone.
- Barrel files exist only as intentional public boundaries; deep wildcard barrels are avoided.
- Modules split by responsibility when they become difficult to understand independently, not at arbitrary line limits.
- Names use product language and describe intent.
- Frontend-derived types live with their feature and do not shadow generated DTO names.
- Non-obvious local constraints belong in the nearest `AGENTS.md`; ordinary structure remains self-explanatory.
- Cross-feature architecture decisions are recorded in `docs/specs`; feature and mock decisions receive separate specs.

## Implementation Sequence

Implementation follows dependency direction:

1. Establish the root pnpm workspace, one lockfile, pinned Node/pnpm/TypeScript 7 versions, root commands, Oxlint, and retained Prettier policy.
2. Add the API-owned full OpenAPI contract and API-side contract validation.
3. Configure the documented separate Orval React Query/Fetch and Zod outputs, committed generation, representative transport tests, and CI drift checks.
4. Establish the generic SPA skeleton: runtime config, e-INFRA setup, providers, file-based router, Query integration, global boundaries, tests, and import rules.
5. Introduce feature modules only through separately approved feature or design-mock specifications.

This sequence does not prescribe migration or release timing. It ensures that feature implementation starts only after the contract and architectural boundaries are operational.

## Architecture Acceptance Criteria

The architecture is operational when:

- All three active UIs install from one frozen workspace lockfile and remain independently buildable.
- Local, CI, and container environments use aligned Node and pnpm versions.
- Stable TypeScript 7 strict checks pass across the active workspace.
- Type-aware Oxlint passes across the active workspace without an ESLint dependency.
- Prettier remains deterministic under the centralized workspace commands.
- The full Dashboard API contract validates, and its method/path inventory exactly matches Flask's registered Dashboard API routes.
- Every documented status/media-type pair has a named API-side contract test.
- Orval output regenerates deterministically, has no manual edits, and compiles.
- Generated contract-shape tests cover JSON, a discriminated union, empty `204`, scalar JSON, multipart, and binary operations. Explicit Zod boundary tests prove generated schemas accept valid values and reject malformed values where runtime parsing is required.
- A generated operation demonstrably uses the initialized runtime base URL and same-origin cookies, passes through TanStack Query and generated MSW, and presents an RFC 9457 response as `ApiError`.
- Runtime configuration and routing pass at both `/` and the representative nested base path `/user/test-user/dash/`, including direct load and refresh.
- TanStack file-based routing and route-tree drift checks are operational.
- Unit and integration suites run in CI. The Playwright architecture smoke suite loads the root route at the nested base path, renders the invalid-config state, and renders route-not-found.
- e-INFRA setup and pre-render theme restoration pass visual and accessibility assertions. Import and source checks reject copied primitive modules, raw color literals, and generic Tailwind palette colors outside approved third-party adapter styles.
- Import restrictions prevent upward dependencies and feature cycles; generated imports are limited to the four approved generated barrels.

## Out Of Scope

- Dashboard screen and feature designs.
- The eventual list or nesting of feature modules.
- Behavior-parity and release-readiness decisions.
- Migration, deployment, and cutover strategy.
- Archiving or deleting the current UI.
- Automatic Flask OpenAPI generation.
- API redesign beyond fixes needed to satisfy the approved manual contract.
- Cross-application React component packages.
- Oxfmt adoption.

These topics consume this architecture or replace a mechanism behind one of its boundaries, but require separate design decisions.
