---
description: 'Python coding conventions and guidelines'
applyTo: '**/*.py'
---

# Python Coding Conventions

## Core Philosophy
- **Modern & Idiomatic**: Use Python 3.10+ features and modern standard libraries.
- **Type Safe**: Strict type hinting is mandatory for all function signatures and class attributes.
- **Readable**: Code should be self-documenting; comments explain *why*, not *what*.
- **Robust**: Handle errors explicitly; avoid silent failures.

## Modern Python Standards
- **Type Hinting**:
  - Use built-in generics (`list[str]`, `dict[str, int]`) instead of `typing.List`.
  - Use the union operator (`str | int`) instead of `typing.Union`.
  - Use `str | None` instead of `typing.Optional`.
- **Data Structures**:
  - Prefer `dataclasses` or `pydantic.BaseModel` over plain dictionaries for structured data.
  - Use `NamedTuple` for simple immutable data structures.
- **String Formatting**:
  - Always use **f-strings** (`f"{var}"`) instead of `.format()` or `%` formatting.
- **Path Handling**:
  - Use `pathlib.Path` for all file system operations. Avoid `os.path`.
- **Control Flow**:
  - Use `match/case` for complex conditional logic (Python 3.10+).
  - Use `contextlib.suppress` for ignoring specific exceptions.

## Code Structure & Style
- **Imports**:
  - Group imports: Standard Library, Third Party, Local Application.
  - Place all imports at the top of the file.
  - Use absolute imports for project modules (e.g., `from src.utils import helper`).
- **Naming**:
  - `snake_case` for functions, variables, and file names.
  - `PascalCase` for classes and exceptions.
  - `UPPER_CASE` for constants.
  - Prefix private members with `_`.
- **Formatting**:
  - Follow **PEP 8**.
  - Max line length: **120 characters**.
  - Use trailing commas in multi-line lists/dicts/function calls.

## Error Handling & Safety
- **Exceptions**:
  - Create custom exception classes for domain-specific errors.
  - **NEVER** use bare `except:` or `except Exception:` without re-raising or logging.
  - Use `try/except/else/finally` blocks appropriately.
- **Resources**:
  - Always use context managers (`with` statement) for file I/O, locks, and connections.

## Documentation
- **Docstrings**:
  - Use **Google Style** docstrings for all public modules, classes, and functions.
  - Include `Args`, `Returns`, and `Raises` sections.
- **Comments**:
  - Do not comment obvious code.
  - Use comments to explain complex algorithmic decisions or business logic.

## Testing (Only when requested)
- If asked to write tests, use **pytest**.
- Use `conftest.py` for shared fixtures.
- Use `@pytest.mark.parametrize` for data-driven tests.
- Do not mock internal implementation details; test public interfaces.

## Examples

### ✅ Good: Modern & Clean
```python
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class UserConfig:
    """Data class to hold user configuration."""

    username: str
    retries: int = 3


def load_config(config_path: Path) -> UserConfig:
    """
    Load user configuration from a JSON file.

    Args:
        config_path: Path to the configuration file.

    Returns:
        UserConfig: The parsed configuration object.

    Raises:
        FileNotFoundError: If the config file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return UserConfig(**data)
```

### ❌ Bad: Outdated & Unsafe
```python
def load_config(path): # No type hints
    import os # Import inside function
    if os.path.exists(path): # Old os.path
        f = open(path) # No context manager (resource leak)
        data = json.load(f)
        return data # Returns dict, not structured object
    else:
        return None # Returns None instead of raising error
```
