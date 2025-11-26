import os
import asyncio
import aiohttp
from kubernetes_asyncio import config  # type: ignore
from kubernetes_asyncio.client import CoreV1Api, RbacAuthorizationV1Api, V1SecurityContext, V1Capabilities  # type: ignore
from kubernetes_asyncio.client.rest import ApiException  # type: ignore


def get_namespace_manifest(namespace, rancher_project_id, cpu_limit, mem_limit, cpu_request, mem_request):
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": namespace,
            "annotations": {
                "field.cattle.io/projectId": rancher_project_id,
                "field.cattle.io/resourceQuota": "{\"limit\":{" +
                    f"\"limitsCpu\":\"{cpu_limit}\"," +
                    f"\"limitsMemory\":\"{mem_limit}\"," +
                    f"\"requestsCpu\":\"{cpu_request}\"," +
                    f"\"requestsMemory\":\"{mem_request}\"" +
                "}}"
            }
        }
    }

def get_role_manifest(role_name):
    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {
            "name": role_name,
        },
        "rules": [
            {
                "apiGroups": [""],
                "resources": ["pods", "pods/exec", "services", "events"],
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

def get_hub_role_manifest(role_name):
    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {
            "name": role_name,
        },
        "rules": [
            {
                "apiGroups": [""],
                "resources": ["pods", "pods/exec", "services", "persistentvolumeclaims", "events"],
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

def get_role_binding_manifest(role_binding_name, service_account_name, role_name, namespace=None):
    """
    Returns a RoleBinding manifest. If namespace is provided, the subject will include it (for cross-namespace binding, e.g. hub).
    """
    subject = {
        "kind": "ServiceAccount",
        "name": service_account_name
    }
    if namespace:
        subject["namespace"] = namespace
    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "RoleBinding",
        "metadata": {
            "name": role_binding_name,
        },
        "subjects": [subject],
        "roleRef": {
            "kind": "Role",
            "name": role_name,
            "apiGroup": "rbac.authorization.k8s.io",
        },
    }

def get_pvc_manifest(pvc_name, storage_size="10Gi", storage_class="nfs-csi"):
    manifest = {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {
            "name": pvc_name,
        },
        "spec": {
            "storageClassName": storage_class,
            "accessModes": ["ReadWriteMany"],
            "resources": {
                "requests": {
                    "storage": storage_size
                }
            }
        }
    }
    return manifest


async def ensure_resource(method, **kwargs):
    try:
        await method(**kwargs)
    except ApiException as e:
        if e.status != 409:  # 409 = Already exists
            raise


async def create_s3_bucket(bucket_name):
    """Create S3 bucket using HTTP API call"""
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
                if response.status in [200, 409]:  # 200 = created, 409 = already exists
                    return
                else:
                    print(f"Failed to create bucket {bucket_name}: {response.text}")
        except Exception as e:
            print(f"Error creating bucket {bucket_name}: {e}")


def set_pod_env(spawner, bucket_name, pvc_name):
    if not hasattr(spawner, "environment"):
        spawner.environment = {}
    hub_namespace = os.environ.get("POD_NAMESPACE", "default")
    spawner.environment["HUB_NAMESPACE"] = hub_namespace
    spawner.environment["JUPYTERHUB_API_URL"] = f"http://hub.{hub_namespace}.svc.cluster.local:8081/hub/api"
    spawner.environment["PVC_NAME"] = pvc_name
    spawner.environment["PVC_STORAGE_SIZE"] = os.environ.get("PVC_STORAGE_SIZE", "10Gi")
    spawner.environment["NS_REQUESTS_CPU"] = os.environ.get("NS_REQUESTS_CPU", "1000m")
    spawner.environment["NS_REQUESTS_MEMORY"] = os.environ.get("NS_REQUESTS_MEMORY", "4Gi")
    spawner.environment["S3_BUCKET"] = bucket_name
    spawner.environment["S3_ENDPOINT"] = os.environ.get("S3_ENDPOINT", "")
    spawner.environment["S3_ACCESS_KEY"] = os.environ.get("S3_ACCESS_KEY", "")
    spawner.environment["S3_SECRET_KEY"] = os.environ.get("S3_SECRET_KEY", "")


def get_security_context():
    """Return security context for sidecar containers."""
    return {
        "allowPrivilegeEscalation": False,
        "runAsNonRoot": True,
        "capabilities": {"drop": ["ALL"]},
        "seccompProfile": {"type": "RuntimeDefault"}
    }


def get_sidecar_containers(spawner, bucket_name, pvc_name):
    """
    Configure sidecar containers for the user pod.
    These containers run alongside the notebook server to provide:
    - proxy: Caddy reverse proxy serving the React UI
    - auth: OAuth forward authentication service
    - api: Flask API backend
    - s3-sync: S3 bidirectional sync daemon
    """
    username = spawner.user.name
    hub_namespace = os.environ.get("POD_NAMESPACE", "default")
    s3_endpoint = os.environ.get("S3_ENDPOINT", "")
    
    # Get images from environment (set via extraEnv in values.yaml)
    proxy_image = os.environ.get("PROXY_IMAGE", "")
    auth_image = os.environ.get("AUTH_IMAGE", "")
    api_image = os.environ.get("API_IMAGE", "")
    s3_sync_image = os.environ.get("S3_SYNC_IMAGE", "")
    notebook_image = os.environ.get("NOTEBOOK_IMAGE", "")
    
    # Service prefix for routing
    service_prefix = f"/user/{username}"
    
    # JupyterHub OAuth variables - these come from the spawner
    jupyterhub_env = spawner.get_env()
    
    security_context = get_security_context()
    
    containers = []
    
    # Proxy container (Caddy + React UI)
    if proxy_image:
        containers.append({
            "name": "proxy",
            "image": proxy_image,
            "imagePullPolicy": "Always",
            "ports": [{"containerPort": 8888, "name": "http"}],
            "env": [
                {"name": "CADDY_ROUTE_PREFIX", "value": service_prefix},
                {"name": "JUPYTERHUB_USER", "value": username},
                {"name": "AUTH_HOST", "value": "localhost"},
                {"name": "API_HOST", "value": "localhost"},
                {"name": "NOTEBOOK_HOST", "value": "localhost"},
            ],
            "resources": {
                "requests": {"cpu": "50m", "memory": "64Mi"},
                "limits": {"cpu": "200m", "memory": "128Mi"}
            },
            "securityContext": security_context
        })
    
    # Auth container (OAuth forward auth)
    if auth_image:
        containers.append({
            "name": "auth",
            "image": auth_image,
            "imagePullPolicy": "Always",
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
                "requests": {"cpu": "50m", "memory": "64Mi"},
                "limits": {"cpu": "200m", "memory": "128Mi"}
            },
            "securityContext": security_context
        })
    
    # API container (Flask backend)
    if api_image:
        containers.append({
            "name": "api",
            "image": api_image,
            "imagePullPolicy": "Always",
            "ports": [{"containerPort": 5000, "name": "api"}],
            "env": [
                {"name": "JUPYTERHUB_USER", "value": username},
                {"name": "NOTEBOOK_IMAGE", "value": notebook_image},
                {"name": "S3_BUCKET", "value": bucket_name},
                {"name": "S3_ENDPOINT", "value": s3_endpoint},
                {"name": "S3_ACCESS_KEY", "value": os.environ.get("S3_ACCESS_KEY", "")},
                {"name": "S3_SECRET_KEY", "value": os.environ.get("S3_SECRET_KEY", "")},
                {"name": "PVC_NAME", "value": pvc_name},
                {"name": "PVC_STORAGE_SIZE", "value": os.environ.get("PVC_STORAGE_SIZE", "10Gi")},
                {"name": "NS_REQUESTS_CPU", "value": os.environ.get("NS_REQUESTS_CPU", "1000m")},
                {"name": "NS_REQUESTS_MEMORY", "value": os.environ.get("NS_REQUESTS_MEMORY", "4Gi")},
            ],
            "volumeMounts": [{"name": "volume-{username}", "mountPath": "/mddash"}],
            "resources": {
                "requests": {"cpu": "100m", "memory": "256Mi"},
                "limits": {"cpu": "500m", "memory": "512Mi"}
            },
            "securityContext": security_context
        })
    
    # S3 sync container
    if s3_sync_image:
        containers.append({
            "name": "s3-sync",
            "image": s3_sync_image,
            "imagePullPolicy": "Always",
            "env": [
                {"name": "S3_BUCKET", "value": bucket_name},
                {"name": "S3_ENDPOINT", "value": s3_endpoint},
                {"name": "S3_ACCESS_KEY", "value": os.environ.get("S3_ACCESS_KEY", "")},
                {"name": "S3_SECRET_KEY", "value": os.environ.get("S3_SECRET_KEY", "")},
            ],
            "volumeMounts": [{"name": "volume-{username}", "mountPath": "/mddash"}],
            "resources": {
                "requests": {"cpu": "50m", "memory": "64Mi"},
                "limits": {"cpu": "200m", "memory": "256Mi"}
            },
            "securityContext": security_context
        })
    
    return containers


def remove_volume_subpath(spawner):
    # static storage works with subPath, so we need to remove it from volume mounts
    for vol_mount in spawner.volume_mounts:
        if "subPath" in vol_mount:
            del vol_mount["subPath"]


async def pre_spawn_hook(spawner):
    await config.load_kube_config(config_file="/home/jovyan/.kube/config")
    core_api = CoreV1Api()
    rbac_api = RbacAuthorizationV1Api()

    username = spawner.user.name
    helm_package = os.environ.get("HELM_PACKAGE", "mddash")
    ns = f"{helm_package}-user-{username}-ns"
    hub_ns = os.environ.get("POD_NAMESPACE", "default")
    rancher_project_id = os.environ.get("RANCHER_PROJECT_ID", "")
    role_name = f"{helm_package}-user-role"
    role_binding_name = f"{helm_package}-user-binding"
    service_account_name = "default"  # use the default namespace service account
    hub_role_name = f"{helm_package}-hub-role"
    hub_role_binding_name = f"{helm_package}-hub-binding"
    hub_service_account = "hub"
    bucket_name = f"{helm_package}-user-{username}"
    pvc_name = f"{helm_package}-user-pvc"

    namespace_manifest = get_namespace_manifest(ns, rancher_project_id,
        cpu_limit=os.environ.get("NS_LIMITS_CPU", "64000m"),
        mem_limit=os.environ.get("NS_LIMITS_MEMORY", "256Gi"),
        cpu_request=os.environ.get("NS_REQUESTS_CPU", "1000m"),
        mem_request=os.environ.get("NS_REQUESTS_MEMORY", "4Gi")
    )
    role_manifest = get_role_manifest(role_name)
    role_binding_manifest = get_role_binding_manifest(role_binding_name, service_account_name, role_name)
    hub_role_manifest = get_hub_role_manifest(hub_role_name)
    hub_role_binding_manifest = get_role_binding_manifest(hub_role_binding_name, hub_service_account, hub_role_name, namespace=hub_ns)
    pvc_manifest = get_pvc_manifest(pvc_name,
        storage_size=os.environ.get("PVC_STORAGE_SIZE", "10Gi"),
        storage_class=os.environ.get("PVC_STORAGE_CLASS", "nfs-csi")
    )

    await ensure_resource(core_api.create_namespace, body=namespace_manifest)
    await asyncio.sleep(1)
    # Ensure the namespace is patched with correct resource quotas
    await core_api.patch_namespace(name=ns, body=namespace_manifest)
    await ensure_resource(rbac_api.create_namespaced_role, namespace=ns, body=role_manifest)
    await ensure_resource(rbac_api.create_namespaced_role_binding, namespace=ns, body=role_binding_manifest)
    await ensure_resource(rbac_api.create_namespaced_role, namespace=ns, body=hub_role_manifest)
    await ensure_resource(rbac_api.create_namespaced_role_binding, namespace=ns, body=hub_role_binding_manifest)
    await ensure_resource(core_api.create_namespaced_persistent_volume_claim, namespace=ns, body=pvc_manifest)

    await create_s3_bucket(bucket_name)
    

    spawner.namespace = ns
    spawner.service_account = service_account_name
    spawner.pvc_name = pvc_name

    remove_volume_subpath(spawner)
    set_pod_env(spawner, bucket_name, pvc_name)
    
    # Configure sidecar containers
    sidecar_containers = get_sidecar_containers(spawner, bucket_name, pvc_name)
    if sidecar_containers:
        spawner.extra_containers = sidecar_containers


c.KubeSpawner.pre_spawn_hook = pre_spawn_hook  # type: ignore


def modify_pod_hook(spawner, pod):
    """
    Drop all capabilities from the pod and disable privilege escalation. (e-INFRA security stuff)
    """
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

c.KubeSpawner.modify_pod_hook = modify_pod_hook  # type: ignore


async def post_stop_hook(spawner, **kwargs):
    """
    Set the namespace quota to 0 and delete all running pods after the user pod is stopped.
    """
    await config.load_kube_config(config_file="/home/jovyan/.kube/config")
    core_api = CoreV1Api()

    username = spawner.user.name
    helm_package = os.environ.get("HELM_PACKAGE", "mddash")
    ns = f"{helm_package}-user-{username}-ns"
    rancher_project_id = os.environ.get("RANCHER_PROJECT_ID", "")
    ns_manifest = get_namespace_manifest(ns, rancher_project_id, "0", "0", "0", "0")

    await core_api.patch_namespace(name=ns, body=ns_manifest)
    
    try:
        await core_api.delete_collection_namespaced_pod(namespace=ns)
    except ApiException as e:
        print(f"Error deleting pods in namespace {ns}: {e}")

c.KubeSpawner.post_stop_hook = post_stop_hook  # type: ignore
