"""Tests verifying Helm values.yaml.tmpl and pre_spawn_hook.py pass MDPOSIT_URL to API sidecars."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
VALUES_TMPL = REPO_ROOT / "helm" / "charts" / "mddash" / "values.yaml.tmpl"
PRE_SPAWN_HOOK = REPO_ROOT / "helm" / "charts" / "mddash" / "files" / "pre_spawn_hook.py"


class TestHelmMdpositRendering:
    """Verify that Helm templates include MDPOSIT_URL in the API sidecar env."""

    def test_values_tmpl_contains_mdposit_url(self) -> None:
        """values.yaml.tmpl must render MDPOSIT_URL for the singleuser API container."""
        content = VALUES_TMPL.read_text()
        assert "MDPOSIT_URL:" in content, "MDPOSIT_URL env var not found in values.yaml.tmpl"

    def test_values_tmpl_mdposit_references_config(self) -> None:
        """The MDPOSIT_URL value should be templated from $cfg.mdposit.url."""
        content = VALUES_TMPL.read_text()
        assert "mdposit.url" in content, "MDPOSIT_URL does not reference mdposit config"

    def test_pre_spawn_hook_includes_mdposit_url_in_passthrough(self) -> None:
        """pre_spawn_hook.py must include MDPOSIT_URL in _API_PASSTHROUGH_ENV."""
        content = PRE_SPAWN_HOOK.read_text()
        assert '"MDPOSIT_URL"' in content, "MDPOSIT_URL not in passthrough env list"

    def test_pre_spawn_hook_api_container_uses_passthrough(self) -> None:
        """The _api_container function must inject _API_PASSTHROUGH_ENV into container env."""
        content = PRE_SPAWN_HOOK.read_text()
        assert "_API_PASSTHROUGH_ENV" in content
        # The env injection line uses getenv over the passthrough keys
        assert "getenv(k" in content or "getenv(" in content
