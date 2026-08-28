"""Unit tests for _demo/analysis_data.py (MDPosit-backed analysis files)."""

import json
from urllib.parse import quote

import pytest
import responses
from _demo import analysis_data
from _demo.state import demo_state
from config import DATA_DIR
from enums import JobStatus
from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, mocker: MockerFixture):
    mocker.patch.object(analysis_data, "ANALYSIS_CACHE_DIR", tmp_path / "cache")


CLUSTERS_SUMMARY = [
    {"name": "Overall", "analysis": "clusters-00"},
    {"name": "Tight", "analysis": "clusters-01"},
]


class TestFetchAnalysisPayload:
    def test_downloads_once_and_serves_cache_afterwards(self) -> None:
        url = f"{analysis_data.MDPOSIT_ANALYSES_URL}/{quote('rmsds', safe='')}"
        with responses.RequestsMock() as rsps:
            rsps.get(url, json={"data": 1}, status=200)
            payload = analysis_data.fetch_analysis_payload("rmsds")
            assert payload == {"data": 1}
            assert len(rsps.calls) == 1

        with responses.RequestsMock() as rsps2:
            assert analysis_data.fetch_analysis_payload("rmsds") == {"data": 1}
            assert len(rsps2.calls) == 0

    def test_returns_none_for_missing_payload(self) -> None:
        url = f"{analysis_data.MDPOSIT_ANALYSES_URL}/pockets"
        with responses.RequestsMock() as rsps:
            rsps.get(url, status=404)
            assert analysis_data.fetch_analysis_payload("pockets") is None
        assert not (analysis_data.ANALYSIS_CACHE_DIR / "MD-A003ZT.2" / "pockets.json").exists()

    def test_corrupt_cache_refetches(self) -> None:
        cache_file = analysis_data.ANALYSIS_CACHE_DIR / "MD-A003ZT.2" / "rmsds.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text("{corrupt")
        url = f"{analysis_data.MDPOSIT_ANALYSES_URL}/rmsds"
        with responses.RequestsMock() as rsps:
            rsps.get(url, json={"data": 2}, status=200)
            assert analysis_data.fetch_analysis_payload("rmsds") == {"data": 2}


class TestWriteAnalysisResult:
    def test_writes_mwf_style_filename(self) -> None:
        path = analysis_data.write_analysis_result("exp-test", "md.simulation.json", "rmsd-pairwise", {"x": 1})
        assert path.name == "mda.rmsd_pairwise.json"
        assert json.loads(path.read_text()) == {"x": 1}


class TestMaterializeAnalysis:
    def _written(self, experiment_id: str, filename: str) -> list:
        return list((DATA_DIR / experiment_id).rglob(filename))

    def test_writes_the_base_payload(self, mocker: MockerFixture) -> None:
        mocker.patch.object(analysis_data, "fetch_analysis_payload", return_value={"x": 1})
        assert analysis_data.materialize_analysis("exp-base", "md.simulation.json", "rmsds")
        [result] = self._written("exp-base", "mda.rmsds.json")
        assert json.loads(result.read_text()) == {"x": 1}

    def test_summary_analyses_write_every_variant(self, mocker: MockerFixture) -> None:
        payloads = {
            "clusters": CLUSTERS_SUMMARY,
            "clusters-00": {"frames": [1]},
            "clusters-01": {"frames": [2]},
        }
        mocker.patch.object(analysis_data, "fetch_analysis_payload", side_effect=payloads.get)
        assert analysis_data.materialize_analysis("exp-summ", "md.simulation.json", "clusters")
        assert self._written("exp-summ", "mda.clusters.json")
        assert self._written("exp-summ", "mda.clusters_00.json")
        assert self._written("exp-summ", "mda.clusters_01.json")

    def test_missing_payload_writes_nothing(self, mocker: MockerFixture) -> None:
        mocker.patch.object(analysis_data, "fetch_analysis_payload", return_value=None)
        assert not analysis_data.materialize_analysis("exp-none", "md.simulation.json", "pockets")
        assert not self._written("exp-none", "mda.*.json")

    def test_unsafe_upstream_variant_names_are_skipped(self, mocker: MockerFixture) -> None:
        summary = [
            {"name": "Overall", "analysis": "clusters-00"},
            {"name": "Evil", "analysis": "../../evil"},
        ]
        payloads = {"clusters": summary, "clusters-00": {"frames": [1]}}
        fetch = mocker.patch.object(analysis_data, "fetch_analysis_payload", side_effect=payloads.get)
        assert analysis_data.materialize_analysis("exp-summ", "md.simulation.json", "clusters")
        assert fetch.call_count == 2  # base + the one safe variant, never the traversal name


class TestCompleteAnalysisWithMdposit:
    def test_finishes_with_materialized_files(self, mocker: MockerFixture) -> None:
        demo_state.analysis_jobs["job-t"] = {"status": JobStatus.RUNNING.value}
        try:
            mocker.patch.object(analysis_data, "materialize_analysis", return_value=True)
            analysis_data.complete_analysis_with_mdposit("job-t", "exp-test", "md.simulation.json", "rmsds", 0)
            assert demo_state.analysis_jobs["job-t"]["status"] == JobStatus.FINISHED.value
        finally:
            demo_state.analysis_jobs.pop("job-t", None)

    def test_missing_payload_marks_the_job_failed(self, mocker: MockerFixture) -> None:
        demo_state.analysis_jobs["job-t"] = {"status": JobStatus.RUNNING.value}
        try:
            mocker.patch.object(analysis_data, "materialize_analysis", return_value=False)
            analysis_data.complete_analysis_with_mdposit("job-t", "exp-test", "md.simulation.json", "pockets", 0)
            assert demo_state.analysis_jobs["job-t"]["status"] == JobStatus.ERROR.value
        finally:
            demo_state.analysis_jobs.pop("job-t", None)
