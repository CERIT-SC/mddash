---
name: docker
description: ALWAYS use this skill when working with Docker, Dockerfiles, compose files, container images, or containerized application configuration.
---

# Docker Standards

## Dockerfiles

- Pin base image versions for production images.
- Use multi-stage builds when build dependencies are not needed at runtime.
- Copy dependency manifests before source files to preserve build cache.
- Run final images as a non-root user. Document any required root runtime.
- Use exec form for `CMD` and `ENTRYPOINT`.
- Keep `.dockerignore` current and exclude VCS data, local dependencies, build output, and secrets.

## Runtime Configuration

- Externalize configuration through environment variables, mounted config, or orchestrator settings.
- Keep secrets out of images and committed local files.
- Add `HEALTHCHECK` for long-running service images on platforms that consume Docker health status.

## Compose Files

- Pin service image versions for shared Compose files.
- Use named volumes for persistent local data.
- Treat `deploy.resources` as Swarm/platform-specific behavior; document the runtime that enforces it.
- Keep local-only overrides separate from shared compose files.
- Use Compose `secrets` or platform-managed secrets for sensitive values.

## Verification

- Build the changed image or run the relevant compose config validation.
- Scan or review dependency and base-image updates before shipping production images.
