---
applyTo: "**"
---

# General Software Engineering Principles

## Context
These guidelines establish the core philosophy for development in this repository. They take precedence over language-specific rules and focus on creating code that is **simple, maintainable, and robust**.

## Core Philosophies

### 1. Simplicity (KISS)
- **Simple is better than complex.** Avoid unnecessary abstraction layers or "clever" solutions that are hard to read.
- **Readable code is reliable code.** Write code primarily for the human reader, not just the compiler/interpreter. If the implementation is hard to explain, it is a bad idea.
- **Reduce cognitive load.** Break complex logic into smaller, self-contained components that can be understood in isolation.

### 2. You Aren't Gonna Need It (YAGNI)
- **Do not over-engineer.** Solve the problem currently at hand. Do not add functionality, parameters, or abstractions for hypothetical future use cases.
- **Iterative Complexity.** Start with the simplest baseline design and introduce complexity (e.g., caching, complex patterns) only when constraints explicitly demand it.

### 3. Don't Repeat Yourself (DRY)
- **Single Source of Truth.** Ensure that every piece of knowledge or logic has a single, unambiguous representation within the system.
- **Abstraction vs. Duplication.** If logic is identical and conceptually related, abstract it. However, be wary of coupling unrelated components just because they happen to look similar (incidental duplication).

## SOLID Design Principles
Apply these principles to manage dependencies and ensure the system remains easy to extend.

- **Single Responsibility Principle (SRP):** A class or module should have one, and only one, reason to change. Separate distinct concerns (e.g., business logic vs. I/O) into different components.
- **Open/Closed Principle (OCP):** Software entities should be open for extension but closed for modification. Implement new behavior by adding new code rather than changing existing, tested code.
- **Liskov Substitution Principle (LSP):** Subtypes must be substitutable for their base types without altering the correctness of the program.
- **Interface Segregation Principle (ISP):** Clients should not be forced to depend on interfaces they do not use. Prefer many small, specific interfaces over a single large one.
- **Dependency Inversion Principle (DIP):** Depend on abstractions (interfaces/contracts), not on concrete details. High-level modules should not import low-level modules directly.

## The "Always, Ask, Never" Framework

### ✅ Always
- **Fail Fast:** Validate inputs and state early. Crash loudly rather than corrupting data silently.
- **Use Meaningful Names:** Names should answer *why* it exists and *what* it does.

### ⚠️ Ask First
- **Before Adding Dependencies:** Every external library adds maintenance burden and security risk.
- **Before Optimizing:** "Premature optimization is the root of all evil." Measure first.

### 🚫 Never
- **Never Swallow Errors:** Empty `catch`/`except` blocks hide bugs and make debugging impossible.
- **Never Use Magic Numbers:** Replace `86400` with `SECONDS_IN_DAY`.

## Universal Coding Standards

### Functions
- **Small:** A function should fit on a single screen.
- **Pure (Preferred):** Avoid side effects where possible. Output should depend only on input.

### Comments
Comments should explain the **intent** and **reasons** behind decisions—not describe what the code does or how it was changed.

- **Document "Why":** Explain the reasoning, edge cases, or business rules that aren't obvious from the code itself.
- **Avoid Redundant Comments:** If the code is self-explanatory, no comment is needed.
- **Never Write Changelog Comments:** Do not describe what was modified or refactored. These comments are useless to future readers who don't know (or care about) the previous implementation.

**Bad:**
```python
total = sum(items)  # now uses built-in sum function instead of iterating manually
```

```javascript
const total = prices.reduce((a, b) => a + b, 0);  // refactored from for-loop
```

**Good:**
```python
total = sum(items)  # No comment needed—code is self-explanatory
```

```python
# Timeout set to 30s to match the upstream API's max response time (see JIRA-1234)
TIMEOUT_SECONDS = 30
```

## Examples

### Readability
**Bad:**
```javascript
// What does 86400 mean?
setTimeout(fn, 86400 * 1000);
```

**Good:**
```javascript
const MILLISECONDS_IN_DAY = 24 * 60 * 60 * 1000;
setTimeout(fn, MILLISECONDS_IN_DAY);
```

### Error Handling
**Bad:**
```python
try:
    do_something()
except:
    pass # Silent failure
```

**Good:**
```python
try:
    do_something()
except ValueError as e:
    log.error(f"Invalid input: {e}")
    raise
```
