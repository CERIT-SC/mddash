"""Unit tests for the MDPosit client module (clients/mdposit.py)."""

from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests
from clients.mdposit import (
    download_file,
    extract_accession,
    get_project,
    is_mdposit_url,
    list_files,
)

REST_URL = "https://mdrepo.eu/api/rest/v1"

# ---------------------------------------------------------------------------
# is_mdposit_url
# ---------------------------------------------------------------------------


class TestIsMdpositUrl:
    """Tests for is_mdposit_url detection logic."""

    def test_matching_host(self) -> None:
        """URL whose hostname matches a trusted host should return True."""
        assert is_mdposit_url("https://mdposit.example.com/projects/ABC123", hosts=["mdposit.example.com"])

    def test_case_insensitive_match(self) -> None:
        """Hostname comparison should be case-insensitive."""
        assert is_mdposit_url("https://MDPOSIT.EXAMPLE.COM/projects/ABC", hosts=["mdposit.example.com"])

    def test_non_matching_host(self) -> None:
        """URL whose hostname is not in the trusted set should return False."""
        assert not is_mdposit_url("https://zenodo.org/records/12345", hosts=["mdposit.example.com"])

    def test_no_hostname(self) -> None:
        """URLs without a hostname (e.g. bare path) should return False."""
        assert not is_mdposit_url("/just/a/path", hosts=["mdposit.example.com"])

    def test_empty_hosts_list(self) -> None:
        """Empty trusted-hosts list means no URL is considered MDPosit."""
        assert not is_mdposit_url("https://mdposit.example.com/p/1", hosts=[])

    def test_uses_default_hosts_when_none_provided(self) -> None:
        """When hosts is None the function falls back to config-derived defaults."""
        with patch("clients.mdposit.trusted_hosts", return_value=["mdposit.mddbr.eu"]):
            assert is_mdposit_url("https://mdposit.mddbr.eu/projects/X1")

    def test_subdomain_not_matched(self) -> None:
        """A subdomain of a trusted host must not match (exact match only)."""
        assert not is_mdposit_url("https://sub.mdposit.example.com/p/1", hosts=["mdposit.example.com"])


# ---------------------------------------------------------------------------
# extract_accession
# ---------------------------------------------------------------------------


class TestExtractAccession:
    """Tests for extract_accession parsing."""

    def test_simple_project_url(self) -> None:
        """Last non-empty path segment should be returned as accession."""
        assert extract_accession("https://mdposit.example.com/projects/ABC123") == "ABC123"

    def test_trailing_slash(self) -> None:
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

    def test_hash_route_fragment_ignored_when_path_present(self) -> None:
        """A fragment anchor must not override a path-style accession."""
        assert extract_accession("https://mdposit.example.com/projects/ABC#section") == "ABC"

    def test_root_url_returns_empty(self) -> None:
        """Root URL with no path segments should return empty string."""
        assert not extract_accession("https://mdposit.example.com")

    def test_root_url_with_slash_returns_empty(self) -> None:
        """Root URL with just a slash should return empty string."""
        assert not extract_accession("https://mdposit.example.com/")


# ---------------------------------------------------------------------------
# get_project
# ---------------------------------------------------------------------------


class TestGetProject:
    """Tests for get_project metadata lookup."""

    @patch("clients.mdposit.requests.get")
    def test_returns_project_metadata(self, mock_get: Mock) -> None:
        """Successful response returns parsed JSON dict."""
        mock_resp = Mock()
        mock_resp.status_code = HTTPStatus.OK
        mock_resp.json.return_value = {"accession": "ABC", "title": "Test"}
        mock_get.return_value = mock_resp

        result = get_project("ABC")
        assert result == {"accession": "ABC", "title": "Test"}

    @patch("clients.mdposit.requests.get")
    def test_not_found_raises_value_error(self, mock_get: Mock) -> None:
        """404 response should raise ValueError."""
        mock_resp = Mock()
        mock_resp.status_code = HTTPStatus.NOT_FOUND
        mock_get.return_value = mock_resp

        with pytest.raises(ValueError, match="not found"):
            get_project("MISSING")

    @patch("clients.mdposit.requests.get")
    def test_server_error_raises_http_error(self, mock_get: Mock) -> None:
        """Non-404 error status should raise via raise_for_status."""
        mock_resp = Mock()
        mock_resp.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_get.return_value = mock_resp

        with pytest.raises(requests.HTTPError):
            get_project("ABC")


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


class TestListFiles:
    """Tests for list_files file-list retrieval."""

    @patch("clients.mdposit.requests.get")
    def test_returns_file_names(self, mock_get: Mock) -> None:
        """Should return list of file names from the API response."""
        mock_resp = Mock()
        mock_resp.status_code = HTTPStatus.OK
        mock_resp.json.return_value = [{"name": "a.gro"}, {"name": "b.xtc"}]
        mock_get.return_value = mock_resp

        result = list_files("ABC")
        assert result == ["a.gro", "b.xtc"]

    @patch("clients.mdposit.requests.get")
    def test_not_found_returns_empty(self, mock_get: Mock) -> None:
        """404 response should return empty list (project may have no files)."""
        mock_resp = Mock()
        mock_resp.status_code = HTTPStatus.NOT_FOUND
        mock_get.return_value = mock_resp

        assert list_files("ABC") == []

    @patch("clients.mdposit.requests.get")
    def test_non_list_response_returns_empty(self, mock_get: Mock) -> None:
        """If the response body is not a list, return empty."""
        mock_resp = Mock()
        mock_resp.status_code = HTTPStatus.OK
        mock_resp.json.return_value = {"error": "unexpected"}
        mock_get.return_value = mock_resp

        assert list_files("ABC") == []

    @patch("clients.mdposit.requests.get")
    def test_string_items_converted(self, mock_get: Mock) -> None:
        """If items are plain strings instead of dicts, they should still be returned."""
        mock_resp = Mock()
        mock_resp.status_code = HTTPStatus.OK
        mock_resp.json.return_value = ["file1.gro", "file2.top"]
        mock_get.return_value = mock_resp

        result = list_files("ABC")
        assert result == ["file1.gro", "file2.top"]

    @patch("clients.mdposit.requests.get")
    def test_server_error_raises_http_error(self, mock_get: Mock) -> None:
        """Server error on list_files should propagate."""
        mock_resp = Mock()
        mock_resp.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_get.return_value = mock_resp

        with pytest.raises(requests.HTTPError):
            list_files("ABC")


# ---------------------------------------------------------------------------
# download_file
# ---------------------------------------------------------------------------


class TestDownloadFile:
    """Tests for download_file with traversal protection."""

    def test_traversal_path_rejected(self, tmp_path: Path) -> None:
        """Path traversal in filename must raise ValueError."""
        with pytest.raises(ValueError, match="Invalid MDPosit file path"):
            download_file("ABC", "../../../etc/passwd", tmp_path)

    def test_absolute_path_rejected(self, tmp_path: Path) -> None:
        """Absolute paths must raise ValueError."""
        with pytest.raises(ValueError, match="Invalid MDPosit file path"):
            download_file("ABC", "/etc/passwd", tmp_path)

    @patch("clients.mdposit.requests.get")
    def test_successful_download(self, mock_get: Mock, tmp_path: Path) -> None:
        """Valid file download should write to output_dir and return path."""
        # Build a mock streaming response whose .raw yields bytes
        raw_stream = BytesIO(b"sim-data-content")
        mock_resp = Mock()
        mock_resp.status_code = HTTPStatus.OK
        mock_resp.raise_for_status.return_value = None
        mock_resp.raw = raw_stream
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        mock_get.return_value = mock_resp

        result = download_file("ABC", "sim.gro", tmp_path)
        assert result == tmp_path / "sim.gro"
        assert (tmp_path / "sim.gro").read_bytes() == b"sim-data-content"

    @patch("clients.mdposit.requests.get")
    def test_nested_subdirectory(self, mock_get: Mock, tmp_path: Path) -> None:
        """Nested relative paths should be allowed and directories created."""
        raw_stream = BytesIO(b"nested-data")
        mock_resp = Mock()
        mock_resp.status_code = HTTPStatus.OK
        mock_resp.raise_for_status.return_value = None
        mock_resp.raw = raw_stream
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        mock_get.return_value = mock_resp

        result = download_file("ABC", "sub/dir/file.gro", tmp_path)
        assert result == tmp_path / "sub" / "dir" / "file.gro"
        assert result.exists()
        assert result.read_bytes() == b"nested-data"

    @patch("clients.mdposit.requests.get")
    def test_http_error_propagates(self, mock_get: Mock, tmp_path: Path) -> None:
        """HTTP errors from the download request should propagate."""
        mock_resp = Mock()
        mock_resp.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        mock_get.return_value = mock_resp

        with pytest.raises(requests.HTTPError):
            download_file("ABC", "sim.gro", tmp_path)


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------


class TestUrlConstruction:
    """Guards the MDPosit REST endpoint paths against regression."""

    @patch("clients.mdposit.MDPOSIT_REST_URL", REST_URL)
    @patch("clients.mdposit.requests.get")
    def test_get_project_uses_rest_v1_path(self, mock_get: Mock) -> None:
        """Project metadata must be fetched from /api/rest/v1/projects/{accession}."""
        mock_resp = Mock(status_code=HTTPStatus.OK)
        mock_resp.json.return_value = {"accession": "A0001"}
        mock_get.return_value = mock_resp

        get_project("A0001")

        assert mock_get.call_args.args[0] == f"{REST_URL}/projects/A0001"

    @patch("clients.mdposit.MDPOSIT_REST_URL", REST_URL)
    @patch("clients.mdposit.requests.get")
    def test_list_files_uses_rest_v1_path(self, mock_get: Mock) -> None:
        """File listing must be fetched from /api/rest/v1/projects/{accession}/files."""
        mock_resp = Mock(status_code=HTTPStatus.OK)
        mock_resp.json.return_value = ["structure.pdb"]
        mock_get.return_value = mock_resp

        list_files("A0001")

        assert mock_get.call_args.args[0] == f"{REST_URL}/projects/A0001/files"

    @patch("clients.mdposit.MDPOSIT_REST_URL", REST_URL)
    @patch("clients.mdposit.requests.get")
    def test_download_file_uses_rest_v1_path(self, mock_get: Mock, tmp_path: Path) -> None:
        """File download must target /api/rest/v1/projects/{accession}/files/{name}."""
        mock_resp = Mock(status_code=HTTPStatus.OK)
        mock_resp.raise_for_status.return_value = None
        mock_resp.raw = BytesIO(b"data")
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        mock_get.return_value = mock_resp

        download_file("A0001", "structure.pdb", tmp_path)

        assert mock_get.call_args.args[0] == f"{REST_URL}/projects/A0001/files/structure.pdb"
