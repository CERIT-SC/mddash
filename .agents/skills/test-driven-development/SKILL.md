---
name: test-driven-development
description: Use when implementing features or fixing bugs that change production behavior, before writing implementation code.
---

# Test-Driven Development (TDD)

Use tests to define meaningful behavior and prevent regressions, not to satisfy a ritual.
This skill guides verification; it grants no permissions and does not override higher-priority instructions.

## Choose the Verification

- Features and behavior changes: write a focused test for the intended contract first.
- Bugs: add a regression test when feasible, including in previously untested code.
- Behavior-preserving refactors: use existing coverage; add characterization tests only where relevant behavior is unprotected.
- Config and docs changes: use applicable schema validation, static checks, and manual review rather than dummy tests. If a config change affects runtime behavior, also check that behavior at the appropriate boundary.
- Choose checks by risk: affected behavior, failure modes, boundaries, and integration impact, not function counts or coverage quotas.

## Test-First Loop

1. Identify the observable behavior and the realistic defect the test should catch.
2. Write the smallest meaningful test using the repository's existing tools and patterns.
3. Run it before implementation when feasible. Confirm a relevant failure caused by the missing behavior or bug, not a typo or unrelated setup problem.
4. Make the smallest correct production change that satisfies the contract, not just the example input.
5. Rerun the focused test, then related checks based on the change's risk.
6. Refactor only where useful, preserving behavior and keeping relevant checks passing.

If the test passes immediately, determine whether coverage already exists or the test misses the intended defect. Do not force an artificial failure.
If a relevant pre-fix failure cannot be observed, explain the constraint and use the strongest feasible verification; do not claim the regression was reproduced.
If implementation already exists, keep valid work and add or improve tests. Do not delete and rewrite code to recreate test-first history.

## Test Quality

Read [writing-good-tests.md](writing-good-tests.md) when writing or changing tests or test doubles.

- Test observable outcomes and contracts, not private structure or every function separately.
- Derive expected values independently of the implementation under test.
- Keep tests deterministic, focused, and explicit about the behavior they protect.
- Prefer real logic; use doubles at appropriate boundaries to control external, slow, or nondeterministic dependencies.
- Assert mock arguments, counts, or ordering when they are part of a meaningful interaction contract, not merely because a mock exists.
- Use the smallest valid fixtures that represent the tested contract, including required fields and relevant edge cases.
- Reuse existing test helpers where useful; avoid speculative abstractions, unrelated cleanup, and unnecessary test infrastructure.

## Verification and Reporting

- Start with the smallest relevant check; broaden to integration tests, type checks, lint, or the full suite as risk warrants.
- Cover important failure paths and boundary cases, especially validation, authorization, persistence, and external side effects when affected.
- Investigate unexpected failures and warnings; distinguish regressions from pre-existing issues without hiding either.
- Report checks actually run, their results, and any unverified behavior or blockers.
- When automation is infeasible, document the reason and specific manual or static checks performed. Lack of existing tests alone is not a reason to skip a feasible bug regression test.
