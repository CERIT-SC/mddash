"""Tests for the MDDash JupyterHub pre-spawn / modify-pod / post-stop hooks."""

from __future__ import annotations

import asyncio
import builtins
import importlib.util
import json
import re
import types
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from kubernetes_asyncio.client import (
    V1Capabilities,
    V1Container,
    V1Pod,
    V1PodSpec,
    V1SeccompProfile,
    V1SecurityContext,
)
from kubernetes_asyncio.client.rest import ApiException

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


NON_ROOT_UID = 1000


# =============================================================================
# Module loading
# =============================================================================


def _load_module(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    # The hook assigns to a module-global ``c`` (JupyterHub config) at import time.
    path = Path(__file__).parents[1] / "files" / "pre_spawn_hook.py"
    monkeypatch.setattr(
        builtins,
        "c",
        SimpleNamespace(KubeSpawner=SimpleNamespace()),
        raising=False,
    )
    spec = importlib.util.spec_from_file_location("pre_spawn_hook_under_test", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _run(coro: Awaitable[object]) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


def _api_exception(status: int) -> ApiException:
    exc = ApiException(status=status)
    exc.status = status
    return exc


def _raises(exc: BaseException) -> Callable[..., object]:
    def _handler(**_kwargs: object) -> object:
        raise exc

    return _handler


# =============================================================================
# Fakes
# =============================================================================


def _noop(**_kwargs: object) -> None:
    return None


class _Recorder:
    def __init__(self, handler: Callable[..., object] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.handler: Callable[..., object] = handler or _noop

    async def __call__(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        result = self.handler(**kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result


class _FakeCoreV1Api:
    def __init__(self) -> None:
        self.create_namespace = _Recorder()
        self.patch_namespace = _Recorder()
        self.read_namespace = _Recorder()
        self.list_namespaced_resource_quota = _Recorder()
        self.create_namespaced_persistent_volume_claim = _Recorder()
        self.list_namespaced_pod = _Recorder(handler=_empty_pod_list)
        self.delete_namespaced_pod = _Recorder()


def _empty_pod_list(**_kwargs: object) -> object:
    """
    Return an empty pod list response.

    Returns:
        A SimpleNamespace with an empty items list.
    """
    return SimpleNamespace(items=[])


class _FakeRbacV1Api:
    def __init__(self) -> None:
        self.create_namespaced_role = _Recorder()
        self.read_namespaced_role = _Recorder()
        self.create_namespaced_role_binding = _Recorder()
        self.read_namespaced_role_binding = _Recorder()


class _FakeApiClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeSpawner:
    def __init__(
        self,
        username: str = "alice",
        env: dict[str, str] | None = None,
        pod_name: str = "jupyter-alice",
        dns_name_template: str = "{name}.{namespace}",
    ) -> None:
        self.user = SimpleNamespace(name=username)
        self._env = dict(env or {})
        self.namespace: str | None = None
        self.dns_name: str | None = None
        self.dns_name_template = dns_name_template
        self.pod_name = pod_name
        self.service_account: str | None = None
        self.volumes: list[dict[str, object]] | None = None
        self.environment: dict[str, str] = {}
        self.extra_containers: list[dict[str, object]] | None = None

    def get_env(self) -> dict[str, str]:
        return dict(self._env)


def _patch_k8s(
    monkeypatch: pytest.MonkeyPatch,
    module: types.ModuleType,
    core_api: _FakeCoreV1Api | None = None,
    rbac_api: _FakeRbacV1Api | None = None,
    api_client: _FakeApiClient | None = None,
) -> tuple[_FakeCoreV1Api, _FakeRbacV1Api, _FakeApiClient]:
    core_api = core_api or _FakeCoreV1Api()
    rbac_api = rbac_api or _FakeRbacV1Api()
    api_client = api_client or _FakeApiClient()

    monkeypatch.setattr(module.config, "load_incluster_config", lambda: None, raising=False)
    monkeypatch.setattr(module, "ApiClient", lambda: api_client)
    monkeypatch.setattr(module, "CoreV1Api", lambda _client: core_api)
    monkeypatch.setattr(module, "RbacAuthorizationV1Api", lambda _client: rbac_api)
    return core_api, rbac_api, api_client


def _set_images(monkeypatch: pytest.MonkeyPatch, **images: str) -> None:
    monkeypatch.setenv("IMAGE_PULL_POLICY", "IfNotPresent")
    for name, value in images.items():
        monkeypatch.setenv(name, value)


def _ns_with_conditions(*types_: str) -> SimpleNamespace:
    return SimpleNamespace(
        metadata=SimpleNamespace(
            annotations={
                "cattle.io/status": json.dumps({"Conditions": [{"Type": t, "Status": "True"} for t in types_]})
            }
        )
    )


def _notebook_pod(container: V1Container) -> V1Pod:
    return V1Pod(spec=V1PodSpec(containers=[container]))


def _configure_happy_path(core_api: _FakeCoreV1Api, *, rancher: bool) -> None:
    if rancher:
        core_api.read_namespace.handler = lambda **_kw: _ns_with_conditions("InitialRolesPopulated")
    core_api.list_namespaced_resource_quota.handler = lambda **_kw: SimpleNamespace(
        items=[SimpleNamespace(status=SimpleNamespace(hard={"requests.cpu": "2500m", "requests.memory": "6Gi"}))]
    )


# =============================================================================
# Manifest builders
# =============================================================================


def test_namespace_manifest_carries_rancher_annotations_and_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    """The namespace manifest embeds the Rancher project id and a resource-quota JSON annotation."""
    module = _load_module(monkeypatch)

    manifest = module._get_namespace_manifest("ns-1", "proj-abc", "32", "64Gi", "4", "8Gi")

    assert manifest["kind"] == "Namespace"
    assert manifest["metadata"]["name"] == "ns-1"
    annotations = manifest["metadata"]["annotations"]
    assert annotations["field.cattle.io/projectId"] == "proj-abc"
    assert json.loads(annotations["field.cattle.io/resourceQuota"]) == {
        "limit": {"limitsCpu": "32", "limitsMemory": "64Gi", "requestsCpu": "4", "requestsMemory": "8Gi"}
    }


def test_role_manifest_adds_pvc_only_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    """The user Role omits PVC access; the hub Role grants it."""
    module = _load_module(monkeypatch)

    base = module._get_role_manifest("user-role")
    with_pvc = module._get_role_manifest("hub-role", include_pvc=True)

    base_resources = base["rules"][0]["resources"]
    pvc_resources = with_pvc["rules"][0]["resources"]
    assert base_resources == ["pods", "pods/exec", "services", "events"]
    assert pvc_resources == ["pods", "pods/exec", "services", "events", "persistentvolumeclaims"]


def test_role_binding_manifest_includes_subject_namespace_only_when_given(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hub binding spans namespaces (subject namespace set); the user binding does not."""
    module = _load_module(monkeypatch)

    same_ns = module._get_role_binding_manifest("user-binding", "default", "user-role")
    cross_ns = module._get_role_binding_manifest("hub-binding", "hub", "hub-role", namespace="hub-ns")

    assert "namespace" not in same_ns["subjects"][0]
    assert cross_ns["subjects"][0]["namespace"] == "hub-ns"
    assert same_ns["roleRef"] == {"kind": "Role", "name": "user-role", "apiGroup": "rbac.authorization.k8s.io"}
    assert cross_ns["roleRef"]["name"] == "hub-role"


def test_pvc_manifest_uses_defaults_and_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """PVC defaults to 10Gi/nfs-csi but honours explicit size and class."""
    module = _load_module(monkeypatch)

    default = module._get_pvc_manifest("claim")
    custom = module._get_pvc_manifest("claim", storage_size="50Gi", storage_class="fast")

    assert default["spec"] == {
        "storageClassName": "nfs-csi",
        "accessModes": ["ReadWriteMany"],
        "resources": {"requests": {"storage": "10Gi"}},
    }
    assert custom["spec"]["storageClassName"] == "fast"
    assert custom["spec"]["resources"]["requests"]["storage"] == "50Gi"


# =============================================================================
# Security context
# =============================================================================


def test_security_context_is_hardened_non_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sidecar security contexts enforce non-root, dropped caps and seccomp."""
    module = _load_module(monkeypatch)

    sc = module._get_security_context()

    assert sc == {
        "allowPrivilegeEscalation": False,
        "runAsNonRoot": True,
        "runAsUser": NON_ROOT_UID,
        "runAsGroup": NON_ROOT_UID,
        "capabilities": {"drop": ["ALL"]},
        "seccompProfile": {"type": "RuntimeDefault"},
    }


# =============================================================================
# Kubernetes polling helpers
# =============================================================================


def test_ensure_resource_ignores_conflict_but_propagates_other_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """AlreadyExists (409) is idempotently swallowed; other statuses surface."""
    module = _load_module(monkeypatch)

    ok = _Recorder()
    conflict = _Recorder(handler=_raises(_api_exception(HTTPStatus.CONFLICT)))
    server_error = _Recorder(handler=_raises(_api_exception(HTTPStatus.INTERNAL_SERVER_ERROR)))

    _run(module._ensure_resource(ok, body={}))
    assert len(ok.calls) == 1

    _run(module._ensure_resource(conflict, body={}))

    with pytest.raises(ApiException):
        _run(module._ensure_resource(server_error, body={}))


@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        (lambda **_kw: "value", True),
        (_raises(_api_exception(HTTPStatus.NOT_FOUND)), False),
        (_raises(_api_exception(HTTPStatus.FORBIDDEN)), False),
    ],
)
def test_resource_exists_handles_found_and_missing(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[..., object], expected: bool
) -> None:
    """``_resource_exists`` treats 403/404 as absent (Rancher propagation window)."""
    module = _load_module(monkeypatch)

    method = _Recorder(handler=handler)
    assert _run(module._resource_exists(method, name="x")) is expected


def test_resource_exists_re_raises_unexpected_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 500 from the existence probe must propagate."""
    module = _load_module(monkeypatch)
    method = _Recorder(handler=_raises(_api_exception(HTTPStatus.INTERNAL_SERVER_ERROR)))

    with pytest.raises(ApiException):
        _run(module._resource_exists(method, name="x"))


def test_wait_for_resource_returns_once_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the resource exists immediately, the waiter returns without polling."""
    module = _load_module(monkeypatch)
    method = _Recorder()

    _run(module._wait_for_resource(method, timeout_s=1.0, interval=0.01, name="x"))

    assert len(method.calls) == 1


def test_wait_for_resource_times_out_when_never_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """A perpetually missing resource raises TimeoutError."""
    module = _load_module(monkeypatch)
    method = _Recorder(handler=_raises(_api_exception(HTTPStatus.NOT_FOUND)))

    with pytest.raises(TimeoutError, match="Timed out"):
        _run(module._wait_for_resource(method, timeout_s=0.05, interval=0.01, name="x"))


@pytest.mark.parametrize(
    ("annotations", "required", "expected"),
    [
        (None, {"A"}, False),
        ({}, {"A"}, False),
        ({"other": "x"}, {"A"}, False),
        ({"cattle.io/status": "not-json"}, {"A"}, False),
        ({"cattle.io/status": json.dumps({"Conditions": "nope"})}, {"A"}, False),
        ({"cattle.io/status": json.dumps({"Conditions": []})}, {"A"}, False),
        ({"cattle.io/status": json.dumps({"Conditions": [{"Type": "A", "Status": "False"}]})}, {"A"}, False),
        ({"cattle.io/status": json.dumps({"Conditions": [{"Type": "A", "Status": "True"}]})}, {"A", "B"}, False),
        (
            {
                "cattle.io/status": json.dumps({
                    "Conditions": [{"Type": "A", "Status": "True"}, {"Type": "B", "Status": "True"}]
                })
            },
            {"A", "B"},
            True,
        ),
        (
            {"cattle.io/status": json.dumps({"Conditions": [{"not-a-dict": 1}, {"Type": "A", "Status": "True"}]})},
            {"A"},
            True,
        ),
    ],
)
def test_ns_has_conditions_parses_rancher_status(
    monkeypatch: pytest.MonkeyPatch, annotations: dict[str, str] | None, required: set[str], expected: bool
) -> None:
    """Malformed/missing/partial Rancher status resolves to False; only full matches are True."""
    module = _load_module(monkeypatch)
    assert module._ns_has_conditions(annotations, required) is expected


def test_wait_for_ns_conditions_returns_when_satisfied(monkeypatch: pytest.MonkeyPatch) -> None:
    """Required conditions being met ends the wait on the first read."""
    module = _load_module(monkeypatch)
    core_api = _FakeCoreV1Api()
    core_api.read_namespace.handler = lambda **_kw: _ns_with_conditions("InitialRolesPopulated")

    _run(module._wait_for_ns_conditions(core_api, "ns", {"InitialRolesPopulated"}, timeout_s=1.0))

    assert len(core_api.read_namespace.calls) == 1


def test_wait_for_ns_conditions_swallows_propagation_errors_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 404/403 during the Rancher propagation window is retried, not fatal."""
    module = _load_module(monkeypatch)
    core_api = _FakeCoreV1Api()

    states: list[object] = [
        _api_exception(HTTPStatus.NOT_FOUND),
        _api_exception(HTTPStatus.FORBIDDEN),
        _ns_with_conditions("InitialRolesPopulated"),
    ]

    def handler(**_kw: object) -> object:
        item = states.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    core_api.read_namespace.handler = handler
    expected_reads = 3

    _run(module._wait_for_ns_conditions(core_api, "ns", {"InitialRolesPopulated"}, timeout_s=1.0, interval=0.01))
    assert len(core_api.read_namespace.calls) == expected_reads


def test_wait_for_ns_conditions_times_out_when_never_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """Conditions never appearing raises TimeoutError."""
    module = _load_module(monkeypatch)
    core_api = _FakeCoreV1Api()
    core_api.read_namespace.handler = lambda **_kw: SimpleNamespace(metadata=SimpleNamespace(annotations={}))

    with pytest.raises(TimeoutError, match="Rancher namespace conditions"):
        _run(module._wait_for_ns_conditions(core_api, "ns", {"InitialRolesPopulated"}, timeout_s=0.05, interval=0.01))


def test_wait_for_resource_quota_active_returns_when_non_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """A quota with non-zero cpu and memory ends the wait immediately."""
    module = _load_module(monkeypatch)
    core_api = _FakeCoreV1Api()
    core_api.list_namespaced_resource_quota.handler = lambda **_kw: SimpleNamespace(
        items=[SimpleNamespace(status=SimpleNamespace(hard={"requests.cpu": "2500m", "requests.memory": "6Gi"}))]
    )

    _run(module._wait_for_resource_quota_active(core_api, "ns", timeout_s=1.0, interval=0.01))
    assert len(core_api.list_namespaced_resource_quota.calls) == 1


def test_wait_for_resource_quota_active_times_out_when_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """A still-zeroed quota (left by post_stop_hook) must time out, not silently pass."""
    module = _load_module(monkeypatch)
    core_api = _FakeCoreV1Api()
    core_api.list_namespaced_resource_quota.handler = lambda **_kw: SimpleNamespace(
        items=[SimpleNamespace(status=SimpleNamespace(hard={"requests.cpu": "0", "requests.memory": "6Gi"}))]
    )

    with pytest.raises(TimeoutError, match="ResourceQuota"):
        _run(module._wait_for_resource_quota_active(core_api, "ns", timeout_s=0.05, interval=0.01))


# =============================================================================
# DNS-1123 naming
# =============================================================================


_DNS1123 = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


def _assert_valid_dns1123(label: str) -> None:
    assert _DNS1123.match(label), f"{label!r} is not a valid DNS-1123 label"


@pytest.mark.parametrize(
    "username",
    ["john.doe", "john.doe@entity.example", "ALLCAPS", "User_With_Underscores", "...leading-and-trailing..."],
)
def test_dns1123_label_sanitizes_invalid_usernames(monkeypatch: pytest.MonkeyPatch, username: str) -> None:
    """Invalid usernames become valid labels distinct from the original."""
    module = _load_module(monkeypatch)
    slug = module._dns1123_label(username)
    assert slug != username
    _assert_valid_dns1123(slug)


def test_dns1123_label_passes_through_valid_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid names pass through unchanged so existing deployments keep their namespaces."""
    module = _load_module(monkeypatch)
    for valid in ("alice", "john-doe", "user123", "a"):
        assert module._dns1123_label(valid) == valid


@pytest.mark.parametrize("bad", ["", "...", "@@@@", "___"])
def test_dns1123_label_rejects_names_with_no_valid_chars(monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    """A username with no usable characters must fail loudly, not silently collide."""
    module = _load_module(monkeypatch)
    with pytest.raises(ValueError, match="valid DNS-1123"):
        module._dns1123_label(bad)


def test_dns1123_label_disambiguates_collapsing_usernames(monkeypatch: pytest.MonkeyPatch) -> None:
    """``john.doe`` and ``john-doe`` must not collapse into the same namespace."""
    module = _load_module(monkeypatch)
    dotted = module._dns1123_label("john.doe")
    hyphenated = module._dns1123_label("john-doe")
    assert dotted != hyphenated
    assert dotted.startswith("john-doe-")
    assert hyphenated == "john-doe"


def test_dns1123_label_truncates_long_names_within_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """Long names truncate to fit max_length while remaining valid and unique."""
    module = _load_module(monkeypatch)
    budget = 20
    first = module._dns1123_label("a" * 200, max_length=budget)
    second = module._dns1123_label("a" * 199 + "b", max_length=budget)
    assert len(first) == budget
    _assert_valid_dns1123(first)
    assert first != second


def test_namespace_and_bucket_fit_dns1123_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wrapped namespace/bucket names stay within the 63-char limit for any username."""
    module = _load_module(monkeypatch)
    helm_package = "mddash"
    budget = module.DNS1123_LABEL_MAX - len(f"{helm_package}-user-") - len("-ns")

    for username in ("john.doe", "alice", "x" * 200, "User.With.Many.Dots"):
        slug = module._dns1123_label(username, max_length=budget)
        namespace = f"{helm_package}-user-{slug}-ns"
        bucket = f"{helm_package}-user-{slug}"
        assert len(namespace) <= module.DNS1123_LABEL_MAX, namespace
        assert len(bucket) <= module.DNS1123_LABEL_MAX, bucket
        _assert_valid_dns1123(namespace)
        _assert_valid_dns1123(bucket)


# =============================================================================
# Sidecar containers
# =============================================================================


def test_proxy_start_command_gates_on_health_before_caddy(monkeypatch: pytest.MonkeyPatch) -> None:
    """The proxy waits for both health endpoints with ``--fail`` before starting Caddy."""
    module = _load_module(monkeypatch)
    cmd = module._proxy_start_command("/user/alice")

    assert cmd.startswith("until ")
    assert "curl --fail" in cmd
    assert "http://localhost:5001/health" in cmd
    assert "http://localhost:5000/user/alice/dash/api/health" in cmd
    assert "sleep 0.1" in cmd
    assert cmd.rstrip().endswith("exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile")


def test_proxy_container_built_from_image_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The proxy container is built from PROXY_IMAGE and carries route/user/env."""
    module = _load_module(monkeypatch)
    _set_images(monkeypatch, PROXY_IMAGE="proxy:1", MDPOSIT_URL="https://mdposit.example.com")
    sc = module._get_security_context()

    container = module._proxy_container("/user/alice", "alice", sc)

    assert container is not None
    assert container["name"] == "proxy"
    assert container["image"] == "proxy:1"
    assert container["imagePullPolicy"] == "IfNotPresent"
    assert container["ports"] == [{"containerPort": 8888, "name": "http"}]
    env = {e["name"]: e["value"] for e in container["env"]}
    assert env["CADDY_ROUTE_PREFIX"] == "/user/alice"
    assert env["JUPYTERHUB_USER"] == "alice"
    assert env["MDPOSIT_URL"] == "https://mdposit.example.com"
    assert container["securityContext"]["runAsUser"] == NON_ROOT_UID


def test_auth_container_reads_jupyterhub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The auth container forwards JupyterHub OAuth env and the cross-namespace hub API URL."""
    module = _load_module(monkeypatch)
    _set_images(monkeypatch, AUTH_IMAGE="auth:1")
    sc = module._get_security_context()

    container = module._auth_container(
        "/user/alice",
        "alice",
        "hub-ns",
        {"JUPYTERHUB_CLIENT_ID": "cid", "JUPYTERHUB_API_TOKEN": "tok", "JUPYTERHUB_OAUTH_CALLBACK_URL": "cb"},
        sc,
    )

    assert container is not None
    env = {e["name"]: e["value"] for e in container["env"]}
    assert env["JUPYTERHUB_USER"] == "alice"
    assert env["JUPYTERHUB_CLIENT_ID"] == "cid"
    assert env["JUPYTERHUB_API_TOKEN"] == "tok"
    assert env["JUPYTERHUB_API_URL"] == "http://hub.hub-ns.svc.cluster.local:8081/hub/api"
    assert env["JUPYTERHUB_OAUTH_CALLBACK_URL"] == "cb"
    assert env["JUPYTERHUB_SERVICE_PREFIX"] == "/user/alice"
    assert env["JUPYTERHUB_DEFAULT_URL"] == "/dash"


def test_api_container_passes_through_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API container receives namespace, bucket, PVC and passthrough config env."""
    module = _load_module(monkeypatch)
    _set_images(monkeypatch, API_IMAGE="api:1", S3_ENDPOINT="https://s3.example", NS_MAX_NOTEBOOKS="5")
    sc = module._get_security_context()

    container = module._api_container(
        "/user/alice", "alice", "mddash-user-alice-ns", "hub-ns", "bucket", "pvc", "vol", sc
    )

    assert container is not None
    env = {e["name"]: e["value"] for e in container["env"]}
    assert env["POD_NAMESPACE"] == "mddash-user-alice-ns"
    assert env["HUB_NAMESPACE"] == "hub-ns"
    assert env["S3_BUCKET"] == "bucket"
    assert env["PVC_NAME"] == "pvc"
    assert env["S3_ENDPOINT"] == "https://s3.example"
    assert env["NS_MAX_NOTEBOOKS"] == "5"
    assert {"name": "vol", "mountPath": "/mddash"} in container["volumeMounts"]


def test_s3_sync_container_mounts_shared_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    """The s3-sync container mounts the shared volume and receives S3 credentials."""
    module = _load_module(monkeypatch)
    _set_images(
        monkeypatch, S3_SYNC_IMAGE="sync:1", S3_ENDPOINT="https://s3.example", S3_ACCESS_KEY="ak", S3_SECRET_KEY="sk"
    )
    sc = module._get_security_context()

    container = module._s3_sync_container("bucket", "vol", sc)

    assert container is not None
    env = {e["name"]: e["value"] for e in container["env"]}
    assert env["S3_BUCKET"] == "bucket"
    assert env["S3_ENDPOINT"] == "https://s3.example"
    assert {"name": "vol", "mountPath": "/mddash"} in container["volumeMounts"]


def test_sidecar_builders_return_none_without_image(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing sidecar image disables that sidecar rather than producing a broken container."""
    module = _load_module(monkeypatch)
    monkeypatch.delenv("PROXY_IMAGE", raising=False)
    monkeypatch.delenv("AUTH_IMAGE", raising=False)
    monkeypatch.delenv("API_IMAGE", raising=False)
    monkeypatch.delenv("S3_SYNC_IMAGE", raising=False)

    assert module._proxy_container("/u", "u", {}) is None
    assert module._auth_container("/u", "u", "ns", {}, {}) is None
    assert module._api_container("/u", "u", "ns", "ns", "b", "p", "v", {}) is None
    assert module._s3_sync_container("b", "v", {}) is None


def test_get_sidecar_containers_orders_and_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enabled sidecars appear in a stable order; disabled ones are omitted entirely."""
    module = _load_module(monkeypatch)
    _set_images(monkeypatch, PROXY_IMAGE="proxy:1", API_IMAGE="api:1", S3_SYNC_IMAGE="sync:1")  # no AUTH_IMAGE

    spawner = _FakeSpawner(username="alice", env={"JUPYTERHUB_CLIENT_ID": "cid"})
    containers = module._get_sidecar_containers(spawner, "bucket", "pvc", "vol", "mddash-user-alice-ns")

    assert [c["name"] for c in containers] == ["proxy", "api", "s3-sync"]


# =============================================================================
# Progress reporting
# =============================================================================


def test_progress_queue_is_created_once_per_spawner(monkeypatch: pytest.MonkeyPatch) -> None:
    """The progress queue is lazily created and reused for subsequent reports."""
    module = _load_module(monkeypatch)
    spawner = _FakeSpawner()

    q1 = module._get_or_create_progress_queue(spawner)
    q2 = module._get_or_create_progress_queue(spawner)

    assert q1 is q2


def test_report_progress_enqueues_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_report_progress`` puts a message/progress dict on the queue."""
    module = _load_module(monkeypatch)
    spawner = _FakeSpawner()

    _run(module._report_progress(spawner, "working", 42))

    assert _run(spawner._mddash_progress_queue.get()) == {"message": "working", "progress": 42}


def test_spawn_progress_terminates_on_sentinel_and_emits_final(monkeypatch: pytest.MonkeyPatch) -> None:
    """The generator stops on the None sentinel and always emits the final waiting message."""
    module = _load_module(monkeypatch)
    spawner = _FakeSpawner()
    queue = module._get_or_create_progress_queue(spawner)
    _run(queue.put({"message": "step", "progress": 10}))
    _run(queue.put(None))

    async def drain() -> list[dict[str, object]]:
        return [item async for item in module._spawn_progress(spawner)]

    items = _run(drain())
    assert items == [
        {"message": "step", "progress": 10},
        {"progress": 85, "message": "Waiting for MDDash to start..."},
    ]


# =============================================================================
# modify_pod_hook
# =============================================================================


def test_modify_pod_hardens_notebook_with_no_security_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """A notebook container with no security context gets full hardening."""
    module = _load_module(monkeypatch)
    pod = _notebook_pod(V1Container(name="notebook"))

    result = module.modify_pod_hook(None, pod)

    sc = result.spec.containers[0].security_context
    assert sc.capabilities == V1Capabilities(drop=["ALL"])
    assert sc.allow_privilege_escalation is False
    assert sc.seccomp_profile == V1SeccompProfile(type="RuntimeDefault")


def test_modify_pod_preserves_existing_notebook_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hardening must not wipe pre-existing settings such as runAsUser."""
    module = _load_module(monkeypatch)
    pod = _notebook_pod(V1Container(name="notebook", security_context=V1SecurityContext(run_as_user=NON_ROOT_UID)))

    sc = module.modify_pod_hook(None, pod).spec.containers[0].security_context

    assert sc.run_as_user == NON_ROOT_UID
    assert sc.capabilities == V1Capabilities(drop=["ALL"])
    assert sc.allow_privilege_escalation is False


def test_modify_pod_converts_dict_security_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """A recognized snake_case dict key is preserved when converting to a model."""
    module = _load_module(monkeypatch)
    # ``openapi_types`` uses snake_case attribute names, so those survive the filter.
    pod = _notebook_pod(V1Container(name="notebook", security_context={"run_as_user": NON_ROOT_UID}))

    sc = module.modify_pod_hook(None, pod).spec.containers[0].security_context

    assert isinstance(sc, V1SecurityContext)
    assert sc.run_as_user == NON_ROOT_UID
    assert sc.capabilities == V1Capabilities(drop=["ALL"])
    assert sc.allow_privilege_escalation is False


def test_modify_pod_drops_unrecognized_dict_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dict keys not in ``V1SecurityContext.openapi_types`` are dropped; hardening still applies."""
    module = _load_module(monkeypatch)
    pod = _notebook_pod(
        V1Container(name="notebook", security_context={"runAsUser": NON_ROOT_UID})
    )  # camelCase -> filtered

    sc = module.modify_pod_hook(None, pod).spec.containers[0].security_context

    assert isinstance(sc, V1SecurityContext)
    assert sc.run_as_user is None
    assert sc.capabilities == V1Capabilities(drop=["ALL"])


def test_modify_pod_leaves_non_notebook_containers_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the notebook container is hardened; sidecars are left as-is."""
    module = _load_module(monkeypatch)
    other = V1Container(name="sidecar", security_context=V1SecurityContext(run_as_user=0))
    pod = V1Pod(spec=V1PodSpec(containers=[V1Container(name="notebook"), other]))

    result = module.modify_pod_hook(None, pod)

    assert result.spec.containers[1] is other


def test_modify_pod_returns_pod_unchanged_without_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pod with no spec is returned unchanged."""
    module = _load_module(monkeypatch)
    pod = V1Pod(spec=None)
    assert module.modify_pod_hook(None, pod) is pod


# =============================================================================
# pre_spawn_hook
# =============================================================================


def test_pre_spawn_hook_provisions_full_user_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: namespace/RBAC/PVC are created, Rancher is awaited, and the spawner is configured."""
    module = _load_module(monkeypatch)
    monkeypatch.setenv("RANCHER_PROJECT_ID", "proj-1")
    monkeypatch.setenv("POD_NAMESPACE", "hub-ns")
    _set_images(monkeypatch, PROXY_IMAGE="p", AUTH_IMAGE="a", API_IMAGE="ap", S3_SYNC_IMAGE="s")

    core_api, rbac_api, api_client = _patch_k8s(monkeypatch, module)
    _configure_happy_path(core_api, rancher=True)
    spawner = _FakeSpawner(username="alice", env={"JUPYTERHUB_CLIENT_ID": "cid", "JUPYTERHUB_API_TOKEN": "tok"})

    _run(module.pre_spawn_hook(spawner))

    expected_namespace = "mddash-user-alice-ns"
    assert core_api.create_namespace.calls[0]["body"]["metadata"]["name"] == expected_namespace
    assert core_api.patch_namespace.calls[0]["name"] == expected_namespace
    # Roles created before bindings; hub role carries PVC access (gather is concurrent, check by content).
    role_resources = [c["body"]["rules"][0]["resources"] for c in rbac_api.create_namespaced_role.calls]
    assert any("persistentvolumeclaims" not in r for r in role_resources)
    assert any("persistentvolumeclaims" in r for r in role_resources)
    assert all(c["namespace"] == expected_namespace for c in rbac_api.create_namespaced_role.calls)
    assert core_api.create_namespaced_persistent_volume_claim.calls[0]["namespace"] == expected_namespace
    bindings = {c["body"]["metadata"]["name"]: c["body"] for c in rbac_api.create_namespaced_role_binding.calls}
    assert bindings["mddash-user-binding"]["subjects"][0] == {"kind": "ServiceAccount", "name": "default"}
    assert bindings["mddash-hub-binding"]["subjects"][0]["namespace"] == "hub-ns"

    assert spawner.namespace == expected_namespace
    assert spawner.service_account == "default"
    assert spawner.volumes == [{"name": "mddash-volume", "persistentVolumeClaim": {"claimName": "mddash-user-pvc"}}]
    assert spawner.environment["JUPYTERHUB_API_URL"] == "http://hub.hub-ns.svc.cluster.local:8081/hub/api"
    assert (
        spawner.environment["JUPYTERHUB_ACTIVITY_URL"]
        == "http://hub.hub-ns.svc.cluster.local:8081/hub/api/users/alice/activity"
    )
    assert [c["name"] for c in spawner.extra_containers] == ["proxy", "auth", "api", "s3-sync"]

    assert core_api.read_namespace.calls
    assert core_api.list_namespaced_resource_quota.calls
    assert api_client.closed
    queue = spawner._mddash_progress_queue
    enqueued: list[object] = []
    while not queue.empty():
        enqueued.append(queue.get_nowait())
    assert enqueued[-1] is None
    sidecar_progress = 70
    assert any(item.get("progress") == sidecar_progress for item in enqueued[:-1])  # type: ignore[union-attr]


def test_pre_spawn_hook_skips_rancher_waits_without_project_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a Rancher project id the hook skips the condition and quota waits."""
    module = _load_module(monkeypatch)
    monkeypatch.delenv("RANCHER_PROJECT_ID", raising=False)
    monkeypatch.setenv("POD_NAMESPACE", "hub-ns")
    _set_images(monkeypatch, PROXY_IMAGE="p")

    core_api, _, api_client = _patch_k8s(monkeypatch, module)
    # If called they would raise, proving the hook skipped them.
    core_api.read_namespace.handler = _raises(_api_exception(HTTPStatus.INTERNAL_SERVER_ERROR))
    core_api.list_namespaced_resource_quota.handler = _raises(_api_exception(HTTPStatus.INTERNAL_SERVER_ERROR))
    spawner = _FakeSpawner(username="bob")

    _run(module.pre_spawn_hook(spawner))

    assert core_api.read_namespace.calls == []
    assert core_api.list_namespaced_resource_quota.calls == []
    assert api_client.closed


def test_pre_spawn_hook_closes_client_and_signals_failure_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """On an unrecoverable API error the client is closed, the exception propagates, and no sentinel is sent."""
    module = _load_module(monkeypatch)
    monkeypatch.setenv("RANCHER_PROJECT_ID", "proj-1")
    monkeypatch.setenv("POD_NAMESPACE", "hub-ns")

    core_api, _, api_client = _patch_k8s(monkeypatch, module)
    core_api.create_namespace.handler = _raises(_api_exception(HTTPStatus.INTERNAL_SERVER_ERROR))
    spawner = _FakeSpawner(username="alice")

    with pytest.raises(ApiException):
        _run(module.pre_spawn_hook(spawner))

    assert api_client.closed
    queue = getattr(spawner, "_mddash_progress_queue", None)
    assert queue is not None
    enqueued: list[object] = []
    while not queue.empty():
        enqueued.append(queue.get_nowait())
    assert enqueued  # the "Creating user namespace..." message was sent before the failure
    assert None not in enqueued


# =============================================================================
# post_stop_hook
# =============================================================================


def test_post_stop_hook_zeroes_quota_and_deletes_pods(monkeypatch: pytest.MonkeyPatch) -> None:
    """post_stop zeroes the namespace quota and deletes all non-preserved pods."""
    module = _load_module(monkeypatch)
    monkeypatch.setenv("RANCHER_PROJECT_ID", "proj-1")

    core_api, _, api_client = _patch_k8s(monkeypatch, module)
    spawner = _FakeSpawner(username="alice")

    _run(module.post_stop_hook(spawner))

    expected_namespace = "mddash-user-alice-ns"
    patch_call = core_api.patch_namespace.calls[0]
    assert patch_call["name"] == expected_namespace
    quota = json.loads(patch_call["body"]["metadata"]["annotations"]["field.cattle.io/resourceQuota"])
    assert quota == {"limit": {"limitsCpu": "0", "limitsMemory": "0", "requestsCpu": "0", "requestsMemory": "0"}}
    assert core_api.list_namespaced_pod.calls[0]["namespace"] == expected_namespace
    assert api_client.closed


def test_post_stop_hook_swallows_pod_deletion_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failure listing/deleting pods is logged, not raised, so quota zeroing still wins."""
    module = _load_module(monkeypatch)
    monkeypatch.setenv("RANCHER_PROJECT_ID", "proj-1")

    core_api, _, api_client = _patch_k8s(monkeypatch, module)
    core_api.list_namespaced_pod.handler = _raises(_api_exception(HTTPStatus.NOT_FOUND))
    spawner = _FakeSpawner(username="alice")

    _run(module.post_stop_hook(spawner))  # must not raise

    assert core_api.patch_namespace.calls
    assert api_client.closed


def test_post_stop_hook_preserves_upload_pods(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pods labeled as MDRepo upload jobs are retained during server stop."""
    module = _load_module(monkeypatch)
    monkeypatch.setenv("RANCHER_PROJECT_ID", "proj-1")

    core_api, _, _ = _patch_k8s(monkeypatch, module)

    # Simulate two pods: one regular, one preserved upload pod.
    regular_pod = SimpleNamespace(metadata=SimpleNamespace(name="notebook-pod", labels={"app": "notebook"}))
    upload_pod = SimpleNamespace(
        metadata=SimpleNamespace(
            name="mdrepo-upload-pod",
            labels={"app": "mdrepo-uploader", "mddash.io/preserve-on-stop": "true"},
        )
    )
    core_api.list_namespaced_pod.handler = _pod_list([regular_pod, upload_pod])

    spawner = _FakeSpawner(username="alice")
    _run(module.post_stop_hook(spawner))

    # Only the regular pod should be deleted.
    deleted_names = [c["name"] for c in core_api.delete_namespaced_pod.calls]
    assert "notebook-pod" in deleted_names
    assert "mdrepo-upload-pod" not in deleted_names


def _pod_list(pods: list) -> Callable[..., object]:
    """
    Return a handler that yields the given pods.

    Returns:
        A callable that returns a SimpleNamespace with the given pods.
    """

    def handler(**_kwargs: object) -> object:
        return SimpleNamespace(items=pods)

    return handler
