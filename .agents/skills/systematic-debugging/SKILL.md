---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes
---

# Systematic Debugging

## Overview

**Core principle:** Investigate the root cause before choosing a fix. Use reproduction and evidence to distinguish a causal fix from symptom suppression.

## When to Use

Use for ANY technical issue:
- Test failures
- Bugs in production
- Unexpected behavior
- Performance problems
- Build failures
- Integration issues

**Use this ESPECIALLY when:**
- Under time pressure (emergencies make guessing tempting)
- "Just one quick fix" seems obvious
- You've already tried multiple fixes
- Previous fix didn't work
- You don't fully understand the issue

## The Four Phases

Follow the phases in order, returning to investigation when evidence contradicts the hypothesis. Scale the investigation to the issue; simple bugs may need only a short reproduction and trace.

### Phase 1: Root Cause Investigation

**BEFORE attempting ANY fix:**

1. **Read Error Messages Carefully**
   - Don't skip past errors or warnings
   - They often contain the exact solution
   - Read stack traces completely
   - Note line numbers, file paths, error codes

2. **Reproduce Consistently**
   - Can you trigger it reliably?
   - What are the exact steps?
   - Does it happen every time?
   - If not reproducible → gather more data, don't guess

3. **Check Recent Changes**
   - What changed that could cause this?
   - Git diff, recent commits
   - New dependencies, config changes
   - Environmental differences

4. **Gather Evidence in Multi-Component Systems**

   For systems such as CI → build → signing or API → service → database:
   - Start with existing errors, traces, and a specific question about where behavior diverges.
   - Inspect the suspected boundary; add instrumentation only if existing evidence cannot answer the question. Expand the trace as evidence requires, not at every layer by default.
   - Capture the minimum useful metadata: state transitions, presence flags, types, or safe correlation IDs. Do not dump payloads, credentials, environment variables, or sensitive paths.
   - Keep diagnostic instrumentation temporary, narrowly scoped, and bounded in volume and duration. Use safe reproductions; avoid repeating destructive or externally visible operations just to collect logs.
   - Remove probes after investigation. Retain telemetry only for a concrete operational need, with redaction, access controls, and bounded volume/retention.

   **Example: test whether a signing identity reaches the build script.** Run this temporary probe at the workflow handoff and build entry, not across every component:
   ```bash
   # Disable shell tracing around secret-related diagnostics.
   set +x
   if [ -n "${IDENTITY:-}" ]; then
     printf '%s\n' 'signing_identity_present=true'
   else
     printf '%s\n' 'signing_identity_present=false'
   fi
   ```

   If present at the handoff but absent at build entry, investigate propagation there. Presence alone does not establish credential validity or signing access.

5. **Trace Data Flow**

   **WHEN error is deep in call stack:**

   See `root-cause-tracing.md` in this directory for the complete backward tracing technique.

   **Quick version:**
   - Where does bad value originate?
   - What called this with bad value?
   - Keep tracing up until you find the source
   - Fix at source, not at symptom

### Phase 2: Pattern Analysis

**Find the pattern before fixing:**

1. **Find Working Examples**
   - Locate similar working code in same codebase
   - What works that's similar to what's broken?

2. **Compare Against References**
   - Read the relevant reference implementation and its contracts, not just an isolated snippet
   - Understand dependencies and assumptions before applying the pattern

3. **Identify Differences**
   - What's different between working and broken?
   - Compare differences that could explain the failure; expand if the hypothesis does not hold
   - Don't assume "that can't matter"

4. **Understand Dependencies**
   - What other components does this need?
   - What settings, config, environment?
   - What assumptions does it make?

### Phase 3: Hypothesis and Testing

**Scientific method:**

1. **Form Single Hypothesis**
   - State clearly: "I think X is the root cause because Y"
   - Write it down
   - Be specific, not vague

2. **Test Minimally**
   - Make the SMALLEST possible change to test hypothesis
   - One variable at a time
   - Don't fix multiple things at once

3. **Verify Before Continuing**
   - Did it work? Yes → Phase 4
   - Didn't work? Form NEW hypothesis
   - DON'T add more fixes on top

4. **When You Don't Know**
   - Say "I don't understand X"
   - Don't pretend to know
   - Ask for help
   - Research more

### Phase 4: Implementation

**Fix the root cause, not the symptom:**

1. **Create Failing Test Case**
   - Simplest possible reproduction
   - Automated test if possible
   - One-off test script if no framework
   - Observe the relevant failure before fixing when feasible. If reproduction is unavailable or the implementation already exists, preserve valid work, state the limitation, and use the strongest feasible verification.
   - Use the `test-driven-development` skill for writing proper failing tests

2. **Implement Single Fix**
   - Address the root cause identified
   - ONE change at a time
   - No "while I'm here" improvements
   - No bundled refactoring
   - For invalid data, validate at the owning trust boundary or invariant. Add another check only for a distinct failure mode, such as an independent caller or state changing after validation; see `defense-in-depth.md`.
   - Do not duplicate checks through internal pass-through calls or add test-environment branches to production without a concrete safety requirement. Prefer fixture isolation and test-harness guards for test-only risks.

3. **Verify Fix**
   - Test passes now?
   - No other tests broken?
   - Issue actually resolved?
   - Where feasible, verify the original reproduction fails before the fix and passes after it; test each distinct retained safety requirement, not every call layer. Do not claim a reproduction or regression check that was not observed.
   - Remove temporary diagnostics and confirm no sensitive data remains in retained logs or artifacts.

4. **If Fix Doesn't Work**
   - Return to Phase 1 with the new evidence rather than stacking speculative fixes.
   - Repeated failures warrant reviewing assumptions and architecture, not an automatic refactor based on an attempt count.

5. **Reassess Architecture When Evidence Warrants**

   **Pattern indicating architectural problem:**
   - Each fix reveals new shared state/coupling/problem in different place
   - Fixes require "massive refactoring" to implement
   - Each fix creates new symptoms elsewhere

   **Questions to investigate:**
   - Is this pattern fundamentally sound?
   - Are we "sticking with it through sheer inertia"?
   - Should we refactor architecture vs. continue fixing symptoms?

   Discuss architectural changes with your human partner before expanding scope. Repeated failures are evidence to investigate, not proof that the architecture is wrong.

## Investigation Warning Signs

Return to evidence gathering when a proposed fix rests on an unverified assumption, several changes obscure which hypothesis is being tested, or each attempt creates a different failure. If a collaborator challenges an assumption, verify it directly rather than defending the proposed fix.

## Quick Reference

| Phase | Key Activities | Success Criteria |
|-------|---------------|------------------|
| **1. Root Cause** | Read errors, reproduce, check changes, gather evidence | Understand WHAT and WHY |
| **2. Pattern** | Find working examples, compare | Identify differences |
| **3. Hypothesis** | Form theory, test minimally | Confirmed or new hypothesis |
| **4. Implementation** | Create test, fix, verify | Bug resolved, tests pass |

## When Process Reveals "No Root Cause"

Environmental, timing-dependent, and external failures still have causes. If the available evidence cannot establish one:

1. Document the reproduction attempts, evidence, and remaining uncertainty.
2. Add handling only for demonstrated failure modes (for example, bounded retries when the operation is safe to repeat, a timeout, or an actionable error).
3. Use targeted, safe diagnostics for the unresolved question and verify any mitigation separately. Do not describe mitigation as a confirmed root-cause fix.

## Supporting Techniques

These techniques are part of systematic debugging and available in this directory:

- **`root-cause-tracing.md`** - Trace bugs backward through call stack to find original trigger
- **`defense-in-depth.md`** - Choose validation at distinct trust boundaries and invariants based on concrete failure modes
- **`condition-based-waiting.md`** - Replace arbitrary timeouts with condition polling
