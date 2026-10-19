"""Unit tests for MDPosit configuration derivation (config.py)."""

from core import config


class TestMdpositConfigConstants:
    """Constant pins for MDPOSIT integration settings."""

    def test_trusted_parent_host_constant(self) -> None:
        """MDPOSIT_TRUSTED_PARENT_HOST should be 'mdposit.mddbr.eu'."""
        assert config.MDPOSIT_TRUSTED_PARENT_HOST == "mdposit.mddbr.eu"
