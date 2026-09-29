---
name: pr
description: Use for every PR. Sets naming, summary, issue, and attribution conventions.
---

Match repo naming; otherwise use `type/short-topic` for branch and `type: concise summary` for title.

- Always find and follow the repo's PR template if present (`.github/pull_request_template.md`). Keep content brief: what, why, non-obvious risks; no diff narration.
- Known GitHub issue: `Fixes #123` if resolved, otherwise `Refs #123`. Never invent links or closure.
- Omit commands and results CI already shows; include useful manual checks or gaps only.
- End with `Prepared with <agent name> (<model name>).`
