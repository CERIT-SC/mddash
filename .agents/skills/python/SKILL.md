---
name: python
description: ALWAYS use this skill when writing, modifying, reviewing, or testing Python code (3.10+), its packaging, or its dependencies.
---

# Python Standards

## Language Defaults

- Target Python 3.10+ idioms unless the project declares an older runtime.
- Use `pathlib` for filesystem paths.
- Use f-strings for interpolation.
- Use `dataclasses` or typed models for structured data instead of loose dictionaries.

## Typing

- Add type hints to public functions and non-trivial internal functions.
- Use built-in generics such as `list[str]` and `dict[str, int]`.
- Use `X | None` and `A | B` unions.
- Keep casts near the untyped boundary and validate external data before trusting it.

## Structure

- Always keep imports at module top.
- Local imports are acceptable only for optional dependencies, expensive imports, cycle breaks, or platform-specific code; make the reason clear in the surrounding code.
- Keep functions small and side effects explicit.
- Prefer dependency injection for I/O boundaries when it improves testability.
- Use Google-style docstrings for public modules, classes, and functions when documentation is needed.

## Errors And Resources

- Catch specific exceptions and preserve context in logs or raised errors.
- Use context managers for files, network clients, database sessions, locks, and temporary resources.
- Use the `logging` module for runtime diagnostics.
- Use `None` sentinels or immutable defaults for optional collection arguments.

## Tests

- Follow the project's existing test strategy.
- Add or update regression tests when changing behavior or fixing bugs.
- Use fixtures and parametrization to keep test setup readable and deterministic.

## Verification

- Run the focused test, formatter/linter, or type checker that matches the changed area.
