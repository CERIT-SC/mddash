---
name: commit
description: Use for every commit. Creates the commit with a concise message, issue references, and model attribution.
---

Inspect the changes, compose the message, and create a commit.

# Commit Messages

- If on `main` or `master`, ask whether to commit there or create a feature branch, then follow the user's choice.
- Match recent repository commit style and keep the subject short and specific.
- Use a body only for non-obvious context the subject and diff cannot show; keep it brief.
- End every model-created commit with `Co-Authored-By: <model name> <model creator email>`.
- Include `Fixes <issue>` when resolving a known issue; use `Refs <issue>` when it remains open.
- Replace customer names, user data, and PII with the technical symptom and issue ID.
- Split changes into multiple commits if they are unrelated.
