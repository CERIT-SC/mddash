---
description: 'Python coding conventions and guidelines'
applyTo: '**/*.py'
---

# Python Coding Conventions

## Python Instructions
- Write clear and concise comments for each function.
- Ensure functions have descriptive names and include type hints.
- Provide docstrings following PEP 257 conventions and using the Google style.
- Prefer using built-in python types (e.g., `list[str]`, `dict[int, object]`) unless there is a need to use `typing`.
- Break down complex functions into smaller, more manageable functions.
- Always import necessary modules at the beginning of the file unless there is a specific reason to do otherwise.

## General Instructions
- Always prioritize readability and clarity.
- For algorithm-related code, include short explanations of the approach used.
- Write code with good maintainability practices, including comments on why certain design decisions were made.
- Do not write comments on code that is self-explanatory.
- Handle edge cases and write clear exception handling.
- Use consistent naming conventions and follow language-specific best practices.
- Write concise, efficient, and idiomatic code that is also easily understandable.

## Code Style and Formatting
- Follow the **PEP 8** style guide for Python.
- Do not bother about line length unless it exceeds 120 characters.
- Place function and class docstrings immediately after the `def` or `class` keyword.
- Use blank lines to separate functions, classes, and code blocks where appropriate.

## Edge Cases and Testing
- Do not write any tests unless explicitly asked.
- Include test cases for critical paths of the application.
- Account for common edge cases like empty inputs, invalid data types, and large datasets.
- Include comments for edge cases and the expected behavior in those cases.
- Write unit tests for functions and document them with docstrings explaining the test cases.

## Example of Proper Documentation

```python
from math import pi

def calculate_area(radius: float) -> float:
    """
    Calculate the area of a circle given the radius.

    Args:
        radius (float): The radius of the circle.
    Returns:
        float: The area of the circle, calculated as π * radius^2.
    Raises:
        ValueError: If the radius is negative.
    """
    return pi * radius ** 2
```
