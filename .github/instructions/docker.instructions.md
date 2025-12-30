---
applyTo: "**/Dockerfile,**/Dockerfile.*,**/*.dockerfile,**/docker-compose*.yml,**/docker-compose*.yaml"
---

# Docker Guidelines

## Context
Standardized guidelines for containerizing applications to ensure reproducibility, security, and efficiency.
- **Immutability:** Never modify running containers; create new images for changes.
- **Efficiency:** Minimize image size and build time (multi-stage, caching).
- **Security:** Run as non-root, scan for vulnerabilities, and use minimal base images.
- **Portability:** Externalize configuration; ensure images run consistently everywhere.

## Boundaries

### ✅ Always
- **Multi-Stage Builds:** Use multi-stage builds to separate build dependencies from the runtime environment.
- **Non-Root User:** Create and switch to a non-root user (e.g., `appuser`) in the final stage.
- **Pin Versions:** Use specific tags for base images (e.g., `node:18-alpine3.19` instead of `node:alpine`).
- **.dockerignore:** Maintain a comprehensive `.dockerignore` to exclude `.git`, `node_modules`, secrets, and temporary files.
- **Exec Form:** Use the JSON array syntax for `CMD` and `ENTRYPOINT` (e.g., `CMD ["node", "app.js"]`) to ensure signals are passed correctly.
- **Health Checks:** Define a `HEALTHCHECK` instruction to monitor application status.

### ⚠️ Ask First
- **Base Image OS:** Ask before choosing between Alpine (smaller) and Debian/Ubuntu (better compatibility) if not specified.
- **Capabilities:** Ask before adding or dropping Linux capabilities (e.g., `--cap-drop ALL` is secure but may break apps).
- **Exposing Ports:** Verify which ports need to be exposed and published.
- **Persistence:** Ask about volume strategies for stateful services.

### 🚫 Never
- **Secrets in Images:** Never `COPY` secrets or credentials into the image. Use environment variables or secret mounts.
- **Latest Tag:** Never use the `latest` tag for base images in production builds.
- **Root Processes:** Never run the main application process as root (UID 0).
- **Dev Dependencies:** Never include build tools (git, gcc, etc.) or development dependencies in the final production image.
- **Mutable Tags:** Avoid overwriting image tags; use unique semantic versions or commit SHAs.

## Examples

### Dockerfile Best Practices

```dockerfile
# ❌ Bad: Single stage, running as root, vague tag
FROM node:latest
COPY . .
RUN npm install
CMD npm start

# ✅ Good: Multi-stage, pinned version, non-root, optimized
# Stage 1: Build
FROM node:18-alpine3.19 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Runtime
FROM node:18-alpine3.19 AS runner
WORKDIR /app
# Create non-root user
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
# Copy only necessary files
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package*.json ./
# Install only production deps
RUN npm ci --only=production && npm cache clean --force
# Set permissions
RUN chown -R appuser:appgroup /app
USER appuser
EXPOSE 3000
# Use exec form
CMD ["node", "dist/main.js"]
```

### Docker Compose Best Practices

```yaml
# ❌ Bad: Version 2 (legacy), no resource limits
version: '2'
services:
  db:
    image: postgres
    environment:
      POSTGRES_PASSWORD: password123 # Hardcoded secret

# ✅ Good: Modern format, explicit versions, secrets
services:
  db:
    image: postgres:15-alpine
    restart: always
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
    volumes:
      - db_data:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          cpus: '0.50'
          memory: 512M

secrets:
  db_password:
    file: ./secrets/db_password.txt

volumes:
  db_data:
```

### Optimization Patterns

**Dependency Caching (Node.js example):**
Copy package files and install dependencies *before* copying source code to leverage Docker layer caching.

```dockerfile
FROM node:18-alpine
WORKDIR /app
# 1. Copy dependency definitions
COPY package*.json ./
# 2. Install dependencies (cached if package.json doesn't change)
RUN npm ci --only=production
# 3. Copy source code
COPY . .
CMD ["node", "server.js"]
```

## Project Structure
- Place `Dockerfile` in the root of the service directory.
- Place `.dockerignore` alongside the `Dockerfile`.
- Use `docker-compose.yml` for local development orchestration.
- Use `docker-compose.prod.yml` (or similar) for production overrides if not using K8s.

