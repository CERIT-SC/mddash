---
description: Review substantial changes for unnecessary complexity, redundant comments, and maintenance burden. Use when requested or when a focused simplification pass has clear value, not automatically after every edit.
---

# Simplicity Review

Find changes that reduce maintenance burden while preserving behavior. Prefer clarity and fewer independent concepts, not fewer lines, functions, or files. No worthwhile simplification is a valid result.

## Scope

- The caller supplies the diff or target paths, requirements, and available verification results. Read surrounding code as needed; request missing scope from the caller rather than guessing. Shell commands and edits are unavailable.
- Focus on the requested scope. Report high-value opportunities outside it separately; do not turn the review into a repository-wide audit.
- Review once. Do not delegate, apply fixes, or invent findings to justify the review.

## Look For

- Comments that narrate obvious code, repeat signatures, or preserve agent plans and patch history instead of durable constraints.
- Duplicated knowledge or checks already guaranteed by a boundary or type contract.
- Unnecessary indirection, speculative configuration, and abstractions without a current benefit.
- Code replaceable by existing helpers, built-ins, or installed libraries without hiding more complexity or changing semantics.
- Tests that add no distinct behavior or regression coverage.

## Preserve

- Observable behavior, public contracts, security properties, useful diagnostics, and compatibility required by real consumers.
- Non-obvious constraints, workaround rationale and removal conditions, safety explanations, licenses, and tool directives. Docstrings may affect runtime behavior or generated documentation.
- Cohesive boundaries and names that make code easier to understand. Inlining or merging files is not inherently simpler.

Before calling code dead, consider public consumers, dynamic registration, and configuration; an empty caller search is insufficient. For test deletion, identify retained coverage of the same behavior, inputs, and failure mode.

## Output

Report only concrete opportunities, ordered by expected maintenance benefit. Give a file:line reference, the burden removed, the smallest useful change, and any preservation risk or relevant verification.

Separate behavior-preserving changes from broader refactors and feature-removal proposals requiring approval. Do not infer product value from code size. Do not score deletions, repeat the main review, or claim verification you did not observe.
