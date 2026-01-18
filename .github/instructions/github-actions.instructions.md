---
applyTo: '.github/workflows/*.yml'
---

# GitHub Actions Best Practices

Secure, efficient CI/CD pipelines.

<context>
Guidelines for building reliable GitHub Actions workflows with proper security, caching, testing, and deployment strategies.
</context>

<best_practices>

<workflow_structure>
### Workflow Structure
- Descriptive `name` and specific triggers (`on: push`, `pull_request`, `workflow_dispatch`)
- `concurrency` to prevent race conditions
- `permissions` with least privilege (default `contents: read`)
- `workflow_call` for reusable workflows

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
      - uses: actions/download-artifact@v4
```
</workflow_structure>

<security>
### Security

**Permissions:**
```yaml
permissions:
  contents: read
  pull-requests: write  # Only if needed
```

**Secrets:**
- Store sensitive data in GitHub Secrets (`${{ secrets.SECRET_NAME }}`)
- Use environment-specific secrets with approval gates
- Never print secrets to logs

**OIDC:**
- Prefer OIDC over long-lived credentials for cloud auth (AWS, Azure, GCP)
</security>

<optimization>
### Optimization

**Caching:**
```yaml
- uses: actions/cache@v4
  with:
    path: ~/.npm
    key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}
    restore-keys: ${{ runner.os }}-node-
```

**Matrix:**
```yaml
strategy:
  fail-fast: false
  matrix:
    os: [ubuntu-latest, windows-latest]
    node-version: [18.x, 20.x]
```

**Checkout:**
- `fetch-depth: 1` for shallow clones (most builds)
- `fetch-depth: 0` only when full history needed
</optimization>

<testing>
### Testing

**Services:**
```yaml
services:
  postgres:
    image: postgres:15
    env:
      POSTGRES_PASSWORD: test
```

- Unit tests on every push/PR
- Integration tests with `services` for databases
- E2E tests with Playwright/Cypress against staging
- Publish results as GitHub Checks
</testing>

<deployment>
### Deployment

**Environments:**
```yaml
environment:
  name: production
  url: https://prod.example.com
```

**Strategies:**
- **Rolling:** Gradual replacement (default)
- **Blue/Green:** Instant traffic switch, easy rollback
- **Canary:** 5-10% rollout first, monitor before full deploy
</deployment>

<troubleshooting>
### Troubleshooting
- **Not triggering:** Check `on` triggers, `branches`/`paths` filters
- **Permission errors:** Set `permissions` explicitly, verify secrets scope
- **Cache issues:** Use `hashFiles()` in key, add `restore-keys`
- **Slow workflows:** Parallelize with matrix, use caching, combine commands with `&&`
</troubleshooting>

</best_practices>

<boundaries>
- ✅ **Always:** Pin actions to `@v4` or commit SHA (never `@main`)
- ✅ **Always:** Set `permissions: contents: read` by default
- ✅ **Always:** Use `${{ secrets.NAME }}` for sensitive data
- ✅ **Always:** Use `fetch-depth: 1` for checkout
- ✅ **Always:** Use `hashFiles()` for cache keys
- ⚠️ **Ask:** Before adding self-hosted runners
- ⚠️ **Ask:** Before adding new workflow triggers
- 🚫 **Never:** Hardcode secrets in workflow files
- 🚫 **Never:** Use `@main` or `@latest` for action versions
- 🚫 **Never:** Print secrets to logs
</boundaries> 
