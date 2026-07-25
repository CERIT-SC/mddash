"""Unit tests for the manifest schema URL resolver."""

from enums import Engine
from manifest_schema import resolve_schema_url, schema_url

GMX_URL = "https://raw.githubusercontent.com/CERIT-SC/mddash/v0.1.4/dashboard/api/manifest_schemas/gromacs.schema.json"
AMBER_URL = "https://raw.githubusercontent.com/CERIT-SC/mddash/v0.1.4/dashboard/api/manifest_schemas/amber.schema.json"


class TestSchemaUrl:
    """schema_url builds the master-ref mddash schema URL."""

    def test_gmx_url(self) -> None:
        """GMX URL points at the bundled gromacs schema on master."""
        assert schema_url(Engine.GMX) == GMX_URL

    def test_amber_url(self) -> None:
        """AMBER URL points at the bundled amber schema on master."""
        assert schema_url(Engine.AMBER) == AMBER_URL


class TestResolveSchemaUrl:
    """resolve_schema_url maps whitelisted mddash URLs to bundled schemas."""

    def test_resolves_gmx_url_to_bundled_schema(self) -> None:
        """A valid GMX URL resolves to the bundled GROMACS schema."""
        schema = resolve_schema_url(GMX_URL)
        assert schema is not None
        assert schema["title"] == "MDDash GROMACS simulation manifest"

    def test_resolves_amber_url_to_bundled_schema(self) -> None:
        """A valid AMBER URL resolves to the bundled AMBER schema."""
        schema = resolve_schema_url(AMBER_URL)
        assert schema is not None
        assert schema["title"] == "MDDash AMBER simulation manifest"

    def test_accepts_any_ref_tag_or_branch(self) -> None:
        """Any ref (tag, branch, or slash-bearing branch) is accepted."""
        for ref in ("v0.1.0", "v9.9.9", "master", "main", "feature/x"):
            url = (
                "https://raw.githubusercontent.com/CERIT-SC/mddash/"
                f"{ref}/dashboard/api/manifest_schemas/gromacs.schema.json"
            )
            assert resolve_schema_url(url) is not None, ref

    def test_rejects_non_mddash_url(self) -> None:
        """A URL pointing at a different repo is rejected."""
        assert resolve_schema_url("https://raw.githubusercontent.com/evil/repo/main/gromacs.schema.json") is None

    def test_rejects_relative_path(self) -> None:
        """A relative file path is rejected."""
        assert resolve_schema_url("./gromacs.schema.json") is None

    def test_rejects_arbitrary_url(self) -> None:
        """An arbitrary non-GitHub URL is rejected."""
        assert resolve_schema_url("https://example.com/schema.json") is None

    def test_rejects_non_string(self) -> None:
        """Non-string inputs are rejected."""
        assert resolve_schema_url(None) is None  # type: ignore[arg-type]
        assert resolve_schema_url(123) is None  # type: ignore[arg-type]

    def test_rejects_wrong_filename(self) -> None:
        """A URL with an unrecognized schema filename is rejected."""
        url = (
            "https://raw.githubusercontent.com/CERIT-SC/mddash/v0.1.0/dashboard/api/manifest_schemas/other.schema.json"
        )
        assert resolve_schema_url(url) is None
