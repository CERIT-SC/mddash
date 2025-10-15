---
applyTo: '.github/workflows/*.yml'
description: 'GitHub Actions CI/CD best practices for secure, efficient pipelines'
---

# GitHub Actions Best Practices

Build secure, efficient CI/CD pipelines following these principles:

## Workflow Structure

**Key Elements:**
- Use descriptive `name` and specific triggers (`on: push`, `pull_request`, `workflow_dispatch`)
- Set `concurrency` to prevent race conditions on shared resources
- Define `permissions` with least privilege (default `contents: read`)
- Use `workflow_call` for reusable workflows across projects

**Jobs:**
- Define clear dependencies with `needs`
- Use `outputs` to pass data between jobs
- Leverage `if` conditions for conditional execution
- Choose appropriate `runs-on` (ubuntu-latest, self-hosted, etc.)

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      artifact_path: ${{ steps.package.outputs.path }}
    steps:
      - uses: actions/checkout@v4
      - id: package
        run: echo "path=dist.zip" >> "$GITHUB_OUTPUT"
  
  deploy:
    needs: build
    if: github.ref == 'refs/heads/main'
    environment: production
    steps:
      - uses: actions/download-artifact@v3
```

**Steps:**
- Pin actions to specific versions (`@v4` or commit SHA, never `@main`)
- Use descriptive `name` for each step
- Combine shell commands with `&&` for efficiency
- Never hardcode secrets in `env`

## Security

**Secret Management:**
- Store all sensitive data in GitHub Secrets (`${{ secrets.SECRET_NAME }}`)
- Use environment-specific secrets with approval gates for production
- Never print secrets to logs or construct them dynamically

**OIDC for Cloud Auth:**
- Prefer OIDC over long-lived credentials (AWS, Azure, GCP)
- Configure trust policies in cloud provider
- Example: `aws-actions/configure-aws-credentials@v4` with OIDC

**Least Privilege:**
```yaml
permissions:
  contents: read        # Default read-only
  pull-requests: write  # Only if needed
```

**Security Scanning:**
- Integrate `dependency-review-action` for vulnerable dependencies
- Use CodeQL or SAST tools to scan source code
- Enable GitHub secret scanning and pre-commit hooks
- Sign container images with Cosign/Notary for verification

## Optimization

**Caching:**
```yaml
- uses: actions/cache@v3
  with:
    path: ~/.npm
    key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}
    restore-keys: ${{ runner.os }}-node-
```

**Matrix Strategies:**
```yaml
strategy:
  fail-fast: false
  matrix:
    os: [ubuntu-latest, windows-latest]
    node-version: [18.x, 20.x]
```

**Fast Checkout:**
- Use `fetch-depth: 1` for shallow clones (most builds)
- Only use `fetch-depth: 0` when full history needed
- Set `submodules: false` if not required

**Artifacts:**
```yaml
- uses: actions/upload-artifact@v3
  with:
    name: build-output
    path: dist/
    retention-days: 7
```

**Self-Hosted Runners:**
- Use for specialized hardware, private network access, or cost optimization
- Secure and maintain runner infrastructure
- Implement auto-scaling for demand

## Testing Strategy

**Unit Tests:**
- Run on every push/PR for fast feedback
- Parallelize for speed, enforce code coverage thresholds
- Publish reports as artifacts and GitHub Checks

**Integration Tests:**
```yaml
services:
  postgres:
    image: postgres:15
    env:
      POSTGRES_PASSWORD: test
```
- Use `services` for databases, message queues, caches
- Run after unit tests, manage test data cleanup

**E2E Tests:**
- Use Cypress/Playwright/Selenium against staging environment
- Mitigate flakiness with explicit waits and robust selectors
- Capture screenshots/videos on failure

**Performance Tests:**
- Use k6, JMeter, Locust for load testing
- Run nightly or on feature merges with defined thresholds
- Compare against baselines to detect degradation

**Test Reporting:**
- Publish results as GitHub Checks/Annotations for PR feedback
- Upload comprehensive reports (JUnit XML, HTML, coverage) as artifacts
- Add status badges to README

## Deployment

**Environments:**
```yaml
environment:
  name: production
  url: https://prod.example.com
```
- Use GitHub Environments with approval rules and secrets
- Staging: mirror production, auto-deploy on develop/release branches
- Production: require manual approval, implement comprehensive monitoring

**Deployment Strategies:**
- **Rolling Update**: Gradual replacement (default for stateless apps)
- **Blue/Green**: Deploy new version alongside old, instant traffic switch, easy rollback
- **Canary**: Roll out to 5-10% of users first, monitor metrics before full deployment
- **Feature Flags**: Deploy code but hide features until toggled (LaunchDarkly, Split.io)

**Rollback:**
- Store versioned artifacts/images for quick recovery
- Implement automated rollback on health check failures or monitoring alerts
- Document runbooks for manual rollback procedures
- Conduct post-incident reviews (PIRs)

## Workflow Checklist

- [ ] Descriptive `name`, appropriate `on` triggers with path/branch filters
- [ ] `concurrency` set for critical workflows
- [ ] `permissions: contents: read` by default, granular overrides
- [ ] Actions pinned to `@v4` or commit SHA (never `@main`)
- [ ] Secrets accessed via `${{ secrets.NAME }}`, never hardcoded
- [ ] OIDC for cloud auth, SAST/SCA tools integrated
- [ ] Caching with `hashFiles()` for optimal hit rates
- [ ] `fetch-depth: 1` for checkout, `strategy.matrix` for parallelization
- [ ] Unit/integration/E2E tests with GitHub Checks integration
- [ ] GitHub Environments for staging/production with approvals
- [ ] Rollback strategy documented and automated
- [ ] Post-deployment health checks and monitoring

## Troubleshooting

**Workflow Not Triggering:**
- Verify `on` triggers match events (push, pull_request, workflow_dispatch)
- Check `branches`, `paths` filters and `paths-ignore` precedence
- Debug with `${{ toJson(github) }}` to inspect context
- Check `concurrency` blocking and branch protection rules

**Permission Errors:**
- Set `permissions: contents: read` globally, add specific write permissions per job
- Verify secrets are configured in correct scope (repo/org/environment)
- For OIDC, check cloud provider trust policies

**Cache Issues:**
- Use `key: ${{ runner.os }}-${{ hashFiles('**/package-lock.json') }}`
- Add `restore-keys` for fallback
- Verify `path` matches actual dependency location

**Slow Workflows:**
- Profile with workflow run summary
- Combine commands with `&&`, use `actions/cache`
- Parallelize with `strategy.matrix`
- Consider larger runners or self-hosted for resource-intensive tasks

**Flaky Tests:**
- Ensure test isolation, clean up resources
- Use explicit waits, not `sleep()` in E2E tests
- Match CI environment to local (use `services` for dependencies)
- Use stable selectors (`data-testid`), capture screenshots/videos on failure

**Deployment Failures:**
- Review logs immediately post-deployment
- Validate env vars, ConfigMaps, Secrets
- Implement post-deployment health checks
- Trigger rollback immediately if issues detected 
