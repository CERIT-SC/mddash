import os
import asyncio
from kubernetes_asyncio import config  # type: ignore
from kubernetes_asyncio.client import CoreV1Api, RbacAuthorizationV1Api, V1SecurityContext, V1Capabilities  # type: ignore
from kubernetes_asyncio.client.rest import ApiException  # type: ignore


def get_namespace_manifest(namespace, rancher_project_id):
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": namespace,
            "annotations": {
                "field.cattle.io/projectId": rancher_project_id
            }
        }
    }

def get_role_manifest(role_name, rancher_project_id):
    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {
            "name": role_name,
            "annotations": {
                "field.cattle.io.projectId": rancher_project_id
            }
        },
        "rules": [
            {
                "apiGroups": [""],
                "resources": ["pods", "services", "events"],
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

def get_hub_role_manifest(role_name, rancher_project_id):
    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {
            "name": role_name,
            "annotations": {
                "field.cattle.io.projectId": rancher_project_id
            }
        },
        "rules": [
            {
                "apiGroups": [""],
                "resources": ["pods", "services", "persistentvolumeclaims", "events"],
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

def get_role_binding_manifest(role_binding_name, service_account_name, role_name, rancher_project_id, namespace=None):
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
            "annotations": {
                "field.cattle.io.projectId": rancher_project_id
            }
        },
        "subjects": [subject],
        "roleRef": {
            "kind": "Role",
            "name": role_name,
            "apiGroup": "rbac.authorization.k8s.io",
        },
    }

def get_pvc_manifest(pvc_name, rancher_project_id, storage_class=None, storage_size="10Gi"):
    manifest = {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {
            "name": pvc_name,
            "annotations": {
                "field.cattle.io/projectId": rancher_project_id
            }
        },
        "spec": {
            "accessModes": ["ReadWriteMany"],
            "resources": {
                "requests": {
                    "storage": storage_size
                }
            }
        }
    }
    if storage_class:
        manifest["spec"]["storageClassName"] = storage_class
    return manifest


async def ensure_resource(method, **kwargs):
    try:
        await method(**kwargs)
    except ApiException as e:
        if e.status != 409:  # 409 = Already exists
            raise


def set_pod_env(spawner):
    if not hasattr(spawner, 'environment'):
        spawner.environment = {}
    hub_namespace = os.environ.get("POD_NAMESPACE", "default")
    spawner.environment["HUB_NAMESPACE"] = hub_namespace
    spawner.environment["JUPYTERHUB_API_URL"] = f"http://hub.{hub_namespace}.svc.cluster.local:8081/hub/api"
    spawner.environment["JUPYTERHUB_ACTIVITY_URL"] = f"http://hub.{hub_namespace}.svc.cluster.local:8081/hub/api/users/admin/activity"


async def pre_spawn_hook(spawner):
    await config.load_kube_config(config_file="/home/jovyan/.kube/config")
    core_api = CoreV1Api()
    rbac_api = RbacAuthorizationV1Api()

    username = spawner.user.name
    ns = f"user-{username}"
    rancher_project_id = os.environ.get("RANCHER_PROJECT_ID", "")
    role_name = "mddash-user-role"
    role_binding_name = "mddash-user-binding"
    service_account_name = "default"  # use the default namespace service account
    hub_role_name = "mddash-hub-role"
    hub_role_binding_name = "mddash-hub-binding"
    hub_service_account = "hub"
    hub_namespace = os.environ.get("POD_NAMESPACE", "default")
    pvc_name = f"claim-{username}"

    namespace_manifest = get_namespace_manifest(ns, rancher_project_id)
    role_manifest = get_role_manifest(role_name, rancher_project_id)
    role_binding_manifest = get_role_binding_manifest(role_binding_name, service_account_name, role_name, rancher_project_id)
    hub_role_manifest = get_hub_role_manifest(hub_role_name, rancher_project_id)
    hub_role_binding_manifest = get_role_binding_manifest(hub_role_binding_name, hub_service_account, hub_role_name, rancher_project_id, namespace=hub_namespace)
    pvc_manifest = get_pvc_manifest(pvc_name, rancher_project_id, storage_class="nfs-csi", storage_size="10Gi")

    await ensure_resource(core_api.create_namespace, body=namespace_manifest)
    await asyncio.sleep(1)
    await ensure_resource(rbac_api.create_namespaced_role, namespace=ns, body=role_manifest)
    await ensure_resource(rbac_api.create_namespaced_role_binding, namespace=ns, body=role_binding_manifest)
    await ensure_resource(rbac_api.create_namespaced_role, namespace=ns, body=hub_role_manifest)
    await ensure_resource(rbac_api.create_namespaced_role_binding, namespace=ns, body=hub_role_binding_manifest)
    await ensure_resource(core_api.create_namespaced_persistent_volume_claim, namespace=ns, body=pvc_manifest)

    spawner.namespace = ns
    spawner.service_account = service_account_name
    spawner.pvc_name = pvc_name

    set_pod_env(spawner)


c.KubeSpawner.pre_spawn_hook = pre_spawn_hook  # type: ignore


def modify_pod_hook(spawner, pod):
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
