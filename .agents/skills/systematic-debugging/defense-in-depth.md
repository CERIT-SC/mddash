# Defense-in-Depth Validation

## Overview

Fix invalid data at its source, then decide whether a boundary or invariant needs protection against recurrence. Defense in depth addresses independent failure modes; repeating the same check at every call layer adds maintenance cost without necessarily improving safety.

**Core principle:** Each retained check needs an owning boundary or invariant and a concrete failure mode it prevents.

## Choosing Checks

| Location | Concrete reason to validate | When not to add another check |
|----------|-----------------------------|-------------------------------|
| Trust boundary | External input can violate the accepted shape or domain contract | An internal wrapper only forwards already-validated, unchanged data |
| Domain operation | Valid input can still violate an operation-specific rule, such as an invalid state transition | The operation merely repeats the entry point's schema checks |
| Side-effect boundary | Independent callers can bypass validation, or mutable state can change before use | All callers share the same enforced contract and no new failure mode exists |
| Test fixture or harness | Uninitialized setup or accidental access to real resources can pollute tests | A production `NODE_ENV` branch exists only to compensate for broken test setup |

Revalidation can be appropriate after a transformation, across a process boundary, or after state changes. Name the actual bypass or invalidated assumption; hypothetical future refactors and mocks alone do not justify checks everywhere. Share validation rules across independent entry points instead of copying them.

## Example: Empty Project Directory

**Observed flow:**
1. Test setup exposes `tempDir: ''` before `beforeEach` runs.
2. `Project.create()` passes that value through workspace/session helpers.
3. The process wrapper receives an empty `cwd` and runs `git init` in the source directory.

**Root-cause fix:** Create the project after fixture initialization. If the fixture API exposes an uninitialized directory, have its getter fail on premature access rather than returning a usable-looking empty string.

**Choose a validation owner:** If `createProject` accepts external directory input, reject a missing directory there before it reaches side effects. For example, this boundary rejects blank input instead of allowing a default working directory:

```typescript
function requireProjectDirectory(value: unknown): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error('project directory required');
  }
  return value;
}
```

This checks only the nonblank-input contract; it is not proof of existence, writability, or authorization. Validate those properties only where the operation requires them. Filesystem prechecks can race with use, so handle operation errors even when prechecks improve diagnostics.

**Additional protection is conditional:**
- If the process wrapper is independently callable with untrusted directory input, enforce the explicit-directory contract at that boundary too, reusing the rule. Show the independent call path in a test.
- Do not repeat the empty-string check in every workspace/session helper that only forwards the validated value.
- Keep test resource isolation in fixtures or the harness. Avoid test-environment branches in production unless a concrete safety requirement cannot be met there; document the requirement and test the affected behavior.
- If the product restricts filesystem operations to an approved root, enforce that policy for all relevant callers, not only tests. A string-prefix check does not prove containment: account for path components, symlinks, and filesystem races according to the threat model.

## Diagnostics Are Not Validation

Logging can reveal a failing call path but cannot prevent it. Start with existing traces; if needed, add a temporary probe for the unresolved question at the suspected operation. Prefer presence flags, safe IDs, and error codes over raw paths, payloads, or environment values.

For stack tracing, use a local debugger or a narrowly scoped diagnostic hook in a safe reproduction. Inspect and redact paths or other sensitive context before retaining or sharing output. Bound collection time and volume, then remove the probe. Permanent telemetry requires a separate operational justification, safe fields, and access/retention controls.

## Applying the Pattern

1. Reproduce the failure and trace the invalid value to its source.
2. Fix the source and add a regression test where feasible. Observe its failure before the fix and success afterward; if that cannot be established, report the limitation and verification actually performed.
3. Identify any remaining trust boundary or invariant. For each proposed check, state the concrete failure mode, owner, and why an existing check cannot cover it.
4. Implement only the justified checks; preserve errors from operations whose state can change after validation.
5. Test each distinct failure mode and the valid path. For a rejected directory, verify no process is launched; for the fixture bug, verify no source-tree pollution occurs in an isolated reproduction.
6. Remove temporary diagnostics and run relevant regression tests. Report observed coverage and limitations rather than claiming the bug is impossible.
