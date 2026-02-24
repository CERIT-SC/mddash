---
applyTo: "**/Dockerfile,**/Dockerfile.*,**/*.dockerfile,**/docker-compose*.yml,**/docker-compose*.yaml"
---
<context>
- **Immutability:** Never modify running containers; create new images for changes.
- **Efficiency:** Minimize image size and build time (multi-stage, caching).
- **Security:** Run as non-root, scan for vulnerabilities, use minimal base images.
- **Portability:** Externalize configuration; ensure images run consistently everywhere.
</context>
<best_practices>
<dockerfile>
### Multi-Stage Builds
Separate build dependencies from runtime.

```dockerfile
# ❌ Bad: Single stage, running as root, vague tag
FROM node:latest
COPY . .
RUN npm install
CMD npm start

# ✅ Good: Multi-stage, pinned version, non-root, optimized
# Stage 1: Build
FROM node:24-alpine3.22 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Runtime
FROM node:24-alpine3.22 AS runner
WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package*.json ./
RUN npm ci --omit=dev && npm cache clean --force
RUN chown -R appuser:appgroup /app
USER appuser
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3000/health || exit 1
CMD ["node", "dist/main.js"]
```

### Layer Caching
Copy dependency files before source code.

```dockerfile
FROM node:24-alpine3.22
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
CMD ["node", "server.js"]
```
</dockerfile>
<compose>
### Docker Compose

```yaml
# ❌ Bad: Version 2 (legacy), no resource limits, hardcoded secret
version: '2'
services:
  db:
    image: postgres
    environment:
      POSTGRES_PASSWORD: password123

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
</compose>
<structure>
### Project Structure
- `Dockerfile` in service root directory
- `.dockerignore` alongside Dockerfile
- `docker-compose.yml` for local development
- `docker-compose.prod.yml` for production overrides
</structure>
</best_practices>
<boundaries>
- ✅ **Always:** Multi-stage builds to separate build from runtime
- ✅ **Always:** Non-root user in final stage
- ✅ **Always:** Pin base image versions (e.g., `node:24-alpine3.22`)
- ✅ **Always:** Maintain `.dockerignore` (exclude `.git`, `node_modules`, secrets)
- ✅ **Always:** Exec form for `CMD`/`ENTRYPOINT` (`CMD ["node", "app.js"]`)
- ✅ **Always:** Define `HEALTHCHECK` instruction
- ⚠️ **Ask:** Before choosing Alpine vs Debian/Ubuntu base
- ⚠️ **Ask:** Before adding/dropping Linux capabilities
- ⚠️ **Ask:** About volume strategies for stateful services
- 🚫 **Never:** Copy secrets into images
- 🚫 **Never:** Use `latest` tag in production
- 🚫 **Never:** Run as root (UID 0)
- 🚫 **Never:** Include build tools in production image
</boundaries>
