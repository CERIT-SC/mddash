---
name: helm
description: ALWAYS use this skill when creating or modifying Helm charts, values, templates, chart tests, or Helm-managed Kubernetes deployments.
---

# Helm Standards

## Chart Structure

- Use lowercase hyphenated chart names.
- Keep chart `version` SemVer-compliant.
- Quote `appVersion`.
- Namespace helper template names with the chart name to avoid collisions.

## Values

- Use stable, documented value names for public chart configuration.
- Group related values clearly while keeping common CLI overrides straightforward.
- Quote strings and version-like values; keep booleans and integers typed correctly.
- Use `values.schema.json` when the chart has a non-trivial public values surface.
- Require mandatory values at template time with clear error messages.

## Templates

- Keep templates deterministic for GitOps-managed releases.
- Use `tpl` for intentionally supported user-supplied templates.
- Apply labels and selectors consistently through helpers.
- Keep RBAC least-privilege. Document any required wildcard verbs or resources.

## Workload Security

- Use non-root containers, dropped capabilities, read-only filesystems, and explicit security contexts.
- Set resource requests and limits according to workload type and platform policy.
- Add readiness and liveness probes for long-running services that can report health meaningfully.
- Keep plaintext secrets out of `values.yaml` and templates.

## Verification

- Run `helm lint` and `helm template` for changed charts.
- Use dry-run or chart tests when changing install/upgrade behavior.
