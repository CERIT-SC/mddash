---
applyTo: "**"
---
# General Software Engineering Principles

Core philosophy for development: **simple, maintainable, and robust** code.

<context>
These guidelines take precedence over language-specific rules. They establish the foundational principles that all code should follow.
</context>
<best_practices>
<philosophies>
- **Simplicity (KISS):** Prefer clear and straightforward solutions over clever complexity.
	- Choose designs that are easy to understand, reason about, and debug.
	- Break complex behavior into smaller, focused units with explicit responsibilities.
	- Reduce cognitive load for future maintainers by favoring readability over novelty.
	- Introduce abstraction only when it clearly improves clarity or reuse.
- **You Aren't Gonna Need It (YAGNI):** Build for current requirements, not speculative future needs.
	- Solve today’s validated problem before adding optional flexibility.
	- Avoid premature generalization, plugin architectures, and extension points without real demand.
	- Add complexity incrementally as constraints become concrete.
	- Prefer reversible decisions early so the system can evolve safely.
- **Don't Repeat Yourself (DRY):** Keep each rule, behavior, and business concept in one source of truth.
	- Eliminate duplicated logic that can diverge over time and create inconsistent behavior.
	- Centralize shared policies, validations, and domain rules behind clear interfaces.
	- Abstract only conceptually related duplication; avoid forced coupling of unrelated code.
	- Prioritize consistency of meaning, not just deduplication of lines.
</philosophies>
<SOLID>
- **SRP:** Each module should have one clear responsibility.
- **OCP:** Extend behavior through composition/extension, not risky modification.
- **LSP:** Subtypes must behave correctly wherever base types are expected.
- **ISP:** Keep interfaces focused; avoid forcing consumers to depend on unused methods.
- **DIP:** Depend on abstractions and stable contracts, not volatile implementation details.
</SOLID>
<problem_framing>
- Start from the problem and desired outcome before choosing tools or patterns.
- Define constraints and success criteria before implementation.
- Solve root causes instead of treating symptoms.
</problem_framing>
<design_and_architecture>
- Keep modules cohesive and loosely coupled; avoid hidden cross-module dependencies.
- Make boundaries explicit between domain logic, infrastructure, and presentation layers.
- Favor composition and clear contracts over deep inheritance trees.
</design_and_architecture>
<code_quality>
- Write readable code with meaningful names, explicit intent, and predictable behavior.
- Keep functions and components focused on one responsibility.
- Prefer explicit data flow over implicit side effects.
</code_quality>
<comments>
**Default to no comment.** Most code should be self-explanatory through naming and structure. Only add a comment when the code alone cannot convey *why* a decision was made.

**Litmus test:** If deleting the comment forces the reader to check git blame or ask a teammate to understand a non-obvious decision, keep it. Otherwise, delete it.

- **Document "Why":** Explain business constraints, edge cases, and non-obvious reasons — not what the code does.
- **Capture Non-Obvious Tradeoffs:** Record rationale when alternatives were considered or when the obvious approach was intentionally avoided.
- **Never Write Changelog Comments:** Do not describe what you just changed or why you changed it. The comment must make sense to a reader who has no knowledge of the change history.
- **Keep comments short.** One line is ideal. Two lines is the maximum.

**Bad** — restates what the code says, or reads like a changelog:
```python
# Sort users by last login date
users.sort(key=lambda u: u.last_login)

# Check if the user is an admin
if user.role == Role.ADMIN:

# Changed from 5 to 10 because the old value was too low
MAX_BATCH_SIZE = 10

# Replaced threading with asyncio for better performance
await process_batch(items)

# Removed the old validation logic and added schema-based validation
schema.validate(payload)
```

**Good** — explains something the code *cannot* tell you:
```python
# Cold accounts fail fast — process them first to free up batch slots
users.sort(key=lambda u: u.last_login)

# Admins bypass rate limiting per contract with enterprise clients
if user.role == Role.ADMIN:

# Benchmarked: 10 saturates the connection pool without triggering OOM
MAX_BATCH_SIZE = 10

# no comment needed — self-explanatory
await process_batch(items)

# no comment needed — self-explanatory
schema.validate(payload)
```
</comments>
<correctness_and_reliability>
- Validate assumptions at boundaries and fail fast on invalid inputs.
- Handle errors deliberately: detect, report, and recover or fail safely.
- Keep state transitions explicit to avoid ambiguous system behavior.
- Design for graceful degradation during partial failures.
</correctness_and_reliability>
<testing_and_verification>
- Verify behavior at the right level: unit, integration, and end-to-end as needed.
- Prioritize tests around critical business flows and regression-prone paths.
- Keep tests deterministic and aligned with real usage patterns.
- Treat CI checks as a quality gate, not an afterthought.
</testing_and_verification>
<maintainability_and_evolution>
- Remove dead code, outdated docs, and accidental complexity continuously.
- Prefer iterative refactoring over large rewrites unless justified.
- Keep docs and contracts in sync with actual behavior.
- Use shared conventions so teams can move across modules safely.
</maintainability_and_evolution>
<security_and_operability>
- Treat security, privacy, and compliance as baseline requirements.
- Never hardcode secrets; use managed configuration and least privilege.
- Ensure systems are observable with logs, metrics, and actionable errors.
- Design operations to be safe, repeatable, and reversible when possible.
</security_and_operability>
</best_practices>
<boundaries>
- ✅ **Always:** Solve the real problem before optimizing implementation details
- ✅ **Always:** Keep behavior explicit, testable, and observable
- ✅ **Always:** Document decisions that affect future changes
- ⚠️ **Ask:** Before introducing major dependencies or architectural changes
- ⚠️ **Ask:** Before making irreversible or high-impact operational changes
- 🚫 **Never:** Trade long-term maintainability for short-term convenience without explicit agreement
- 🚫 **Never:** Hide errors, risks, or uncertainty
- 🚫 **Never:** Compromise security, data safety, or correctness for speed
</boundaries>
