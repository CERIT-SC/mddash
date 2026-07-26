from api.engines.amber.config import EwaldPreset
from api.engines.amber.mdin import patch_mdin_for_benchmark

MINIMAL_MDIN = """\
Benchmark run
 &cntrl
  imin   = 0,
  irest  = 1,
  ntx    = 5,
  nstlim = 500000,
  dt     = 0.002,
  ntc    = 2,
  ntf    = 2,
  ntb    = 2,
  ntp    = 1,
  ntt    = 3,
  gamma_ln = 1.0,
  temp0  = 300.0,
  ntpr   = 1000,
  ntwx   = 500,
  ntwr   = 10000,
  ntave  = 100,
 /
"""


def test_nstlim_overridden() -> None:
    result = patch_mdin_for_benchmark(MINIMAL_MDIN, nsteps=10000, ewald=EwaldPreset.DEFAULT)
    assert "nstlim = 10000" in result
    assert "nstlim = 500000" not in result


def test_ntwx_set_to_zero() -> None:
    result = patch_mdin_for_benchmark(MINIMAL_MDIN, nsteps=10000, ewald=EwaldPreset.DEFAULT)
    assert "ntwx = 0" in result


def test_ntwr_set_to_zero() -> None:
    result = patch_mdin_for_benchmark(MINIMAL_MDIN, nsteps=10000, ewald=EwaldPreset.DEFAULT)
    assert "ntwr = 0" in result


def test_ntave_set_to_zero() -> None:
    result = patch_mdin_for_benchmark(MINIMAL_MDIN, nsteps=10000, ewald=EwaldPreset.DEFAULT)
    assert "ntave = 0" in result


def test_ntpr_capped_at_5000() -> None:
    result = patch_mdin_for_benchmark(MINIMAL_MDIN, nsteps=10000, ewald=EwaldPreset.DEFAULT)
    assert "ntpr = 5000" in result


def test_ntpr_equals_nsteps_when_small() -> None:
    result = patch_mdin_for_benchmark(MINIMAL_MDIN, nsteps=100, ewald=EwaldPreset.DEFAULT)
    assert "ntpr = 100" in result


def test_physics_params_preserved() -> None:
    result = patch_mdin_for_benchmark(MINIMAL_MDIN, nsteps=10000, ewald=EwaldPreset.DEFAULT)
    assert "temp0  = 300.0" in result
    assert "gamma_ln = 1.0" in result
    assert "ntc    = 2" in result


def test_ewald_default_no_ewald_block_added() -> None:
    result = patch_mdin_for_benchmark(MINIMAL_MDIN, nsteps=10000, ewald=EwaldPreset.DEFAULT)
    assert "&ewald" not in result


def test_ewald_optimized_adds_ewald_block() -> None:
    result = patch_mdin_for_benchmark(MINIMAL_MDIN, nsteps=10000, ewald=EwaldPreset.OPTIMIZED)
    assert "&ewald" in result
    assert "netfrc = 0" in result
    assert "skin_permit = 0.75" in result


def test_ewald_optimized_existing_ewald_block_overridden() -> None:
    mdin_with_ewald = MINIMAL_MDIN + "\n &ewald\n  netfrc = 1,\n /\n"
    result = patch_mdin_for_benchmark(mdin_with_ewald, nsteps=10000, ewald=EwaldPreset.OPTIMIZED)
    assert result.count("netfrc = 0") == 1
    assert "netfrc = 1" not in result
