---
applyTo: "**/*.py"
---
<context>
These guidelines cover Python-specific best practices, idioms, and anti-patterns.
</context>
<best_practices>
<idioms>
### Path Handling
Use `pathlib` instead of `os.path`.

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
Use **f-strings** for interpolation.

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
Use list/dict comprehensions for simple transformations.

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
Use `enumerate()` instead of `range(len())`. Use `zip()` for parallel iteration.

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

### Pattern Matching
Use `match`/`case` for complex conditional logic.

**Bad:**
```python
def handle(response):
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
def handle(response):
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
</idioms>
<typing>
### Built-in Generics (PEP 585)
Use built-in types instead of `typing` imports.

**Bad:**
```python
from typing import List, Dict, Optional

def process(data: Dict[str, Any]) -> Optional[int]:
    return data.get("id")
```

**Good:**
```python
from typing import Any

def process(data: dict[str, Any]) -> int | None:
    return data.get("id")
```

### Union Types (PEP 604)
Use `|` instead of `Union` or `Optional`.

**Bad:**
```python
from typing import Union, Optional

def find(id: int) -> Optional[User]: ...
def parse(value: Union[str, int]) -> str: ...
```

**Good:**
```python
def find(id: int) -> User | None: ...
def parse(value: str | int) -> str: ...
```

### Docstrings
Follow **Google Style**. Do not duplicate type info—rely on hints.

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
</typing>
<classes>
### Data Classes
Use `@dataclass` for data containers. It automatically has `__init__`, `__repr__`, and `__eq__`.

**Good:**
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class User:
    id: int
    name: str
```

### Properties
Use `@property` instead of getters/setters.

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
Implement `__repr__` for debuggability.

**Good:**
```python
def __repr__(self):
    return f"User(id={self.id}, name='{self.name}')"
```
</classes>
<error_handling>
### Specific Exceptions
Catch specific errors, not bare `Exception`.

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
    logger.exception("Invalid input")  # Stack trace included automatically
```

### Logging
Use `logging`, not `print()`.

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
</error_handling>
<resources>
### Context Managers
Use `with` statements for resource cleanup.

**Bad:**
```python
conn = db.connect()
result = conn.execute(query)
conn.close()  # Won't run if execute() raises
```

**Good:**
```python
with db.connect() as conn:
    result = conn.execute(query)
```

### File I/O
Use `pathlib` for file operations.

**Good:**
```python
from pathlib import Path

file = Path("file.txt")
data = file.read_text()

# For larger files:
with file.open() as f:
    for line in f:
        process(line)
```
</resources>
<anti_patterns>
### Mutable Default Arguments

**Bad:**
```python
def append(item, items=[]):
    items.append(item)
    return items
```

**Good:**
```python
def append(item, items=None):
    if items is None:
        items = []
    items.append(item)
    return items
```

### Unbounded Loops

**Bad:**
```python
while True:
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

> **Exception:** `while True` is acceptable for intentional infinite loops (event loops, servers) with graceful shutdown handling.

### Hardcoded Configuration

**Bad:**
```python
DB_URL = "postgres://user:pass@localhost:5432/db"
```

**Good:**
```python
import os
DB_URL = os.environ.get("DB_URL")
```

> **Exception:** Constants that are truly constant and not environment-specific (e.g., mathematical constants).

</anti_patterns>

<testing>
> ⚠️ Only write tests when explicitly requested or if the codebase already includes tests.

### Fixtures
```python
@pytest.fixture
def db():
    conn = connect()
    yield conn
    conn.close()
```

### Parametrization
```python
@pytest.mark.parametrize("inp,out", [(1, 2), (2, 4)])
def test_double(inp, out):
    assert double(inp) == out
```
</testing>
</best_practices>
<boundaries>
- ✅ **Always:** Type hints on all function signatures
- ✅ **Always:** `pathlib` for filesystem operations
- ✅ **Always:** f-strings for formatting
- ✅ **Always:** Context managers for resources
- ✅ **Always:** `logging` module in production
- ⚠️ **Ask:** Before adding dependencies to `requirements.txt`
- 🚫 **Never:** Hardcode secrets or config
- 🚫 **Never:** Mutable default arguments
- 🚫 **Never:** Wildcard imports (`from x import *`)
- 🚫 **Never:** Imports inside functions
</boundaries>
