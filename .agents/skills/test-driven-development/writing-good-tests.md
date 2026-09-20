# Writing Good Tests

**Load this reference when:** writing or changing tests, adding mocks, or
adding cleanup/helper methods for tests.

## Overview

A test exists to catch a specific break. Two principles govern everything
here:

```
1. Every test names the break it catches
2. Every test exercises the real thing
```

Prefer test-first for production behavior changes: observing a relevant
failure shows the test can detect the intended defect. Use doubles at
boundaries to control external, slow, or nondeterministic dependencies.

## Principle 1: Name the Break

Before writing the test body, answer: **what production change should
make this test fail — and is that change a bug or a decision?** A test
earns its place by catching a wrong branch, missing side effect, wrong
argument, boundary case, or broken contract.

**Derive expectations independently.** Use literals and hand-checked
fixtures; table-driven tests with literal `want` values are the preferred
shape. An expectation computed by the code under test — or its helpers —
passes no matter what that code does:

```typescript
// ❌ Mirror assertion: the same builder computes both sides — always true
const expected = buildSearchQuery({ tag: 'urgent' });
expect(buildSearchQuery({ tag: 'urgent' })).toBe(expected);

// ✅ Hand-derived literal
expect(buildSearchQuery({ tag: 'urgent' })).toBe('tag:"urgent"');
```

**Avoid change detectors.** Assertions on private structure or incidental
wording create churn without protecting behavior. Exact values are useful
when they are part of a public contract. Test the behavior that depends on
a decision: not `expect(MAX_RETRIES).toBe(5)` but "a failing call is
retried 5 times after the initial attempt, with no further attempts."

**Match verification to the artifact.** Run scripts against controlled
inputs and assert outputs, side effects, or exit codes. For config and
docs changes, use applicable schema validation, static checks, and manual
review rather than dummy tests that assert prose or source lines exist.
Check runtime behavior when a config change affects it; use consumer
behavior checks for agent instructions when risk warrants them.

**Your code, not the framework.** Test the contract your code makes at
its boundaries — the route you register, the query you emit, the payload
you produce. Upstream mechanics are their maintainers' tests to write
(the classic: asserting your router invokes a registered handler — that
is the framework's test, not yours). When upstream behavior genuinely
surprised you, write one narrow characterization test naming the
assumption. The same boundary applies inside your code: constructors,
getters, constants, and trivial forwarding earn tests only when they
validate, normalize, default, derive, enforce, or cause side effects —
otherwise assert the first consumer-visible result that depends on them.

### Gate Function

```
BEFORE writing the test body:
  Name the production change that would make this test fail.

  Cannot name one            → redesign around an observable behavior
  "The source text changed"  → choose artifact-appropriate verification
  Private structure changed → test observable behavior instead
  Exact value changed       → assert it only if the contract requires it

  Confirm the expected value is derived without the code under test.
  IF it reuses the code's logic or helpers:
    Replace it with a literal or hand-checked fixture
```

## Principle 2: Exercise the Real Thing

**Assert contracts, not mock existence.** Exercise real production logic.
Assert its outputs or side effects, including calls to a double when
arguments, counts, or ordering are part of a boundary contract. Checking
only that a mocked component renders its own marker proves little.

```typescript
// ✅ Real behavior
expect(screen.getByRole('navigation')).toBeInTheDocument();

// ❌ Mock existence
expect(screen.getByTestId('sidebar-mock')).toBeInTheDocument();
```

**Mock at the right level.** Understand the relevant side effects of the real method
before replacing it; mock the slow or external operation and keep what
the test depends on real. When unsure, run the test against the real
implementation first and observe what actually needs to happen.

```typescript
// ❌ The mock swallows the config write that duplicate detection reads
vi.mock('ToolCatalog', () => ({
  discoverAndCacheTools: vi.fn().mockResolvedValue(undefined)
}));

// ✅ Mock only the slow server startup; the config write stays real
vi.mock('MCPServerManager');
```

**Make doubles specific.** When arguments, call counts, or ordering are
part of the contract, assert them — a fake that accepts anything verifies
nothing about those contracts. Use distinct responses where needed so
the wrong branch cannot satisfy the expectation.

**Use small, valid fixtures.** Include fields required by the boundary
contract and those relevant to the behavior under test. Omit unrelated
optional fields rather than copying entire payloads. Test missing or
malformed fields explicitly where handling them matters; use schema or
integration checks when fixture drift is a risk.

**Keep test-only helpers out of production classes.** Test setup and
cleanup belong in test utilities. A class that owns a resource may still
need a production lifecycle method even if tests are its first caller;
decide by ownership and contract, not caller count alone.

**Prefer real components over complex mocks.** When mock setup outgrows
the test logic, mocks miss methods the real components have, or tests
break when the mock changes, switch to an integration test with real
components where practical.

### Gate Function

```
BEFORE adding a mock or test helper:
  Identify the real method's relevant side effects; keep the ones the test
  depends on real — mock the slow/external level below them.

  Mock responses satisfy the tested contract with small, valid fixtures.

  Test-only helpers live in test utilities; resource owners manage lifecycle.

  About to assert on a mock?
    Check a meaningful interaction contract, not the double's own behavior.
```

## Tests Ship With the Implementation

Ship the tests the behavior needs, not one test per function. For features
and bugs, prefer a focused test first and observe the relevant failure
before implementation when feasible. Add feasible bug regression tests
even in previously untested code. Refactors can rely on existing coverage;
config and docs changes use artifact-appropriate checks. Preserve valid
implementation work and report verification gaps rather than restarting
to recreate a test-first sequence.

## The Mutation Check

Before finishing, consider likely regressions in the changed behavior
and whether the relevant tests would catch them, prioritizing by risk:

- Wrong constant or argument
- Wrong branch handler
- Missing state change or side effect
- Empty or default return
- Missing validation for zero, empty, nil, unauthorized, or malformed input

An important mutation nothing catches suggests a coverage gap or a
tautological test. This is a focused review, not an exhaustive mutation quota.

## Quick Reference

| When you... | Do |
|-------------|-----|
| Write any test | Name the defect or contract violation it catches |
| Build an expected value | Derive it by hand; never with the code under test |
| Verify scripts, configs, or docs | Use behavior, schema, static, or manual checks appropriate to the artifact |
| Reach for a dependency test | Test your boundary contract, not their documented mechanics |
| Want to assert on a mock | Check a boundary contract, not mock existence |
| Are about to mock a method | Learn its side effects; mock the slow/external level |
| Build a mock response | Use a small, valid fixture for the tested contract |
| Need cleanup only tests use | Put it in test utilities |
| Watch mock setup balloon | Switch to an integration test with real components |
| Finish a test file | Review likely regressions by risk |

## Warning Signs

- Setup and assertion share the same object, guaranteeing equality
- The test can fail only through a panic, crash, or missing selector
- The test fails on every intentional change, never on accidental breakage
- Expected values are hidden behind loops, builders, or helpers
- The test greps source text, or asserts a removed symbol stays removed
- The test would still matter if only the framework remained
- The test exists for coverage, checking no side effect or outcome
- An assertion checks only a `*-mock` test ID rather than a meaningful contract
- A production method exists solely for test setup rather than resource ownership
- Mock setup is more than half the test, or you can't explain why the mock is needed
- Mocking "just to be safe"
