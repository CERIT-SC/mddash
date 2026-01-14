---
applyTo: "**/*.py"
---

# Python Development Guidelines

These instructions focus on **idiomatic Python implementation details**.

## 1. Modern Idioms & Control Flow
Write code that leverages modern Python (3.10+) features for readability and safety.

### Path Handling
Use `pathlib` instead of `os.path` for filesystem operations. It offers an object-oriented interface and better cross-platform compatibility.

**Bad:**
```python
import os
path = os.path.join(data_dir, "file.txt")
if os.path.exists(path):
    ...
```

**Good:**
```python
from pathlib import Path
path = Path(data_dir) / "file.txt"
if path.exists():
    ...
```

### String Formatting
Always use **f-strings** for string interpolation. They are faster and more readable than `.format()` or `%` formatting.

**Bad:**
```python
print("Hello, %s" % user)
print("Hello, {}".format(user))
```

**Good:**
```python
print(f"Hello, {user}")
```

### Comprehensions
Use list/dict comprehensions for simple transformations instead of `map()` or loops.

**Bad:**
```python
users = []
for u in user_list:
    if u.active:
        users.append(u.name)
```

**Good:**
```python
users = [u.name for u in user_list if u.active]
```

### Iteration
Use `enumerate()` instead of `range(len())`. Use `zip()` to iterate multiple sequences simultaneously.

**Bad:**
```python
for i in range(len(items)):
    print(i, items[i])
```

**Good:**
```python
for i, item in enumerate(items):
    print(i, item)
```

### Structural Pattern Matching (Python 3.10+)
Use `match`/`case` statements for complex conditional logic involving type checks or value unpacking. Avoid long `if`/`elif` chains when matching against patterns.

**Bad:**
```python
def handle_response(response):
    if isinstance(response, dict) and "error" in response:
        return f"Error: {response['error']}"
    elif isinstance(response, dict) and "data" in response:
        return response["data"]
    elif response is None:
        return "No response"
    else:
        return str(response)
```

**Good:**
```python
def handle_response(response):
    match response:
        case {"error": msg}:
            return f"Error: {msg}"
        case {"data": data}:
            return data
        case None:
            return "No response"
        case _:
            return str(response)
```

## 2. Type Safety & Documentation
Python is dynamically typed, but we enforce strict static analysis to catch bugs early.

### Strict Typing
Annotate all function arguments and return values. Avoid `Any`.

Use **built-in generics** (PEP 585) instead of importing from `typing`. Since Python 3.9+, `list`, `dict`, `tuple`, `set`, and `type` are directly subscriptable.

**Bad:**
```python
from typing import List, Dict, Optional  # ❌ Deprecated imports

def process(data: Dict[str, Any]) -> Optional[int]:
    return data.get("id")
```

**Good:**
```python
from typing import Any  # Only import types not available as builtins

def process(data: dict[str, Any]) -> int | None:
    return data.get("id")
```

### Union Types (Python 3.10+)
Use the `|` operator instead of `Union` or `Optional` from the `typing` module.

**Bad:**
```python
from typing import Union, Optional

def find(id: int) -> Optional[User]:  # ❌ Verbose
    ...

def parse(value: Union[str, int]) -> str:  # ❌ Verbose
    ...
```

**Good:**
```python
def find(id: int) -> User | None:  # ✅ Clean
    ...

def parse(value: str | int) -> str:  # ✅ Clean
    ...
```

### Docstrings
Follow **Google Style** docstrings. Do not duplicate type information in the docstring; rely on type hints.

**Good:**
```python
def calculate_tax(price: float, rate: float) -> float:
    """Calculates the tax amount.

    Args:
        price: The base price.
        rate: The tax rate (0.0 to 1.0).

    Returns:
        The calculated tax.

    Raises:
        ValueError: If rate is negative.
    """
    return price * rate
```

## 3. Class Design

### Data Classes
Use `@dataclass` for classes that primarily store data. It automatically generates `__init__`, `__repr__`, and `__eq__`.

**Good:**
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class User:
    id: int
    name: str
```

### Properties
Use `@property` instead of Java-style getters and setters.

**Bad:**
```python
class Box:
    def get_width(self):
        return self._width
```

**Good:**
```python
class Box:
    @property
    def width(self):
        return self._width
```

### Magic Methods
Implement `__repr__` for all custom classes to ensure they are debuggable.

**Good:**
```python
def __repr__(self):
    return f"User(id={self.id}, name='{self.name}')"
```

## 4. Error Handling & Logging

### Specific Exceptions
Never catch `Exception` directly. Catch specific errors (e.g., `ValueError`, `KeyError`).

**Bad:**
```python
try:
    process()
except Exception:
    pass
```

**Good:**
```python
try:
    process()
except ValueError as e:
    logger.error(f"Invalid input: {e}")
```

### Logging vs Print
**Never** use `print()` in production code. Use the standard `logging` module.

**Bad:**
```python
print(f"Processing user {user_id}")
```

**Good:**
```python
import logging
logger = logging.getLogger(__name__)

logger.info("Processing user %s", user_id)
```

## 5. Configuration
**Never** hardcode secrets or configuration. Use Environment Variables.

**Bad:**
```python
DB_URL = "postgres://user:pass@localhost:5432/db"
```

**Good:**
```python
import os
DB_URL = os.environ.get("DB_URL")
```

## 6. Testing with Pytest
> ⚠️ **Note:** Only write tests when explicitly requested or if the codebase already includes tests.

### Fixtures
Use `pytest.fixture` for setup/teardown logic.

**Good:**
```python
@pytest.fixture
def db():
    conn = connect()
    yield conn
    conn.close()
```

### Parametrization
Use `@pytest.mark.parametrize` to test multiple inputs.

**Good:**
```python
@pytest.mark.parametrize("inp,out", [(1, 2), (2, 4)])
def test_double(inp, out):
    assert double(inp) == out
```

## 7. Resource Management
Always use Context Managers (`with` statements) to ensure resources are properly released.

**Bad:**
```python
conn = db.connect()
result = conn.execute(query)
conn.close()  # ❌ Won't run if execute() raises an exception
```

**Good:**
```python
with db.connect() as conn:
    result = conn.execute(query)
# Connection is always closed, even on exception
```

**Good (file I/O with pathlib):**
```python
from pathlib import Path

file = Path("file.txt")
data = file.read_text()  # Simple read, auto-closes

# For larger files or line-by-line processing:
with file.open() as f:
    for line in f:
        process(line)
```

## 8. Critical Anti-Patterns

### Mutable Default Arguments
**Never** use mutable objects (lists, dicts) as default arguments.

**Bad:**
```python
def append(item, list=[]):
    list.append(item)
```

**Good:**
```python
def append(item, list=None):
    if list is None:
        list = []
    list.append(item)
```

### Wildcard Imports
**Never** use `from module import *`. It pollutes the namespace.

### Inline Imports
**Never** place imports inside functions. Imports belong at the top of the file.

### Unbounded Loops
> ⚠️ **Warning:** Avoid `while True` in production code without safeguards.

Unbounded loops can cause infinite execution, resource exhaustion, or hung processes. Always include a **maximum iteration limit** or **timeout** for retry/polling logic.

**Bad:**
```python
while True:  # ❌ Can hang forever
    result = fetch_data()
    if result:
        break
    time.sleep(1)
```

**Good:**
```python
MAX_ATTEMPTS = 10

for attempt in range(MAX_ATTEMPTS):
    result = fetch_data()
    if result:
        break
    time.sleep(1)
else:
    raise TimeoutError(f"Failed after {MAX_ATTEMPTS} attempts")
```

> **Exception:** `while True` is acceptable for **intentional** infinite loops like event loops, servers, or daemons—but these should handle graceful shutdown signals.
