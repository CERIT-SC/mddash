import os
from kubernetes_asyncio import client, config  # type: ignore
from kubernetes_asyncio.client.rest import ApiException  # type: ignore


SERVICE_ACCOUNT_NAME = "mddash-user"
ROLE_NAME = "mddash-user-role"
ROLE_BINDING_NAME = "mddash-user-binding"

ROLE_MANIFEST = {
    "apiVersion": "rbac.authorization.k8s.io/v1",
    "kind": "Role",
    "metadata": {"name": ROLE_NAME},
    "rules": [
        {
            "apiGroups": [""],
            "resources": ["pods", "services"],
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

ROLE_BINDING_MANIFEST = {
    "apiVersion": "rbac.authorization.k8s.io/v1",
    "kind": "RoleBinding",
    "metadata": {"name": ROLE_BINDING_NAME},
    "subjects": [
        {
            "kind": "ServiceAccount",
            "name": SERVICE_ACCOUNT_NAME
        },
    ],
    "roleRef": {
        "kind": "Role",
        "name": ROLE_NAME,
        "apiGroup": "rbac.authorization.k8s.io",
    },
}

SERVICE_ACCOUNT_MANIFEST = {
    "apiVersion": "v1",
    "kind": "ServiceAccount",
    "metadata": {"name": SERVICE_ACCOUNT_NAME},
}

async def ensure_resource(method, manifest, namespace):
    try:
        await method(namespace=namespace, body=manifest)
    except ApiException as e:
        if e.status == 409:  # Already exists
            return
        else:
            raise

async def pre_spawn_hook(spawner):
    config.load_incluster_config()
    namespace = spawner.namespace
    core_api = client.CoreV1Api()
    rbac_api = client.RbacAuthorizationV1Api()
    await ensure_resource(core_api.create_namespaced_service_account, SERVICE_ACCOUNT_MANIFEST, namespace)
    await ensure_resource(rbac_api.create_namespaced_role, ROLE_MANIFEST, namespace)
    await ensure_resource(rbac_api.create_namespaced_role_binding, ROLE_BINDING_MANIFEST, namespace)

    spawner.service_account = SERVICE_ACCOUNT_NAME

    # Set environment variables for the pod
    if not hasattr(spawner, 'environment'):  # for compatibility
        spawner.environment = {}

    hub_namespace = os.environ.get("POD_NAMESPACE", "default")
    spawner.environment["JUPYTERHUB_API_URL"] = f"http://hub.{hub_namespace}.svc.cluster.local:8081/hub/api"
    spawner.environment["JUPYTERHUB_ACTIVITY_URL"] = f"http://hub.{hub_namespace}.svc.cluster.local:8081/hub/api/users/admin/activity"


c.KubeSpawner.pre_spawn_hook = pre_spawn_hook  # type: ignore
