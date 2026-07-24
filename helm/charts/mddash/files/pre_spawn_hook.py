import asyncio
import hashlib
import json
import logging
import re
import time
from http import HTTPStatus
from os import getenv
from typing import Any

from kubernetes_asyncio import config
from kubernetes_asyncio.client import (
    ApiClient,
    CoreV1Api,
    RbacAuthorizationV1Api,
    V1Capabilities,
    V1Pod,
    V1SeccompProfile,
    V1SecurityContext,
)
from kubernetes_asyncio.client.rest import ApiException
from kubespawner import KubeSpawner

logger = logging.getLogger(__name__)

PRESERVE_LABEL = "mddash.io/preserve-on-stop"


# =============================================================================
# Kubernetes Manifest Builders
# =============================================================================


def _get_namespace_manifest(
    namespace: str, rancher_project_id: str, cpu_limit: str, mem_limit: str, cpu_request: str, mem_request: str
) -> dict:
    resource_quota = json.dumps({
        "limit": {
            "limitsCpu": cpu_limit,
            "limitsMemory": mem_limit,
            "requestsCpu": cpu_request,
            "requestsMemory": mem_request,
        }
    })
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": namespace,
            "annotations": {
                "field.cattle.io/projectId": rancher_project_id,
                "field.cattle.io/resourceQuota": resource_quota,
            },
        },
    }


def _get_role_manifest(role_name: str, include_pvc: bool = False) -> dict:
    resources = ["pods", "pods/exec", "services", "events"]
    if include_pvc:
        resources.append("persistentvolumeclaims")

    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {"name": role_name},
        "rules": [
            {"apiGroups": [""], "resources": resources, "verbs": ["create", "delete", "get", "list", "watch"]},
            {"apiGroups": [""], "resources": ["pods/log"], "verbs": ["get", "list"]},
            {
                "apiGroups": ["batch"],
                "resources": ["jobs"],
                "verbs": ["create", "get", "list", "watch", "update", "patch", "delete"],
            },
        ],
    }


def _get_role_binding_manifest(
    role_binding_name: str, service_account_name: str, role_name: str, namespace: str | None = None
) -> dict:
    subject = {"kind": "ServiceAccount", "name": service_account_name}
    if namespace:
        subject["namespace"] = namespace

    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "RoleBinding",
        "metadata": {"name": role_binding_name},
        "subjects": [subject],
        "roleRef": {
            "kind": "Role",
            "name": role_name,
            "apiGroup": "rbac.authorization.k8s.io",
        },
    }


def _get_pvc_manifest(pvc_name: str, storage_size: str = "10Gi", storage_class: str = "nfs-csi") -> dict:
    return {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {"name": pvc_name},
        "spec": {
            "storageClassName": storage_class,
            "accessModes": ["ReadWriteMany"],
            "resources": {"requests": {"storage": storage_size}},
        },
    }


# =============================================================================
# Helper Functions
# =============================================================================


async def _ensure_resource(method: Any, **kwargs: object) -> None:  # ruff:ignore[any-type]
    """
    Create a Kubernetes resource, ignoring AlreadyExists errors.

    Raises:
        ApiException: If the API call fails for any reason other than a 409 Conflict.
    """
    try:
        await method(**kwargs)
    except ApiException as e:
        if e.status != HTTPStatus.CONFLICT:
            raise


async def _resource_exists(method: Any, **kwargs: object) -> bool:  # ruff:ignore[any-type]
    """
    Check if a Kubernetes resource exists.

    Returns:
        bool: True if the resource exists, False if a 403 or 404 is returned.

    Raises:
        ApiException: If the API call fails for any reason other than 403 or 404.
    """
    try:
        await method(**kwargs)
        return True
    except ApiException as e:
        # In Rancher environments, a 403 Forbidden can occur briefly after resource creation before permissions propagate to the proxy.
        if e.status in {HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND}:
            return False
        raise


async def _wait_for_resource(method: Any, timeout_s: float = 30.0, interval: float = 0.1, **kwargs: object) -> None:  # ruff:ignore[any-type]
    """
    Wait until a Kubernetes resource exists (or time out).

    Raises:
        TimeoutError: If the resource does not become available within timeout_s seconds.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if await _resource_exists(method, **kwargs):
            return
        await asyncio.sleep(interval)

    raise TimeoutError(f"Timed out after {timeout_s:.1f}s waiting for resource")


def _ns_has_conditions(annotations: dict[str, str] | None, required: set[str]) -> bool:
    """
    Check if Rancher finished namespace initialization.

    Rancher sets `cattle.io/status` JSON with Conditions including:
    - Type: InitialRolesPopulated, Status: True
    - Type: ResourceQuotaInit, Status: True

    Returns:
        bool: True if all required condition types are present with Status "True".
    """
    if not annotations:
        return False

    status_raw = annotations.get("cattle.io/status")
    if not status_raw:
        return False

    try:
        status_obj = json.loads(status_raw)
    except json.JSONDecodeError:
        return False

    conditions = status_obj.get("Conditions")
    if not isinstance(conditions, list):
        return False

    found_true: set[str] = set()
    for cond in conditions:
        if not isinstance(cond, dict):
            continue
        cond_type = cond.get("Type")
        cond_status = cond.get("Status")
        if cond_type in required and cond_status == "True":
            found_true.add(cond_type)

    return required.issubset(found_true)


async def _wait_for_ns_conditions(
    core_api: CoreV1Api,
    namespace: str,
    required: set[str],
    timeout_s: float = 60.0,
    interval: float = 0.1,
) -> None:
    """
    Wait until Rancher reports required namespace conditions.

    Raises:
        TimeoutError: If the required conditions are not met within timeout_s seconds.
        ApiException: If the namespace read fails for any reason other than 403 or 404.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            ns_obj = await core_api.read_namespace(name=namespace)  # type: ignore[misc]
            annotations = getattr(getattr(ns_obj, "metadata", None), "annotations", None)
            if _ns_has_conditions(annotations, required):
                return
        except ApiException as e:
            # Catch 403/404 during the propagation window
            if e.status not in {HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND}:
                raise
        await asyncio.sleep(interval)

    raise TimeoutError(
        f"Timed out after {timeout_s:.1f}s waiting for Rancher namespace conditions {sorted(required)} in {namespace}"
    )


async def _wait_for_resource_quota_active(
    core_api: CoreV1Api,
    namespace: str,
    timeout_s: float = 60.0,
    interval: float = 0.5,
) -> None:
    """
    Wait until the ResourceQuota in the namespace has non-zero limits in status.hard.

    The post_stop_hook zeroes the quota. After the namespace is patched with restored limits,
    Rancher updates the ResourceQuota spec and the quota controller reconciles status.
    The admission controller uses status.hard — if still zero or absent, pods are rejected.

    Raises:
        TimeoutError: If the quota is not active within timeout_s seconds.
        ApiException: If the API call fails for any reason other than 403 or 404.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            quotas = await core_api.list_namespaced_resource_quota(namespace=namespace)
            for quota in quotas.items:
                status_hard = getattr(getattr(quota, "status", None), "hard", None)
                if not status_hard:
                    continue
                if status_hard.get("requests.cpu", "0") != "0" and status_hard.get("requests.memory", "0") != "0":
                    return
        except ApiException as e:
            if e.status not in {HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND}:
                raise
        await asyncio.sleep(interval)

    raise TimeoutError(f"Timed out after {timeout_s:.1f}s waiting for ResourceQuota in {namespace} to become active")


def _get_security_context() -> dict:
    """
    Return hardened security context for sidecar containers.

    Returns:
        dict: A security context dict enforcing non-root, read-only, and capability drop policies.
    """
    return {
        "allowPrivilegeEscalation": False,
        "runAsNonRoot": True,
        "runAsUser": 1000,
        "runAsGroup": 1000,
        "capabilities": {"drop": ["ALL"]},
        "seccompProfile": {"type": "RuntimeDefault"},
    }


# =============================================================================
# User Resource Naming
# =============================================================================


_VALID_DNS1123 = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
_INVALID_DNS1123_CHARS = re.compile(r"[^a-z0-9-]+")
_REPEATED_HYPHENS = re.compile(r"-+")
DNS1123_LABEL_MAX = 63
_HASH_SUFFIX_LEN = 9  # "-" + 8 hex chars from sha256


def _dns1123_label(value: str, max_length: int = DNS1123_LABEL_MAX) -> str:
    """
    Map a username to a valid Kubernetes DNS-1123 label no longer than ``max_length``.

    Already-valid names short enough to fit pass through unchanged so existing
    deployments keep their namespaces. Any name that needs sanitization or would
    exceed ``max_length`` gets an 8-char SHA-256 suffix of the original value, so
    two usernames that collapse to the same label (e.g. ``john.doe`` and
    ``john-doe``) or are both truncated cannot land in the same namespace.

    Returns:
        str: The sanitized label.

    Raises:
        ValueError: If the value contains no valid label characters, or
            ``max_length`` is too small to hold a label plus the hash suffix.
    """
    if _VALID_DNS1123.match(value) and len(value) <= max_length:
        return value

    digest = hashlib.sha256(value.encode()).hexdigest()[:8]
    budget = max_length - _HASH_SUFFIX_LEN
    if budget < 1:
        raise ValueError(f"max_length {max_length} leaves no room for a label")

    safe = _REPEATED_HYPHENS.sub("-", _INVALID_DNS1123_CHARS.sub("-", value.lower())).strip("-")
    if not safe:
        raise ValueError(f"username {value!r} has no valid DNS-1123 characters")

    if len(safe) > budget:
        safe = safe[:budget].rstrip("-")
        if not safe:
            raise ValueError(f"username {value!r} has no valid DNS-1123 characters")
    return f"{safe}-{digest}"


# =============================================================================
# Sidecar Container Builders
# =============================================================================


def _proxy_start_command(service_prefix: str) -> str:
    """
    Return the proxy startup command that waits for auth and API health.

    Returns:
        str: Shell command string for proxy container startup.
    """
    api_health_url = f"http://localhost:5000{service_prefix}/dash/api/health"
    return (
        "until "
        "curl --fail --silent --show-error --connect-timeout 1 http://localhost:5001/health > /dev/null "
        f"&& curl --fail --silent --show-error --connect-timeout 1 {api_health_url} > /dev/null; "
        "do echo 'waiting for auth and dashboard API health'; sleep 0.1; done; "
        "exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile"
    )


def _proxy_container(service_prefix: str, username: str, security_context: dict) -> dict | None:
    image = getenv("PROXY_IMAGE")
    if not image:
        return None

    return {
        "name": "proxy",
        "image": image,
        "imagePullPolicy": getenv("IMAGE_PULL_POLICY", "Always"),
        "command": ["sh", "-c", _proxy_start_command(service_prefix)],
        "ports": [{"containerPort": 8888, "name": "http"}],
        "env": [
            {"name": "CADDY_ROUTE_PREFIX", "value": service_prefix},
            {"name": "JUPYTERHUB_USER", "value": username},
            {"name": "AUTH_HOST", "value": "localhost"},
            {"name": "API_HOST", "value": "localhost"},
            {"name": "NOTEBOOK_HOST", "value": "localhost"},
            {
                "name": "DEFAULT_NOTEBOOKS_REPO",
                "value": getenv("DEFAULT_NOTEBOOKS_REPO", "https://github.com/sb-ncbr/mddash-notebooks.git"),
            },
            {"name": "MDPOSIT_URL", "value": getenv("MDPOSIT_URL", "")},
        ],
        "resources": {"requests": {"cpu": "10m", "memory": "32Mi"}, "limits": {"cpu": "100m", "memory": "64Mi"}},
        "securityContext": security_context,
    }


def _auth_container(
    service_prefix: str, username: str, hub_namespace: str, jupyterhub_env: dict, security_context: dict
) -> dict | None:
    image = getenv("AUTH_IMAGE")
    if not image:
        return None

    return {
        "name": "auth",
        "image": image,
        "imagePullPolicy": getenv("IMAGE_PULL_POLICY", "Always"),
        "ports": [{"containerPort": 5001, "name": "auth"}],
        "env": [
            {"name": "JUPYTERHUB_USER", "value": username},
            {"name": "JUPYTERHUB_CLIENT_ID", "value": jupyterhub_env.get("JUPYTERHUB_CLIENT_ID", "")},
            {"name": "JUPYTERHUB_API_TOKEN", "value": jupyterhub_env.get("JUPYTERHUB_API_TOKEN", "")},
            {"name": "JUPYTERHUB_API_URL", "value": f"http://hub.{hub_namespace}.svc.cluster.local:8081/hub/api"},
            {"name": "JUPYTERHUB_OAUTH_CALLBACK_URL", "value": jupyterhub_env.get("JUPYTERHUB_OAUTH_CALLBACK_URL", "")},
            {"name": "JUPYTERHUB_SERVICE_PREFIX", "value": service_prefix},
            {"name": "JUPYTERHUB_DEFAULT_URL", "value": "/dash"},
        ],
        "resources": {"requests": {"cpu": "10m", "memory": "48Mi"}, "limits": {"cpu": "100m", "memory": "96Mi"}},
        "securityContext": security_context,
    }


_API_PASSTHROUGH_ENV = [
    "IMAGE_PULL_POLICY",
    "NOTEBOOK_IMAGE",
    "ANALYSIS_IMAGE",
    "GPU_TYPE",
    "S3_ENDPOINT",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "PVC_STORAGE_SIZE",
    "NS_REQUESTS_CPU",
    "NS_REQUESTS_MEMORY",
    "NS_LIMITS_CPU",
    "NS_LIMITS_MEMORY",
    "NS_MAX_NOTEBOOKS",
    "NOTEBOOK_CPU_REQUEST",
    "NOTEBOOK_MEMORY_REQUEST",
    "NOTEBOOK_CPU_LIMIT",
    "NOTEBOOK_MEMORY_LIMIT",
    "NOTEBOOK_IDLE_TIMEOUT",
    "ANALYSIS_CPU_REQUEST",
    "ANALYSIS_MEMORY_REQUEST",
    "ANALYSIS_CPU_LIMIT",
    "ANALYSIS_MEMORY_LIMIT",
    "HOSTNAME",
    "MDREPO_URL",
    "MDREPO_SCOPES",
    "MDREPO_CLIENT_ID",
    "MDREPO_CLIENT_SECRET",
    "MDPOSIT_URL",
    "TUNER_USER",
    "TUNER_PASSWORD",
    "DEFAULT_NOTEBOOKS_REPO",
    "METADUMP_API_URL",
    "MDREPO_UPLOADER_IMAGE",
]


def _api_container(
    service_prefix: str,
    username: str,
    user_namespace: str,
    hub_namespace: str,
    bucket_name: str,
    pvc_name: str,
    volume_name: str,
    security_context: dict,
) -> dict | None:
    image = getenv("API_IMAGE")
    if not image:
        return None

    return {
        "name": "api",
        "image": image,
        "imagePullPolicy": getenv("IMAGE_PULL_POLICY", "Always"),
        "ports": [{"containerPort": 5000, "name": "api"}],
        "env": [
            {"name": "JUPYTERHUB_USER", "value": username},
            {"name": "JUPYTERHUB_SERVICE_PREFIX", "value": service_prefix},
            {"name": "POD_NAMESPACE", "value": user_namespace},
            {"name": "HUB_NAMESPACE", "value": hub_namespace},
            {"name": "S3_BUCKET", "value": bucket_name},
            {"name": "PVC_NAME", "value": pvc_name},
            {"name": "TZ", "value": "UTC"},
            *[{"name": k, "value": getenv(k, "")} for k in _API_PASSTHROUGH_ENV],
        ],
        "volumeMounts": [{"name": volume_name, "mountPath": "/mddash"}],
        "resources": {"requests": {"cpu": "50m", "memory": "128Mi"}, "limits": {"cpu": "250m", "memory": "512Mi"}},
        "securityContext": security_context,
    }


def _s3_sync_container(bucket_name: str, volume_name: str, security_context: dict) -> dict | None:
    image = getenv("S3_SYNC_IMAGE")
    if not image:
        return None

    return {
        "name": "s3-sync",
        "image": image,
        "imagePullPolicy": getenv("IMAGE_PULL_POLICY", "Always"),
        "env": [
            {"name": "S3_BUCKET", "value": bucket_name},
            {"name": "S3_ENDPOINT", "value": getenv("S3_ENDPOINT", "")},
            {"name": "S3_ACCESS_KEY", "value": getenv("S3_ACCESS_KEY", "")},
            {"name": "S3_SECRET_KEY", "value": getenv("S3_SECRET_KEY", "")},
        ],
        "volumeMounts": [{"name": volume_name, "mountPath": "/mddash"}],
        "resources": {"requests": {"cpu": "10m", "memory": "64Mi"}, "limits": {"cpu": "200m", "memory": "256Mi"}},
        "securityContext": security_context,
    }


def _get_sidecar_containers(
    spawner: "KubeSpawner", bucket_name: str, pvc_name: str, volume_name: str, user_namespace: str
) -> list[dict]:
    """
    Build sidecar container configurations for the user pod.

    Returns:
        list[dict]: Container spec dicts for all enabled sidecar containers.
    """
    username: str = spawner.user.name  # type: ignore[union-attr]
    hub_namespace = getenv("POD_NAMESPACE", "default")
    service_prefix = f"/user/{username}"
    jupyterhub_env = spawner.get_env()
    security_context = _get_security_context()

    container_builders = [
        lambda: _proxy_container(service_prefix, username, security_context),
        lambda: _auth_container(service_prefix, username, hub_namespace, jupyterhub_env, security_context),
        lambda: _api_container(
            service_prefix,
            username,
            user_namespace,
            hub_namespace,
            bucket_name,
            pvc_name,
            volume_name,
            security_context,
        ),
        lambda: _s3_sync_container(bucket_name, volume_name, security_context),
    ]

    return [c for builder in container_builders if (c := builder()) is not None]


# =============================================================================
# Progress Reporting
# =============================================================================


def _get_or_create_progress_queue(spawner: "KubeSpawner") -> asyncio.Queue:
    if not hasattr(spawner, "_mddash_progress_queue"):
        spawner._mddash_progress_queue = asyncio.Queue()  # type: ignore  # ruff:ignore[private-member-access]
    return spawner._mddash_progress_queue  # type: ignore  # ruff:ignore[private-member-access]


async def _report_progress(spawner: "KubeSpawner", message: str, progress: int) -> None:
    await _get_or_create_progress_queue(spawner).put({"message": message, "progress": progress})


async def _spawn_progress(self: "KubeSpawner") -> Any:  # type: ignore[override]  # ruff:ignore[any-type]
    """
    Yield spawn progress messages sourced from the pre_spawn_hook via an asyncio.Queue.

    Yields:
        dict[str, int | str]: Progress message with "message" and "progress" keys.
    """
    queue = _get_or_create_progress_queue(self)
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=2.0)
        except asyncio.TimeoutError:
            continue
        if item is None:
            break
        yield item
    yield {"progress": 85, "message": "Waiting for MDDash to start..."}


# =============================================================================
# JupyterHub Spawner Hooks
# =============================================================================


async def pre_spawn_hook(spawner: "KubeSpawner") -> None:  # ruff:ignore[too-many-locals]
    """
    Prepare user environment before spawning the notebook server.

    Creates user namespace, RBAC, PVC, S3 bucket, and configures sidecar containers.
    """
    config.load_incluster_config()
    api_client = ApiClient()
    core_api = CoreV1Api(api_client)
    rbac_api = RbacAuthorizationV1Api(api_client)

    try:
        username: str = spawner.user.name  # type: ignore[union-attr]
        helm_package = getenv("HELM_PACKAGE", "mddash")
        hub_namespace = getenv("POD_NAMESPACE", "default")
        rancher_project_id = getenv("RANCHER_PROJECT_ID", "")

        user_slug = _dns1123_label(username, max_length=DNS1123_LABEL_MAX - len(f"{helm_package}-user-") - len("-ns"))
        user_namespace = f"{helm_package}-user-{user_slug}-ns"
        bucket_name = f"{helm_package}-user-{user_slug}"
        pvc_name = f"{helm_package}-user-pvc"
        volume_name = "mddash-volume"

        # Create namespace with resource quotas
        namespace_manifest = _get_namespace_manifest(
            user_namespace,
            rancher_project_id,
            cpu_limit=getenv("NS_LIMITS_CPU", "32000m"),
            mem_limit=getenv("NS_LIMITS_MEMORY", "64Gi"),
            cpu_request=getenv("NS_REQUESTS_CPU", "2500m"),
            mem_request=getenv("NS_REQUESTS_MEMORY", "6Gi"),
        )
        await _report_progress(spawner, "Creating user namespace...", 5)
        await _ensure_resource(core_api.create_namespace, body=namespace_manifest)

        await _report_progress(spawner, "Waiting for namespace to be ready...", 15)
        if rancher_project_id:
            await _wait_for_ns_conditions(core_api, user_namespace, {"InitialRolesPopulated"})
        await core_api.patch_namespace(name=user_namespace, body=namespace_manifest)  # type: ignore[misc]

        # Prepare resource names and manifests
        user_role = f"{helm_package}-user-role"
        user_binding = f"{helm_package}-user-binding"
        hub_role = f"{helm_package}-hub-role"
        hub_binding = f"{helm_package}-hub-binding"
        pvc_manifest = _get_pvc_manifest(
            pvc_name,
            storage_size=getenv("PVC_STORAGE_SIZE", "10Gi"),
            storage_class=getenv("PVC_STORAGE_CLASS", "nfs-csi"),
        )

        # Create Roles first, then RoleBindings.
        # Some clusters (or admission webhooks) reject RoleBindings that reference Roles that haven't been created yet.
        await _report_progress(spawner, "Setting up access controls...", 35)
        await asyncio.gather(
            _ensure_resource(
                rbac_api.create_namespaced_role,
                namespace=user_namespace,
                body=_get_role_manifest(user_role),
            ),
            _ensure_resource(
                rbac_api.create_namespaced_role,
                namespace=user_namespace,
                body=_get_role_manifest(hub_role, include_pvc=True),
            ),
            _ensure_resource(
                core_api.create_namespaced_persistent_volume_claim,
                namespace=user_namespace,
                body=pvc_manifest,
            ),
        )

        await asyncio.gather(
            _wait_for_resource(rbac_api.read_namespaced_role, name=user_role, namespace=user_namespace),
            _wait_for_resource(rbac_api.read_namespaced_role, name=hub_role, namespace=user_namespace),
        )

        await asyncio.gather(
            _ensure_resource(
                rbac_api.create_namespaced_role_binding,
                namespace=user_namespace,
                body=_get_role_binding_manifest(user_binding, "default", user_role),
            ),
            _ensure_resource(
                rbac_api.create_namespaced_role_binding,
                namespace=user_namespace,
                body=_get_role_binding_manifest(hub_binding, "hub", hub_role, namespace=hub_namespace),
            ),
        )

        await asyncio.gather(
            _wait_for_resource(rbac_api.read_namespaced_role_binding, name=user_binding, namespace=user_namespace),
            _wait_for_resource(rbac_api.read_namespaced_role_binding, name=hub_binding, namespace=user_namespace),
        )

        await _report_progress(spawner, "Waiting for resource quota...", 55)
        if rancher_project_id:
            await _wait_for_resource_quota_active(core_api, user_namespace)

        await _report_progress(spawner, "Starting sidecar containers...", 70)

        # Configure spawner
        spawner.namespace = user_namespace
        spawner.dns_name = spawner.dns_name_template.format(namespace=user_namespace, name=spawner.pod_name)
        spawner.service_account = "default"
        spawner.volumes = [{"name": volume_name, "persistentVolumeClaim": {"claimName": pvc_name}}]

        # Override hub URLs for cross-namespace access
        hub_api_base = f"http://hub.{hub_namespace}.svc.cluster.local:8081/hub/api"
        spawner.environment["JUPYTERHUB_API_URL"] = hub_api_base
        spawner.environment["JUPYTERHUB_ACTIVITY_URL"] = f"{hub_api_base}/users/{username}/activity"

        sidecar_containers = _get_sidecar_containers(spawner, bucket_name, pvc_name, volume_name, user_namespace)
        if sidecar_containers:
            spawner.extra_containers = sidecar_containers
    finally:
        await api_client.close()

    # Signal progress generator that hook is done
    await _get_or_create_progress_queue(spawner).put(None)


def modify_pod_hook(spawner: "KubeSpawner", pod: V1Pod) -> V1Pod:  # ruff:ignore[unused-function-argument]
    """
    Apply security hardening to the notebook container (e-INFRA requirement).

    Returns:
        V1Pod: The pod with updated security context on the notebook container.
    """
    if pod.spec is None:
        return pod
    for container in pod.spec.containers:
        if container.name == "notebook":
            sc = container.security_context
            if isinstance(sc, dict):
                allowed = {k: v for k, v in sc.items() if k in V1SecurityContext.openapi_types}  # type: ignore
                sc = V1SecurityContext(**allowed)  # type: ignore
            if sc is None:
                sc = V1SecurityContext()
            sc.capabilities = V1Capabilities(drop=["ALL"])
            sc.allow_privilege_escalation = False
            sc.seccomp_profile = V1SeccompProfile(type="RuntimeDefault")
            container.security_context = sc
    return pod


async def post_stop_hook(spawner: "KubeSpawner", **kwargs: object) -> None:  # ruff:ignore[unused-function-argument]
    """
    Clean up after user pod stops.

    Sets namespace quota to zero and deletes all non-preserved pods to free
    resources. Pods owned by a labeled MDRepo upload Job with
    ``mddash.io/preserve-on-stop=true`` are retained so durable uploads
    continue after server stop.
    """
    config.load_incluster_config()
    api_client = ApiClient()
    core_api = CoreV1Api(api_client)

    try:
        username: str = spawner.user.name  # type: ignore[union-attr]
        helm_package = getenv("HELM_PACKAGE", "mddash")
        user_namespace = f"{helm_package}-user-{_dns1123_label(username, max_length=DNS1123_LABEL_MAX - len(f'{helm_package}-user-') - len('-ns'))}-ns"
        rancher_project_id = getenv("RANCHER_PROJECT_ID", "")

        zero_quota_manifest = _get_namespace_manifest(user_namespace, rancher_project_id, "0", "0", "0", "0")
        await core_api.patch_namespace(name=user_namespace, body=zero_quota_manifest)  # type: ignore[misc]

        # Delete all pods except those owned by a labeled MDRepo upload Job.
        try:
            pods = await core_api.list_namespaced_pod(namespace=user_namespace)
            for pod in pods.items:
                pod_labels = getattr(getattr(pod, "metadata", None), "labels", None) or {}
                if pod_labels.get(PRESERVE_LABEL) == "true":
                    logger.info("Retaining upload pod %s during server stop", pod.metadata.name)
                    continue
                try:
                    await core_api.delete_namespaced_pod(name=pod.metadata.name, namespace=user_namespace)
                except ApiException as e:
                    if e.status != HTTPStatus.NOT_FOUND:
                        logger.warning("Failed to delete pod %s: %s", pod.metadata.name, e)
        except ApiException as e:
            logger.exception("Error listing/deleting pods in namespace %s: %s", user_namespace, e)
    finally:
        await api_client.close()


# =============================================================================
# Hook Registration
# =============================================================================

c.KubeSpawner.pre_spawn_hook = pre_spawn_hook  # type: ignore # ruff:ignore[undefined-name]
c.KubeSpawner.modify_pod_hook = modify_pod_hook  # type: ignore # ruff:ignore[undefined-name]
c.KubeSpawner.post_stop_hook = post_stop_hook  # type: ignore # ruff:ignore[undefined-name]

# progress is a plain method (not a traitlet), so c.KubeSpawner.progress is silently ignored.
# Direct monkey-patch is required to override it.
KubeSpawner.progress = _spawn_progress  # type: ignore
