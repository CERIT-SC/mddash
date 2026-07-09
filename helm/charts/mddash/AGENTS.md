# helm/charts/mddash

## Mission

Deploys a multi-tenant JupyterHub environment for MDDash: isolated per-user namespaces with sidecar services (proxy/auth/api/s3-sync) around the notebook.

## Patterns

- **Pre-spawn hook** (`files/pre_spawn_hook.py`, injected via `--set-file jupyterhub.hub.extraConfig.pre-spawn-hook`) provisions each user namespace (namespace, RBAC, PVC) before notebook startup. It uses `kubernetes_asyncio` (async — not the sync `kubernetes` client); all calls must be awaited.
- **Proxy serves the static UI**: the proxy (Caddy) is not just a reverse proxy — it embeds the compiled React/TypeScript dashboard as static assets and routes to auth, API, and notebook.
- **Template-based values**: `values.yaml.tmpl` is rendered with `gomplate` (`make -C helm render` from root, `make render` from `helm/`). Never edit `values.yaml` — it's generated.

## Critical Gotchas

- **Rancher annotations**: namespaces require `field.cattle.io/projectId` and `field.cattle.io/resourceQuota`. The hook waits for `InitialRolesPopulated`, patches the namespace, then waits for ResourceQuota status to become active.
- **Proxy readiness waits on health**: the proxy sidecar waits for `auth` `/health` and the dashboard `/dash/api/health` with `curl --fail` before starting Caddy. Don't replace this with bare port checks — non-2xx must not count as readiness.
- **Cross-namespace hub access**: the hook overrides `JUPYTERHUB_API_URL` to `http://hub.{hub_namespace}.svc.cluster.local:8081/hub/api`.
- **Security hardening**: `modify_pod_hook` drops all capabilities and sets seccomp profiles (e-INFRA compliance).
- **Network policies and pre-puller are disabled** intentionally (deployment model + resource limits).
- **Landing page ingress**: uses `pathType: Exact /` on the same host as JupyterHub. NGINX resolves Exact before Prefix, so the landing page owns only `/` while all other traffic continues to JupyterHub.
