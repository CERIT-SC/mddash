"""Unit tests for the MDPosit client module (clients/mdposit.py)."""

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx
from clients import Clients
from clients.mdposit import MDPositClient, extract_accession, is_mdposit_url

REST_URL = "https://mdrepo.eu/api/rest/v1"


@pytest.fixture
def mdposit(clients: Clients) -> MDPositClient:
    return MDPositClient(clients.http, REST_URL)


# ---------------------------------------------------------------------------
# is_mdposit_url
# ---------------------------------------------------------------------------


class TestIsMdpositUrl:
    """Tests for is_mdposit_url detection logic."""

    def test_matching_host(self, mdposit: MDPositClient) -> None:
        """URL whose hostname matches a trusted host should return True."""
        assert is_mdposit_url("https://mdposit.example.com/projects/ABC123", hosts=["mdposit.example.com"])

    def test_case_insensitive_match(self, mdposit: MDPositClient) -> None:
        """Hostname comparison should be case-insensitive."""
        assert is_mdposit_url("https://MDPOSIT.EXAMPLE.COM/projects/ABC", hosts=["mdposit.example.com"])

    def test_non_matching_host(self, mdposit: MDPositClient) -> None:
        """URL whose hostname is not in the trusted set should return False."""
        assert not is_mdposit_url("https://zenodo.org/records/12345", hosts=["mdposit.example.com"])

    def test_no_hostname(self, mdposit: MDPositClient) -> None:
        """URLs without a hostname (e.g. bare path) should return False."""
        assert not is_mdposit_url("/just/a/path", hosts=["mdposit.example.com"])

    def test_empty_hosts_list(self, mdposit: MDPositClient) -> None:
        """Empty trusted-hosts list means no URL is considered MDPosit."""
        assert not is_mdposit_url("https://mdposit.example.com/p/1", hosts=[])

    def test_uses_default_hosts_when_none_provided(self, mdposit: MDPositClient) -> None:
        """When hosts is None the function falls back to config-derived defaults."""
        with patch("clients.mdposit.trusted_hosts", return_value=["mdposit.mddbr.eu"]):
            assert is_mdposit_url("https://mdposit.mddbr.eu/projects/X1")

    def test_subdomain_not_matched(self, mdposit: MDPositClient) -> None:
        """A subdomain of a trusted host must not match (exact match only)."""
        assert not is_mdposit_url("https://sub.mdposit.example.com/p/1", hosts=["mdposit.example.com"])


# ---------------------------------------------------------------------------
# extract_accession
# ---------------------------------------------------------------------------


class TestExtractAccession:
    """Tests for extract_accession parsing."""

    def test_simple_project_url(self, mdposit: MDPositClient) -> None:
        """Last non-empty path segment should be returned as accession."""
        assert extract_accession("https://mdposit.example.com/projects/ABC123") == "ABC123"

    def test_trailing_slash(self, mdposit: MDPositClient) -> None:
        """Trailing slashes should be stripped before extracting."""
        assert extract_accession("https://mdposit.example.com/projects/ABC123/") == "ABC123"

    def test_nested_path(self) -> None:
        """Only the last segment matters regardless of nesting depth."""
        assert extract_accession("https://host/a/b/c/MY_ACCESSION") == "MY_ACCESSION"

    def test_hash_routed_detail_url(self) -> None:
        """SPA hash route #/id/{accession}/overview must yield the accession."""
        assert extract_accession("https://mdrepo.eu/#/id/A0001/overview") == "A0001"

    def test_hash_routed_detail_url_without_tab(self) -> None:
        """Hash route ending at the accession (#/id/{accession}) must still work."""
        assert extract_accession("https://mdrepo.eu/#/id/A0001") == "A0001"

    def test_hash_route_fragment_ignored_when_path_present(self, mdposit: MDPositClient) -> None:
        """A fragment anchor must not override a path-style accession."""
        assert extract_accession("https://mdposit.example.com/projects/ABC#section") == "ABC"

    def test_root_url_returns_empty(self, mdposit: MDPositClient) -> None:
        """Root URL with no path segments should return empty string."""
        assert not extract_accession("https://mdposit.example.com")

    def test_root_url_with_slash_returns_empty(self, mdposit: MDPositClient) -> None:
        """Root URL with just a slash should return empty string."""
        assert not extract_accession("https://mdposit.example.com/")


# ---------------------------------------------------------------------------
# get_project
# ---------------------------------------------------------------------------


class TestGetProject:
    """Tests for get_project metadata lookup (served from /api/rest/v1/projects/{accession})."""

    async def test_returns_project_metadata(self, http_mock: respx.MockRouter, mdposit: MDPositClient) -> None:
        http_mock.get(f"{REST_URL}/projects/ABC").mock(
            return_value=httpx.Response(200, json={"accession": "ABC", "title": "Test"})
        )
        assert await mdposit.get_project("ABC") == {"accession": "ABC", "title": "Test"}

    async def test_not_found_raises_value_error(self, http_mock: respx.MockRouter, mdposit: MDPositClient) -> None:
        http_mock.get(f"{REST_URL}/projects/MISSING").mock(return_value=httpx.Response(404))
        with pytest.raises(ValueError, match="not found"):
            await mdposit.get_project("MISSING")

    async def test_server_error_raises_http_error(self, http_mock: respx.MockRouter, mdposit: MDPositClient) -> None:
        http_mock.get(f"{REST_URL}/projects/ABC").mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            await mdposit.get_project("ABC")


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


class TestListFiles:
    """Tests for list_files file-list retrieval (served from /api/rest/v1/projects/{accession}/files)."""

    async def test_returns_file_names(self, http_mock: respx.MockRouter, mdposit: MDPositClient) -> None:
        http_mock.get(f"{REST_URL}/projects/ABC/files").mock(
            return_value=httpx.Response(200, json=[{"name": "a.gro"}, {"name": "b.xtc"}])
        )
        assert await mdposit.list_files("ABC") == ["a.gro", "b.xtc"]

    async def test_not_found_returns_empty(self, http_mock: respx.MockRouter, mdposit: MDPositClient) -> None:
        """A project may have no files."""
        http_mock.get(f"{REST_URL}/projects/ABC/files").mock(return_value=httpx.Response(404))
        assert await mdposit.list_files("ABC") == []

    async def test_non_list_response_returns_empty(self, http_mock: respx.MockRouter, mdposit: MDPositClient) -> None:
        http_mock.get(f"{REST_URL}/projects/ABC/files").mock(
            return_value=httpx.Response(200, json={"error": "unexpected"})
        )
        assert await mdposit.list_files("ABC") == []

    async def test_string_items_converted(self, http_mock: respx.MockRouter, mdposit: MDPositClient) -> None:
        http_mock.get(f"{REST_URL}/projects/ABC/files").mock(
            return_value=httpx.Response(200, json=["file1.gro", "file2.top"])
        )
        assert await mdposit.list_files("ABC") == ["file1.gro", "file2.top"]

    async def test_server_error_raises_http_error(self, http_mock: respx.MockRouter, mdposit: MDPositClient) -> None:
        http_mock.get(f"{REST_URL}/projects/ABC/files").mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            await mdposit.list_files("ABC")


# ---------------------------------------------------------------------------
# download_file
# ---------------------------------------------------------------------------


class TestDownloadFile:
    """Tests for download_file with traversal protection."""

    async def test_traversal_path_rejected(self, tmp_path: Path, mdposit: MDPositClient) -> None:
        with pytest.raises(ValueError, match="Invalid MDPosit file path"):
            await mdposit.download_file("ABC", "../../../etc/passwd", tmp_path)

    async def test_absolute_path_rejected(self, tmp_path: Path, mdposit: MDPositClient) -> None:
        with pytest.raises(ValueError, match="Invalid MDPosit file path"):
            await mdposit.download_file("ABC", "/etc/passwd", tmp_path)

    async def test_successful_download(
        self, http_mock: respx.MockRouter, tmp_path: Path, mdposit: MDPositClient
    ) -> None:
        route = http_mock.get(f"{REST_URL}/projects/ABC/files/sim.gro").mock(
            return_value=httpx.Response(200, content=b"sim-data-content")
        )
        result = await mdposit.download_file("ABC", "sim.gro", tmp_path)
        assert route.call_count == 1
        assert result == tmp_path / "sim.gro"
        assert (tmp_path / "sim.gro").read_bytes() == b"sim-data-content"

    async def test_nested_subdirectory(
        self, http_mock: respx.MockRouter, tmp_path: Path, mdposit: MDPositClient
    ) -> None:
        """Nested relative paths are allowed and their directories created."""
        http_mock.get(f"{REST_URL}/projects/ABC/files/sub/dir/file.gro").mock(
            return_value=httpx.Response(200, content=b"nested-data")
        )
        result = await mdposit.download_file("ABC", "sub/dir/file.gro", tmp_path)
        assert result == tmp_path / "sub" / "dir" / "file.gro"
        assert result.read_bytes() == b"nested-data"

    async def test_http_error_propagates(
        self, http_mock: respx.MockRouter, tmp_path: Path, mdposit: MDPositClient
    ) -> None:
        http_mock.get(f"{REST_URL}/projects/ABC/files/sim.gro").mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            await mdposit.download_file("ABC", "sim.gro", tmp_path)
