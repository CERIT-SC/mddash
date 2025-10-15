---
description: 'Docker best practices for optimized, secure container images'
applyTo: '**/Dockerfile,**/Dockerfile.*,**/*.dockerfile,**/docker-compose*.yml,**/docker-compose*.yaml'
---

# Docker Best Practices

Build secure, efficient, and maintainable Docker images following these core principles:

## Core Principles

**Immutability**: Never modify running containers. Create new versioned images for changes.
- Use semantic versioning for tags (avoid `latest` in production)
- Enable instant rollbacks and reproducible deployments

**Efficiency**: Minimize image size to reduce attack surface, build time, and resource usage.
- Prefer Alpine/slim variants and multi-stage builds
- Exclude development dependencies from production images

**Security**: Run as non-root user, use minimal base images, scan for vulnerabilities.
- Never include secrets in image layers
- Implement health checks for container lifecycle management

**Portability**: Externalize configuration via environment variables.
- Design self-contained images that run consistently across environments

## Dockerfile Guidelines

### 1. Multi-Stage Builds
Use multiple `FROM` stages to separate build dependencies from runtime. Copy only necessary artifacts to final stage.

```dockerfile
FROM node:18-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:18-alpine AS production
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY --from=build /app/package*.json ./
USER node
EXPOSE 3000
CMD ["node", "dist/main.js"]
```

### 2. Base Image Selection
- Use Alpine (`node:18-alpine`) or slim variants for minimal size
- Pin specific versions (avoid `latest` in production)
- Prefer official images from trusted sources

### 3. Layer Optimization
- Order instructions from least to most frequently changing
- Combine `RUN` commands to reduce layers
- Clean up in the same layer: `RUN apt-get update && apt-get install -y pkg && rm -rf /var/lib/apt/lists/*`

```dockerfile
# Good: Copy dependencies first, then source code
COPY package*.json ./
RUN npm ci
COPY src/ ./src/
```

### 4. .dockerignore
Create comprehensive `.dockerignore` to exclude:
- Version control (`.git*`)
- Dependencies installed in container (`node_modules`, `__pycache__`)
- Build artifacts, logs, IDE files
- Test files and documentation

### 5. Security: Non-Root User
Always run as non-root user with proper permissions:

```dockerfile
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
RUN chown -R appuser:appgroup /app
USER appuser
```

### 6. Command Execution
- Use exec form `CMD ["executable", "arg"]` for proper signal handling
- Use `ENTRYPOINT` for the main executable, `CMD` for default arguments
- Document ports with `EXPOSE` (doesn't publish, just documents)

### 7. Configuration
- Externalize config via `ENV` variables with sensible defaults
- Never hardcode secrets in images
- Use runtime injection for sensitive data (K8s secrets, Docker secrets)

## Security Checklist

When creating or reviewing Dockerfiles, ensure:

- [ ] **Non-root user**: Define `USER` directive with dedicated application user
- [ ] **Minimal base image**: Use Alpine/slim variants with pinned versions
- [ ] **No secrets in layers**: Use runtime injection, never `COPY` secrets
- [ ] **Health checks**: Implement `HEALTHCHECK` for orchestration
- [ ] **Security scanning**: Integrate `hadolint` and `trivy` in CI pipeline
- [ ] **Layer optimization**: Combine commands, clean up in same layer
- [ ] **`.dockerignore`**: Exclude dev files, secrets, and unnecessary content

## Health Checks

Define health checks for container lifecycle management:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl --fail http://localhost:8080/health || exit 1
```

## Common Patterns

**Multi-stage with different base images:**
```dockerfile
FROM golang:1.21-alpine AS build
WORKDIR /app
COPY go.* ./
RUN go mod download
COPY . .
RUN go build -o server

FROM alpine:3.19
RUN addgroup -S app && adduser -S app -G app
COPY --from=build /app/server /app/server
USER app
HEALTHCHECK CMD ["/app/server", "-health"]
CMD ["/app/server"]
```

**Node.js with separate dependency install:**
```dockerfile
FROM node:18-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

FROM node:18-alpine
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
USER node
CMD ["node", "server.js"]
```
