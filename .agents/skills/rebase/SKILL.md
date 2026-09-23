---
name: rebase
description: Rebase a PR branch onto its base branch and resolve conflicts correctly. ALWAYS use this skill when rebasing or resolving merge conflicts.
---

Rebase = replay your commits on top of updated base. Not a merge. Not "pick a side".

## Mental Model

Each conflict = git stopped mid-replay of ONE of your commits. At that point:
- **Incoming (theirs)** = base branch — new ground truth, already merged, already reviewed
- **Current (yours)** = your commit being replayed — the intent you must preserve

Ask: "Given the base now looks like THIS, what should MY change look like?"
Never: "whose code wins?" — wrong question. Both sides may be partially correct.

## Flow

```bash
# 1. Find your base branch — check PR description or ask
git log --oneline HEAD..origin/<base-branch>   # see what you're rebasing

# 2. Fetch latest base
git fetch origin

# 3. Rebase
git rebase origin/<base-branch>

# 4. For each conflict:
#    - resolve file
#    - git add <file>
#    - git rebase --continue

# 5. After clean rebase — force push (history rewrote; --force-with-lease fails if remote has commits you haven't fetched)
git push --force-with-lease
```

## Conflict Resolution Rules

**Understand before editing.** Read both sides. Identify what the base changed and what your commit changed.

**Typical cases:**

| Situation | Right move |
|-----------|-----------|
| Base refactored a function your commit also touches | Apply your logic to the refactored version |
| Base deleted code your commit modifies | Evaluate if your change is still needed; if yes, find new home |
| Base added imports/lines near yours | Keep both — merge manually |
| Pure formatting conflict | Take base formatting, reapply your logic |

**When unsure what base change does:** read the commit that introduced it (`git log -p origin/<base-branch>`) before resolving.

## Database Migration Conflicts

Migrations are ordered and immutable once applied. Two rules:

1. **Sequence collision** (both branches added `0067_*.sql`) — keep both files, renumber yours to the next available number.
2. **Never edit an existing migration** — if it may already be applied anywhere, create a new compensating migration instead.

## Auto-Generated File Conflicts

Never hand-edit generated files (lock files, API clients, protobuf outputs, etc.). Accept either side to clear markers, run the project's generator, then `git add`.

## Abort If Wrong

```bash
git rebase --abort   # safe — resets to pre-rebase state
```

Abort when: conflict unclear, or you don't understand what the base change did.

## Anti-Patterns

- **Do not rebase directly onto remote base without fetching first** — replays onto stale history
- **Do not rebase shared branches** — rewrites history; only safe on your own PR branch
