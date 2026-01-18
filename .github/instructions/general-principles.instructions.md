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
### Simplicity (KISS)
- **Simple is better than complex.** Avoid unnecessary abstraction or "clever" solutions.
- **Readable code is reliable code.** Write for the human reader first.
- **Reduce cognitive load.** Break complex logic into smaller, self-contained components.

### You Aren't Gonna Need It (YAGNI)
- **Do not over-engineer.** Solve the problem at hand, not hypothetical future ones.
- **Iterative Complexity.** Start simple; add complexity only when constraints demand it.

### Don't Repeat Yourself (DRY)
- **Single Source of Truth.** Every piece of logic should have one unambiguous representation.
- **Abstraction vs. Duplication.** Abstract identical, conceptually related logic—but don't couple unrelated code just because it looks similar.
</philosophies>

<solid>
### SOLID Principles
- **SRP:** A class/module should have one reason to change.
- **OCP:** Open for extension, closed for modification.
- **LSP:** Subtypes must be substitutable for base types.
- **ISP:** Prefer small, specific interfaces over large ones.
- **DIP:** Depend on abstractions, not concrete details.
</solid>

<functions>
### Functions
- **Small:** A function should fit on a single screen.
- **Pure (Preferred):** Avoid side effects; output depends only on input.
</functions>

<comments>
### Comments
Comments should explain the **intent** and **reasons** behind decisions—not describe what the code does or how it was changed.

- **Document "Why":** Explain the reasoning, edge cases, or business rules that aren't obvious from the code itself.
- **Avoid Redundant Comments:** If the code is self-explanatory, no comment is needed.
- **Never Write Changelog Comments:** Do not describe what was modified or refactored. These comments are useless to future readers who don't know (or care about) the previous implementation.

**Bad:**
```python
total = sum(items)  # now uses built-in sum function instead of iterating manually
```

**Good:**
```python
# Timeout set to 30s to match upstream API's max response time (see JIRA-1234)
TIMEOUT_SECONDS = 30
```
</comments>

<errors>
### Error Handling

**Bad:**
```python
try:
    do_something()
except:
    pass  # Silent failure
```

**Good:**
```python
try:
    do_something()
except ValueError as e:
    log.error(f"Invalid input: {e}")
    raise
```
</errors>

<naming>
### Naming & Magic Numbers

**Bad:**
```javascript
setTimeout(fn, 86400 * 1000);
```

**Good:**
```javascript
const MILLISECONDS_IN_DAY = 24 * 60 * 60 * 1000;
setTimeout(fn, MILLISECONDS_IN_DAY);
```
</naming>

</best_practices>

<boundaries>
- ✅ **Always:** Fail fast—validate inputs early, crash loudly
- ✅ **Always:** Use meaningful names that explain *why* and *what*
- ⚠️ **Ask:** Before adding dependencies (maintenance burden, security risk)
- ⚠️ **Ask:** Before optimizing ("Premature optimization is the root of all evil")
- 🚫 **Never:** Swallow errors with empty catch blocks
- 🚫 **Never:** Use magic numbers—define named constants
</boundaries>
