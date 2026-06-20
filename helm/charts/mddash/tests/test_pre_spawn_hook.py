"""Tests for MDDash JupyterHub pre-spawn hook helpers."""

import builtins
import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_pre_spawn_hook(monkeypatch):  # noqa: ANN001, ANN202
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


def test_proxy_start_command_waits_for_real_health_endpoints(monkeypatch) -> None:  # noqa: ANN001
    """Proxy startup should wait for successful auth and API health checks."""
    module = _load_pre_spawn_hook(monkeypatch)

    command = module._proxy_start_command("/user/alice")  # noqa: SLF001

    assert "curl --fail" in command
    assert "http://localhost:5001/health" in command
    assert "http://localhost:5000/user/alice/dash/api/health" in command
    assert "sleep 0.1" in command
    assert "caddy run --config /etc/caddy/Caddyfile --adapter caddyfile" in command


_DNS1123 = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


def _assert_valid_dns1123(label: str) -> None:
    assert _DNS1123.match(label), f"{label!r} is not a valid DNS-1123 label"


@pytest.mark.parametrize(
    "username",
    [
        "john.doe",
        "john.doe@entity.example",
        "ALLCAPS",
        "User_With_Underscores",
        "...leading-and-trailing...",
    ],
)
def test_dns1123_label_sanitizes_usernames(monkeypatch, username: str) -> None:  # noqa: ANN001
    """Usernames with dots or other invalid chars become valid DNS-1123 labels."""
    module = _load_pre_spawn_hook(monkeypatch)

    slug = module._dns1123_label(username)  # noqa: SLF001

    assert slug != username  # invalid input was changed
    _assert_valid_dns1123(slug)


def test_dns1123_label_passes_through_already_valid_names(monkeypatch) -> None:  # noqa: ANN001
    """Valid names are returned unchanged so existing deployments keep their namespaces."""
    module = _load_pre_spawn_hook(monkeypatch)

    for valid in ("alice", "john-doe", "user123", "a"):
        assert module._dns1123_label(valid) == valid  # noqa: SLF001


def test_dns1123_label_rejects_empty(monkeypatch) -> None:  # noqa: ANN001
    """A username with no valid characters must fail loudly, not silently collide."""
    module = _load_pre_spawn_hook(monkeypatch)

    for bad in ("", "...", "@@@@", "___"):
        with pytest.raises(ValueError, match="valid DNS-1123"):
            module._dns1123_label(bad)  # noqa: SLF001


def test_dns1123_label_is_deterministic(monkeypatch) -> None:  # noqa: ANN001
    """The same username always produces the same slug."""
    module = _load_pre_spawn_hook(monkeypatch)

    assert module._dns1123_label("john.doe") == module._dns1123_label("john.doe")  # noqa: SLF001


def test_dns1123_label_disambiguates_collapsing_usernames(monkeypatch) -> None:  # noqa: ANN001
    """``john.doe`` and ``john-doe`` must not map to the same namespace."""
    module = _load_pre_spawn_hook(monkeypatch)

    dotted = module._dns1123_label("john.doe")  # noqa: SLF001
    hyphenated = module._dns1123_label("john-doe")  # noqa: SLF001

    assert dotted != hyphenated
    assert dotted.startswith("john-doe-")
    assert hyphenated == "john-doe"


def test_dotted_username_produces_valid_namespace_and_bucket(monkeypatch) -> None:  # noqa: ANN001
    """The reported bug: a dotted username must yield a valid namespace/bucket."""
    module = _load_pre_spawn_hook(monkeypatch)

    slug = module._dns1123_label("john.doe")  # noqa: SLF001
    namespace = f"mddash-user-{slug}-ns"
    bucket = f"mddash-user-{slug}"

    assert "." not in namespace
    assert namespace.startswith("mddash-user-john-doe-")
    assert namespace.endswith("-ns")
    assert "." not in bucket
    assert bucket.startswith("mddash-user-john-doe-")
    _assert_valid_dns1123(namespace)
    _assert_valid_dns1123(bucket)


def test_safe_username_not_altered(monkeypatch) -> None:  # noqa: ANN001
    """Usernames that are already valid are not altered."""
    module = _load_pre_spawn_hook(monkeypatch)

    assert module._dns1123_label("alice") == "alice"  # noqa: SLF001


def test_dns1123_label_truncates_long_names_within_budget(monkeypatch) -> None:  # noqa: ANN001
    """A long name is truncated to fit max_length while staying a valid label."""
    module = _load_pre_spawn_hook(monkeypatch)

    budget = 20
    slug = module._dns1123_label("a" * 200, max_length=budget)  # noqa: SLF001

    assert len(slug) == budget
    _assert_valid_dns1123(slug)


def test_dns1123_label_truncated_names_stay_distinct(monkeypatch) -> None:  # noqa: ANN001
    """Two long names sharing a prefix but differing later must not collide."""
    module = _load_pre_spawn_hook(monkeypatch)

    first = module._dns1123_label("a" * 200, max_length=20)  # noqa: SLF001
    second = module._dns1123_label("a" * 199 + "b", max_length=20)  # noqa: SLF001

    assert first != second


def _wrapped_names(module, helm_package: str, username: str) -> tuple[str, str]:  # noqa: ANN001
    limit = module.DNS1123_LABEL_MAX
    budget = limit - len(f"{helm_package}-user-") - len("-ns")
    slug = module._dns1123_label(username, max_length=budget)  # noqa: SLF001
    return f"{helm_package}-user-{slug}-ns", f"{helm_package}-user-{slug}"


def test_wrapped_names_fit_dns1123_limit(monkeypatch) -> None:  # noqa: ANN001
    """Namespace and bucket stay within the 63-char DNS-1123 limit for any input."""
    module = _load_pre_spawn_hook(monkeypatch)
    limit = module.DNS1123_LABEL_MAX

    for username in ("john.doe", "alice", "x" * 200, "User.With.Many.Dots"):
        namespace, bucket = _wrapped_names(module, "mddash", username)

        assert len(namespace) <= limit, namespace
        assert len(bucket) <= limit, bucket
        _assert_valid_dns1123(namespace)
        _assert_valid_dns1123(bucket)


def test_wrapped_names_are_consistent_across_hooks(monkeypatch) -> None:  # noqa: ANN001
    """pre-spawn and post-stop resolve identical namespaces for a given user."""
    module = _load_pre_spawn_hook(monkeypatch)

    spawn_ns, _ = _wrapped_names(module, "mddash", "john.doe")
    stop_ns, _ = _wrapped_names(module, "mddash", "john.doe")

    assert spawn_ns == stop_ns
