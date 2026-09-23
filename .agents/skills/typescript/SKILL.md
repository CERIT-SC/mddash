---
name: typescript
description: ALWAYS use this skill when writing, modifying, reviewing, or testing TypeScript, TSConfig, or typed JavaScript interfaces.
---

# TypeScript Standards

## Type Safety

- Use `unknown` for unvalidated external data and convert it to typed values at the boundary.
- Use schemas or type guards for API responses, parsed files, user input, messages, and storage data.
- Contain third-party `any` at the boundary and immediately convert it to a specific type.
- Replace non-null assertions with explicit narrowing, defaults, or error handling.
- Use explicit return types for exported APIs, non-trivial functions, and async boundaries.
- Infer obvious local return types.

## Data Modeling

- Use `type` aliases for authored object shapes, unions, props, and aliases.
- Use `interface` only for required ambient, global, or third-party declaration merging.
- Use string literal unions or `as const` maps for finite sets.
- Use `undefined` for optional in-process values.
- Use `null` for explicit external contracts such as JSON APIs or database values.
- Model create, update, and patch inputs explicitly.

## Expressions And Control Flow

- Use `??` for defaults when `0`, `false`, or `""` are valid values.
- Use `Array.isArray()` for array checks.
- Use `for...of` when early exit, `await`, or clear control flow matters.
- Use `satisfies` for literal object validation.
- Keep type assertions local to validated boundaries.

## Imports And Modules

- Follow the project `tsconfig` and linter as the source of truth.
- Use `import type` for type-only imports where required or clearer.
- Keep module boundaries explicit.
- Use ES modules for modern application code.
- Keep generated types generated; update schemas or source contracts.

## Naming

- Use PascalCase for types and components.
- Use single uppercase or PascalCase type parameters.
- Use camelCase for functions and variables.
- Use SCREAMING_SNAKE_CASE for constants.
- Use kebab-case filenames.
- Use descriptive domain type names for interface-like shapes: `User`, `UserProps`, `ApiResponse`.
- Use names without `I` prefixes for types and interfaces.

## Verification

- Run the project typecheck after non-trivial TypeScript changes.
- Run focused tests for changed runtime behavior.
