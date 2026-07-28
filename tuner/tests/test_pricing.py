import pytest
from api.engines.amber.config import AmberBinary, AmberTrialConfig, EwaldPreset
from api.engines.gmx.config import GmxTrialConfig, NBMode, PMEMode
from api.pricing import ResourceFootprint


def _gmx(np: int = 4, ntomp: int = 2, nb: NBMode = NBMode.CPU, pme: PMEMode = PMEMode.CPU) -> GmxTrialConfig:
    return GmxTrialConfig(np=np, ntomp=ntomp, nb=nb, pme=pme)


class TestGmxFootprint:
    def test_cpu_only_config(self) -> None:
        assert _gmx().footprint == ResourceFootprint(8, 0, 16.0)

    def test_gpu_offload_adds_one_gpu(self) -> None:
        assert _gmx(nb=NBMode.GPU).footprint == ResourceFootprint(8, 1, 16.0)
        assert _gmx(np=1, ntomp=4, pme=PMEMode.GPU).footprint == ResourceFootprint(4, 1, 4.0)

    def test_ntomp_zero_counts_as_one(self) -> None:
        assert _gmx(np=2, ntomp=0).footprint == ResourceFootprint(2, 0, 8.0)


class TestAmberFootprint:
    def test_mpi_scales_with_ranks(self) -> None:
        cfg = AmberTrialConfig(binary=AmberBinary.PMEMD_MPI, np=4, ntomp=2, ewald=EwaldPreset.DEFAULT)
        assert cfg.footprint == ResourceFootprint(8, 0, 16.0)

    def test_cuda_uses_single_gpu(self) -> None:
        cfg = AmberTrialConfig(binary=AmberBinary.PMEMD_CUDA, np=1, ntomp=1, ewald=EwaldPreset.DEFAULT)
        assert cfg.footprint == ResourceFootprint(1, 1, 4.0)


class TestEstimate:
    def test_time_and_cost(self) -> None:
        # 100 ns at 100 ns/day -> 24 h; 8 cores * 0.04 + 1 GPU * 3.0 + 16 GB * 0.005 = 3.40/h
        footprint = ResourceFootprint(8, 1, 16.0)
        estimated_time, estimated_cost = footprint.estimate(100.0, 100.0)
        assert estimated_time == 24.0
        assert estimated_cost == pytest.approx(24.0 * 3.40)

    def test_scales_linearly_with_sim_length(self) -> None:
        footprint = ResourceFootprint(1, 0, 4.0)
        t1, _ = footprint.estimate(50.0, 100.0)
        t2, _ = footprint.estimate(100.0, 100.0)
        assert t2 == 2 * t1

    @pytest.mark.parametrize(("sim_length_ns", "performance"), [(None, 10.0), (100.0, None), (100.0, 0.0), (0.0, 10.0)])
    def test_null_when_unestimatable(self, sim_length_ns, performance) -> None:
        assert ResourceFootprint(8, 1, 16.0).estimate(sim_length_ns, performance) == (None, None)


def test_hourly_cost_uses_default_rates() -> None:
    # defaults: 0.04/core-h, 3.00/GPU-h, 0.005/GB-h
    assert ResourceFootprint(8, 1, 16.0).hourly_cost() == pytest.approx(8 * 0.04 + 3.0 + 16 * 0.005)
