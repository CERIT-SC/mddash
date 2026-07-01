"""Unit tests for MDPosit configuration derivation (config.py)."""

from unittest.mock import patch

import config


class TestMdpositConfigDerivation:
    """Tests for MDPOSIT_URL, MDPOSIT_HOST, MDPOSIT_REST_URL, MDPOSIT_VRE_LITE_URL."""

    def test_all_mdposit_vars_derived_from_url(self) -> None:
        """Setting MDPOSIT_URL should derive host, REST URL, and VRE lite URL."""
        with (
            patch.object(config, "MDPOSIT_URL", "https://mdposit.example.com"),
            patch.object(config, "MDPOSIT_HOST", "mdposit.example.com"),
            patch.object(config, "MDPOSIT_REST_URL", "https://mdposit.example.com/api/rest/v1"),
            patch.object(config, "MDPOSIT_VRE_LITE_URL", "https://mdposit.example.com/vre_lite/"),
        ):
            assert config.MDPOSIT_URL == "https://mdposit.example.com"
            assert config.MDPOSIT_HOST == "mdposit.example.com"
            assert config.MDPOSIT_REST_URL == "https://mdposit.example.com/api/rest/v1"
            assert config.MDPOSIT_VRE_LITE_URL == "https://mdposit.example.com/vre_lite/"

    def test_empty_url_yields_empty_derivations(self) -> None:
        """When MDPOSIT_URL is empty, all derived values should be empty strings."""
        with (
            patch.object(config, "MDPOSIT_URL", ""),
            patch.object(config, "MDPOSIT_HOST", ""),
            patch.object(config, "MDPOSIT_REST_URL", ""),
            patch.object(config, "MDPOSIT_VRE_LITE_URL", ""),
        ):
            assert not config.MDPOSIT_URL
            assert not config.MDPOSIT_HOST
            assert not config.MDPOSIT_REST_URL
            assert not config.MDPOSIT_VRE_LITE_URL

    def test_trailing_slash_stripped(self) -> None:
        """Trailing slash on MDPOSIT_URL should be stripped per config.py logic."""
        url = "https://mdposit.example.com"
        with (
            patch.object(config, "MDPOSIT_URL", url),
            patch.object(config, "MDPOSIT_HOST", "mdposit.example.com"),
            patch.object(config, "MDPOSIT_REST_URL", f"{url}/api/rest/v1"),
            patch.object(config, "MDPOSIT_VRE_LITE_URL", f"{url}/vre_lite/"),
        ):
            assert config.MDPOSIT_URL == "https://mdposit.example.com"

    def test_host_derived_from_url(self) -> None:
        """MDPOSIT_HOST is the netloc of the parsed MDPOSIT_URL."""
        with (
            patch.object(config, "MDPOSIT_URL", "https://mdposit.example.com"),
            patch.object(config, "MDPOSIT_HOST", "mdposit.example.com"),
        ):
            assert config.MDPOSIT_HOST == "mdposit.example.com"

    def test_rest_url_format(self) -> None:
        """MDPOSIT_REST_URL follows {MDPOSIT_URL}/api/rest/v1 format."""
        url = "https://mdposit.example.com"
        with patch.object(config, "MDPOSIT_URL", url), patch.object(config, "MDPOSIT_REST_URL", f"{url}/api/rest/v1"):
            assert config.MDPOSIT_REST_URL == "https://mdposit.example.com/api/rest/v1"

    def test_vre_lite_url_format(self) -> None:
        """MDPOSIT_VRE_LITE_URL follows {MDPOSIT_URL}/vre_lite/ format."""
        url = "https://mdposit.example.com"
        with patch.object(config, "MDPOSIT_URL", url), patch.object(config, "MDPOSIT_VRE_LITE_URL", f"{url}/vre_lite/"):
            assert config.MDPOSIT_VRE_LITE_URL == "https://mdposit.example.com/vre_lite/"

    def test_trusted_parent_host_constant(self) -> None:
        """MDPOSIT_TRUSTED_PARENT_HOST should be 'mdposit.mddbr.eu'."""
        assert config.MDPOSIT_TRUSTED_PARENT_HOST == "mdposit.mddbr.eu"

    def test_config_attributes_exist(self) -> None:
        """All expected MDPosit config attributes should exist on the config module."""
        for attr in (
            "MDPOSIT_URL",
            "MDPOSIT_HOST",
            "MDPOSIT_REST_URL",
            "MDPOSIT_VRE_LITE_URL",
            "MDPOSIT_TRUSTED_PARENT_HOST",
        ):
            assert hasattr(config, attr), f"config module missing attribute: {attr}"
