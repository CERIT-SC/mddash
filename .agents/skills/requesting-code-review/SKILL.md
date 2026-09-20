---
name: requesting-code-review
description: Use for requested reviews, substantial or high-risk changes, or a project-required pre-merge review. Routine edits do not need an independent reviewer by default.
---

# Requesting Code Review

Use independent review when it can catch meaningful defects. Do not create a review cycle for every small task or subagent output.

## Request

- Give an available review-capable subagent the requirements, change scope, relevant constraints, and verification results.
- Use [code-reviewer.md](code-reviewer.md) as the prompt template. Review is read-only.
- Identify the actual comparison base; do not assume `HEAD~1` covers the work. Include staged, unstaged, and untracked changes when reviewing unfinished work.
- Keep context focused on the contract and evidence, not the implementer's reasoning history.

## Act On Findings

- Validate each finding against the code and requirements before changing anything.
- Fix confirmed correctness, security, and regression issues within scope. Escalate consequential requirement changes instead of silently implementing them.
- Treat stylistic preferences, speculative scalability, and unrelated improvements as nonblocking.
- Recheck affected behavior after fixes. Repeat review only when material changes or unresolved findings justify it.

For substantial changes with unnecessary complexity, consider the `simplicity` subagent. Do not dispatch it in addition to a reviewer already checking the same concerns unless an independent pass has a clear benefit.
