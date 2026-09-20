---
name: github-actions
description: ALWAYS use this skill when creating or modifying GitHub Actions workflows, reusable actions, CI/CD triggers, secrets, or deployment jobs.
---

# GitHub Actions Standards

## Workflow Defaults

- Use descriptive workflow and job names.
- Set top-level `permissions: contents: read` by default and grant additional permissions only per job when needed.
- Use `concurrency` for deployments and single-flight workflows.
- Pin actions to major versions at minimum; use commit SHAs for high-risk or security-sensitive workflows.
- Use versioned action refs or commit SHAs for all actions.

## Secrets And Identity

- Use GitHub Secrets or environment secrets for sensitive values.
- Prefer OIDC federation over long-lived cloud credentials.
- Keep secrets, tokens, and raw environment dumps out of logs.
- For `pull_request_target`, keep fork checkout and script execution separated from privileged credentials.

## Build Quality

- Use cache keys based on lockfiles and relevant platform inputs.
- Pin toolchain versions.
- Keep matrix jobs focused on meaningful compatibility coverage.
- Upload artifacts with explicit names and retention where artifacts matter.
- Use `actions/checkout` with `fetch-depth: 1` by default. Use full history for release, changelog, version, or `git describe` workflows.

## Deployment

- Use GitHub environments for protected deployments.
- Make deployment jobs depend on successful build/test jobs.
- Prefer progressive rollout and clear rollback commands for production changes.

## Verification

- Validate changed workflows with the available local or CI syntax tooling.
- Check permissions, triggers, secrets, and fork behavior after workflow changes.
