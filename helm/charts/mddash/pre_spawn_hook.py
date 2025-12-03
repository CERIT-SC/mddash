import json
import os
import asyncio
import aiohttp
from kubernetes_asyncio import config  # type: ignore
from kubernetes_asyncio.client import CoreV1Api, RbacAuthorizationV1Api, V1SecurityContext, V1Capabilities  # type: ignore
from kubernetes_asyncio.client.rest import ApiException  # type: ignore


# =============================================================================
# Kubernetes Manifest Builders
# =============================================================================

def get_namespace_manifest(namespace: str, rancher_project_id: str,
                           cpu_limit: str, mem_limit: str,
                           cpu_request: str, mem_request: str) -> dict:
    resource_quota = json.dumps({
        "limit": {
            "limitsCpu": cpu_limit,
            "limitsMemory": mem_limit,
            "requestsCpu": cpu_request,
            "requestsMemory": mem_request
        }
    })
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": namespace,
            "annotations": {
                "field.cattle.io/projectId": rancher_project_id,
                "field.cattle.io/resourceQuota": resource_quota
            }
        }
    }


def get_role_manifest(role_name: str, include_pvc: bool = False) -> dict:
    resources = ["pods", "pods/exec", "services", "events"]
    if include_pvc:
        resources.append("persistentvolumeclaims")

    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {"name": role_name},
        "rules": [
            {
                "apiGroups": [""],
                "resources": resources,
                "verbs": ["create", "delete", "get", "list", "watch"]
            },
            {
                "apiGroups": [""],
                "resources": ["pods/log"],
                "verbs": ["get", "list"]
            },
            {
                "apiGroups": ["batch"],
                "resources": ["jobs"],
                "verbs": ["create", "get", "list", "watch", "update", "patch", "delete"]
            },
        ],
    }


def get_role_binding_manifest(role_binding_name: str, service_account_name: str,
                              role_name: str, namespace: str | None = None) -> dict:
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


def get_pvc_manifest(pvc_name: str, storage_size: str = "10Gi",
                     storage_class: str = "nfs-csi") -> dict:
    return {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {"name": pvc_name},
        "spec": {
            "storageClassName": storage_class,
            "accessModes": ["ReadWriteMany"],
            "resources": {"requests": {"storage": storage_size}}
        }
    }


# =============================================================================
# Helper Functions
# =============================================================================

async def ensure_resource(method, **kwargs):
    """Create a Kubernetes resource, ignoring AlreadyExists errors."""
    try:
        await method(**kwargs)
    except ApiException as e:
        if e.status != 409:
            raise


async def create_s3_bucket(bucket_name: str):
    """Create an S3 bucket if it doesn't exist."""
    s3_endpoint = os.environ.get("S3_ENDPOINT")
    access_key = os.environ.get("S3_ACCESS_KEY")
    secret_key = os.environ.get("S3_SECRET_KEY")

    if not access_key or not secret_key:
        raise ValueError("S3 credentials not found in environment variables")

    url = f"{s3_endpoint}/{bucket_name}"
    auth = aiohttp.BasicAuth(access_key, secret_key)

    async with aiohttp.ClientSession(auth=auth) as session:
        try:
            async with session.put(url) as response:
                if response.status not in [200, 409]:
                    print(f"Failed to create bucket {bucket_name}: {response.text}")
        except Exception as e:
            print(f"Error creating bucket {bucket_name}: {e}")


def get_security_context() -> dict:
    """Return hardened security context for sidecar containers."""
    return {
        "allowPrivilegeEscalation": False,
        "runAsNonRoot": True,
        "runAsUser": 1000,
        "runAsGroup": 1000,
        "capabilities": {"drop": ["ALL"]},
        "seccompProfile": {"type": "RuntimeDefault"}
    }


# =============================================================================
# Sidecar Container Builders
# =============================================================================

def _proxy_container(service_prefix: str, username: str, security_context: dict) -> dict | None:
    image = os.environ.get("PROXY_IMAGE")
    if not image:
        return None

    return {
        "name": "proxy",
        "image": image,
        "imagePullPolicy": "Always",  # TODO: Change to IfNotPresent in production
        "ports": [{"containerPort": 8888, "name": "http"}],
        "env": [
            {"name": "CADDY_ROUTE_PREFIX", "value": service_prefix},
            {"name": "JUPYTERHUB_USER", "value": username},
            {"name": "AUTH_HOST", "value": "localhost"},
            {"name": "API_HOST", "value": "localhost"},
            {"name": "NOTEBOOK_HOST", "value": "localhost"},
        ],
        "resources": {
            "requests": {"cpu": "10m", "memory": "32Mi"},
            "limits": {"cpu": "100m", "memory": "64Mi"}
        },
        "securityContext": security_context
    }


def _auth_container(service_prefix: str, username: str, hub_namespace: str,
                    jupyterhub_env: dict, security_context: dict) -> dict | None:
    image = os.environ.get("AUTH_IMAGE")
    if not image:
        return None

    return {
        "name": "auth",
        "image": image,
        "imagePullPolicy": "Always",  # TODO: Change to IfNotPresent in production
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
        "resources": {
            "requests": {"cpu": "10m", "memory": "48Mi"},
            "limits": {"cpu": "100m", "memory": "96Mi"}
        },
        "securityContext": security_context
    }


def _api_container(service_prefix: str, username: str, user_namespace: str,
                   hub_namespace: str, bucket_name: str, pvc_name: str,
                   volume_name: str, security_context: dict) -> dict | None:
    image = os.environ.get("API_IMAGE")
    if not image:
        return None

    return {
        "name": "api",
        "image": image,
        "imagePullPolicy": "Always",  # TODO: Change to IfNotPresent in production
        "ports": [{"containerPort": 5000, "name": "api"}],
        "env": [
            {"name": "JUPYTERHUB_USER", "value": username},
            {"name": "JUPYTERHUB_SERVICE_PREFIX", "value": service_prefix},
            {"name": "POD_NAMESPACE", "value": user_namespace},
            {"name": "HUB_NAMESPACE", "value": hub_namespace},
            {"name": "NOTEBOOK_IMAGE", "value": os.environ.get("NOTEBOOK_IMAGE", "")},
            {"name": "S3_BUCKET", "value": bucket_name},
            {"name": "S3_ENDPOINT", "value": os.environ.get("S3_ENDPOINT", "")},
            {"name": "S3_ACCESS_KEY", "value": os.environ.get("S3_ACCESS_KEY", "")},
            {"name": "S3_SECRET_KEY", "value": os.environ.get("S3_SECRET_KEY", "")},
            {"name": "PVC_NAME", "value": pvc_name},
            {"name": "PVC_STORAGE_SIZE", "value": os.environ.get("PVC_STORAGE_SIZE", "10Gi")},
            {"name": "NS_REQUESTS_CPU", "value": os.environ.get("NS_REQUESTS_CPU", "1000m")},
            {"name": "NS_REQUESTS_MEMORY", "value": os.environ.get("NS_REQUESTS_MEMORY", "4Gi")},
            {"name": "HOSTNAME", "value": os.environ.get("HOSTNAME", "")},
            {"name": "MDREPO_URL", "value": os.environ.get("MDREPO_URL", "")},
            {"name": "MDREPO_CLIENT_ID", "value": os.environ.get("MDREPO_CLIENT_ID", "")},
            {"name": "MDREPO_CLIENT_SECRET", "value": os.environ.get("MDREPO_CLIENT_SECRET", "")},
        ],
        "volumeMounts": [{"name": volume_name, "mountPath": "/mddash"}],
        "resources": {
            "requests": {"cpu": "50m", "memory": "128Mi"},
            "limits": {"cpu": "300m", "memory": "256Mi"}
        },
        "securityContext": security_context
    }


def _s3_sync_container(bucket_name: str, volume_name: str,
                       security_context: dict) -> dict | None:
    image = os.environ.get("S3_SYNC_IMAGE")
    if not image:
        return None

    return {
        "name": "s3-sync",
        "image": image,
        "imagePullPolicy": "Always",  # TODO: Change to IfNotPresent in production
        "env": [
            {"name": "S3_BUCKET", "value": bucket_name},
            {"name": "S3_ENDPOINT", "value": os.environ.get("S3_ENDPOINT", "")},
            {"name": "S3_ACCESS_KEY", "value": os.environ.get("S3_ACCESS_KEY", "")},
            {"name": "S3_SECRET_KEY", "value": os.environ.get("S3_SECRET_KEY", "")},
        ],
        "volumeMounts": [{"name": volume_name, "mountPath": "/mddash"}],
        "resources": {
            "requests": {"cpu": "10m", "memory": "64Mi"},
            "limits": {"cpu": "200m", "memory": "256Mi"}
        },
        "securityContext": security_context
    }


def get_sidecar_containers(spawner, bucket_name: str, pvc_name: str,
                           volume_name: str, user_namespace: str) -> list[dict]:
    """Build sidecar container configurations for the user pod."""
    username = spawner.user.name
    hub_namespace = os.environ.get("POD_NAMESPACE", "default")
    service_prefix = f"/user/{username}"
    jupyterhub_env = spawner.get_env()
    security_context = get_security_context()

    container_builders = [
        lambda: _proxy_container(service_prefix, username, security_context),
        lambda: _auth_container(service_prefix, username, hub_namespace, jupyterhub_env, security_context),
        lambda: _api_container(service_prefix, username, user_namespace, hub_namespace,
                               bucket_name, pvc_name, volume_name, security_context),
        lambda: _s3_sync_container(bucket_name, volume_name, security_context),
    ]

    return [c for builder in container_builders if (c := builder()) is not None]


# =============================================================================
# JupyterHub Spawner Hooks
# =============================================================================

async def pre_spawn_hook(spawner):
    """
    Prepare user environment before spawning the notebook server.
    Creates user namespace, RBAC, PVC, S3 bucket, and configures sidecar containers.
    """
    await config.load_kube_config(config_file="/home/jovyan/.kube/config")
    core_api = CoreV1Api()
    rbac_api = RbacAuthorizationV1Api()

    username = spawner.user.name
    helm_package = os.environ.get("HELM_PACKAGE", "mddash")
    hub_namespace = os.environ.get("POD_NAMESPACE", "default")
    rancher_project_id = os.environ.get("RANCHER_PROJECT_ID", "")

    user_namespace = f"{helm_package}-user-{username}-ns"
    bucket_name = f"{helm_package}-user-{username}"
    pvc_name = f"{helm_package}-user-pvc"
    volume_name = "mddash-volume"

    # Create namespace with resource quotas
    namespace_manifest = get_namespace_manifest(
        user_namespace, rancher_project_id,
        cpu_limit=os.environ.get("NS_LIMITS_CPU", "64000m"),
        mem_limit=os.environ.get("NS_LIMITS_MEMORY", "256Gi"),
        cpu_request=os.environ.get("NS_REQUESTS_CPU", "1000m"),
        mem_request=os.environ.get("NS_REQUESTS_MEMORY", "4Gi")
    )
    await ensure_resource(core_api.create_namespace, body=namespace_manifest)
    await asyncio.sleep(1)
    await core_api.patch_namespace(name=user_namespace, body=namespace_manifest)

    # Create RBAC for default service account (user workloads)
    user_role = f"{helm_package}-user-role"
    user_binding = f"{helm_package}-user-binding"
    await ensure_resource(rbac_api.create_namespaced_role,
                          namespace=user_namespace,
                          body=get_role_manifest(user_role))
    await ensure_resource(rbac_api.create_namespaced_role_binding,
                          namespace=user_namespace,
                          body=get_role_binding_manifest(user_binding, "default", user_role))

    # Create RBAC for hub service account (cross-namespace access)
    hub_role = f"{helm_package}-hub-role"
    hub_binding = f"{helm_package}-hub-binding"
    await ensure_resource(rbac_api.create_namespaced_role,
                          namespace=user_namespace,
                          body=get_role_manifest(hub_role, include_pvc=True))
    await ensure_resource(rbac_api.create_namespaced_role_binding,
                          namespace=user_namespace,
                          body=get_role_binding_manifest(hub_binding, "hub", hub_role, namespace=hub_namespace))

    # Create PVC for user data
    pvc_manifest = get_pvc_manifest(
        pvc_name,
        storage_size=os.environ.get("PVC_STORAGE_SIZE", "10Gi"),
        storage_class=os.environ.get("PVC_STORAGE_CLASS", "nfs-csi")
    )
    await ensure_resource(core_api.create_namespaced_persistent_volume_claim,
                          namespace=user_namespace, body=pvc_manifest)

    await create_s3_bucket(bucket_name)

    # Configure spawner
    spawner.namespace = user_namespace
    spawner.service_account = "default"
    spawner.volumes = [{"name": volume_name, "persistentVolumeClaim": {"claimName": pvc_name}}]
    spawner.volume_mounts = [{"name": volume_name, "mountPath": "/home/jovyan"}]

    # Override hub URLs for cross-namespace access
    hub_api_base = f"http://hub.{hub_namespace}.svc.cluster.local:8081/hub/api"
    if not hasattr(spawner, "environment"):
        spawner.environment = {}
    spawner.environment["JUPYTERHUB_API_URL"] = hub_api_base
    spawner.environment["JUPYTERHUB_ACTIVITY_URL"] = f"{hub_api_base}/users/{username}/activity"

    sidecar_containers = get_sidecar_containers(spawner, bucket_name, pvc_name, volume_name, user_namespace)
    if sidecar_containers:
        spawner.extra_containers = sidecar_containers


def modify_pod_hook(spawner, pod):
    """Apply security hardening to the notebook container (e-INFRA requirement)."""
    for container in pod.spec.containers:
        if container.name == "notebook":
            sc = container.security_context
            if isinstance(sc, dict):
                allowed = {k: v for k, v in sc.items() if k in V1SecurityContext.openapi_types}
                sc = V1SecurityContext(**allowed)
            if sc is None:
                sc = V1SecurityContext()
            sc.capabilities = V1Capabilities(drop=["ALL"])
            sc.allow_privilege_escalation = False
            container.security_context = sc
    return pod


async def post_stop_hook(spawner, **kwargs):
    """
    Clean up after user pod stops.
    Sets namespace quota to zero and deletes all pods to free resources.
    """
    await config.load_kube_config(config_file="/home/jovyan/.kube/config")
    core_api = CoreV1Api()

    username = spawner.user.name
    helm_package = os.environ.get("HELM_PACKAGE", "mddash")
    user_namespace = f"{helm_package}-user-{username}-ns"
    rancher_project_id = os.environ.get("RANCHER_PROJECT_ID", "")

    zero_quota_manifest = get_namespace_manifest(user_namespace, rancher_project_id, "0", "0", "0", "0")
    await core_api.patch_namespace(name=user_namespace, body=zero_quota_manifest)

    try:
        await core_api.delete_collection_namespaced_pod(namespace=user_namespace)
    except ApiException as e:
        print(f"Error deleting pods in namespace {user_namespace}: {e}")


# =============================================================================
# Hook Registration
# =============================================================================

c.KubeSpawner.pre_spawn_hook = pre_spawn_hook  # type: ignore
c.KubeSpawner.modify_pod_hook = modify_pod_hook  # type: ignore
c.KubeSpawner.post_stop_hook = post_stop_hook  # type: ignore
