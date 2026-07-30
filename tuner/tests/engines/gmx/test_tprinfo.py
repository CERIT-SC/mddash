from unittest.mock import MagicMock

import pytest
from api.engines.gmx.tprinfo import _read_sim_length_ns, parse_dump_output

DUMP_SNIPPET = """\
               init-step                  = 0
               nsteps                     = 1000000
               simulation-part            = 1
...
               delta-t                    = 0.002
"""

DUMP_SNIPPET_UNDERSCORE = """\
               nsteps                     = 250000
               delta_t                    = 0.001
"""

DUMP_SNIPPET_2026 = """\
inputrec:
   tinit                          = 0
   dt                             = 0.002
   nsteps                         = 50000
   init-step                      = 0
"""


def test_parse_dump_output_reads_nsteps_and_delta_t() -> None:
    assert parse_dump_output(DUMP_SNIPPET) == (1000000, 0.002)


def test_parse_dump_output_accepts_underscore_variant() -> None:
    assert parse_dump_output(DUMP_SNIPPET_UNDERSCORE) == (250000, 0.001)


def test_parse_dump_output_accepts_gromacs_2026_dt() -> None:
    assert parse_dump_output(DUMP_SNIPPET_2026) == (50000, 0.002)


def test_parse_dump_output_missing_values() -> None:
    assert parse_dump_output("nothing useful here") is None
    assert parse_dump_output("nsteps = 100") is None


def _mock_gmx_dump(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "subprocess.run",
        MagicMock(return_value=MagicMock(returncode=0, stdout=DUMP_SNIPPET_2026, stderr="")),
    )


def test_read_sim_length_ns_from_tpr(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_gmx_dump(monkeypatch)
    assert _read_sim_length_ns("x.tpr") == pytest.approx(50000 * 0.002 / 1000)


def test_read_sim_length_ns_nsteps_override_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_gmx_dump(monkeypatch)
    assert _read_sim_length_ns("x.tpr", nsteps_override=500000) == pytest.approx(500000 * 0.002 / 1000)
