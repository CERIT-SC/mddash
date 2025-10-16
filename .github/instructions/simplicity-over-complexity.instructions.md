---
description: 'Guidelines for GitHub Copilot to prioritize simple, readable code over complex implementations'
applyTo: '**'
---

# Simplicity Over Complexity Instructions

## Core Principle
**Write the simplest code that solves the problem. Use fewer lines when it maintains readability.**

## Key Rules

- Use standard library over custom implementations
- Prefer direct logic over abstractions
- Use guard clauses instead of deep nesting
- Avoid premature optimization and over-engineering
- Use language idioms that reduce code without obscuring intent
- Functions should do one thing and stay under 20 lines
- Max 3 levels of indentation, max 4 parameters

## Decision Framework

Before adding complexity, ask:
1. Is this solving a real problem today?
2. Will teammates understand this in 6 months?
3. Can I explain this in one sentence?

Add complexity only when it:
- Improves performance measurably (e.g., O(n²) → O(n))
- Handles actual production edge cases
- Meets security/compliance requirements

## Examples

### Direct Logic
```javascript
// Good
const activeUsers = users.filter(u => u.isActive);

// Bad: unnecessary abstraction
class UserFilter {
    constructor(predicate) { this.predicate = predicate; }
    apply(collection) { return new FilteredCollection(collection, this.predicate).toArray(); }
}
```

### Guard Clauses
```javascript
// Good
function processOrder(order) {
    if (!order?.items?.length) return;
    if (!order.user?.isVerified) return;
    // Process order
}

// Bad: deep nesting
function processOrder(order) {
    if (order) {
        if (order.items) {
            if (order.items.length > 0) {
                if (order.user?.isVerified) {
                    // Process order
                }
            }
        }
    }
}
```

### Simple Patterns
```javascript
// Good: simple module
export const config = {
    apiUrl: process.env.API_URL,
    timeout: 5000
};

// Bad: unnecessary singleton
class ConfigManager {
    private static instance: ConfigManager;
    static getInstance() { /* ... */ }
}
```

### API Design
```javascript
// Good
function fetchUsers(options = {}) {
    const { page = 1, limit = 20 } = options;
}

// Bad: 8+ individual parameters
function fetchUsers(page, limit, sortBy, sortOrder, filterBy, includeInactive, includeDeleted, expandRelations) { }
```

### Language Idioms (Use These)
```python
# Good: Pythonic
result = [x * 2 for x in numbers if x > 0]
user_dict = {u.id: u for u in users}

# Bad
result = []
for x in numbers:
    if x > 0:
        result.append(x * 2)
```

```javascript
// Good: Modern JS
const uniqueItems = [...new Set(items)];
const userMap = Object.fromEntries(users.map(u => [u.id, u]));

// Bad: manual implementation
const uniqueItems = items.filter((v, i, a) => a.indexOf(v) === i);
```

```typescript
// Good: Simple types
type User = { id: string; name: string; email: string };

// Bad: over-engineered
type User<T extends BaseEntity, K extends keyof T = keyof T> = Pick<T, K> & { metadata: Partial<EntityMetadata<T>> };
```

## Code Smells

Avoid:
- Functions >20 lines or >3 indentation levels
- Classes >10 methods
- Names with "Manager", "Handler", "Processor", "and", "or"
- Abstractions with only one implementation
- Complex error hierarchies (use error codes instead)

## Checklist

- [ ] Simplest solution that works?
- [ ] Uses language idioms appropriately?
- [ ] Understandable by junior developers?
- [ ] Can delete any code without losing functionality?
