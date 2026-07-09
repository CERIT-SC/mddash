# Landing Page

## Mission

Public landing page for MDDash — a React + TypeScript single-file SPA served by Caddy at the root path (`/`). Introduces the platform and links to JupyterHub login at `/hub/`. No auth required.

**Design system compliance is mandatory** because this is the first point of user contact: all components, colors, and typography must use the e-INFRA design system (`@e-infra/design-system`, https://design-system.e-infra.cz/docs). Custom CSS only extends it, never replaces it. If a needed component/token is missing, open an issue/PR in https://github.com/CERIT-SC/design-system rather than working around it.

## Non-Obvious Gotchas

- **Single-file build**: `vite-plugin-singlefile` inlines all JS/CSS (and a custom `webpOptimize` plugin converts PNG/JPEG imports to WebP base64 data URIs) into one `index.html`. Don't expect separate `/assets/` paths in production.
- **Caddy is static only**: no auth, no proxy logic, no runtime config in the landing-page Caddyfile. Runtime runs as non-root (UID 1000) with dropped capabilities.
- **Ingress exact match**: the landing page shares the host with JupyterHub and uses `pathType: Exact /` to own only the root path — all other traffic goes to JupyterHub.
