from api.engines.gmx.tprinfo import parse_dump_output

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


def test_parse_dump_output_reads_nsteps_and_delta_t() -> None:
    assert parse_dump_output(DUMP_SNIPPET) == (1000000, 0.002)


def test_parse_dump_output_accepts_underscore_variant() -> None:
    assert parse_dump_output(DUMP_SNIPPET_UNDERSCORE) == (250000, 0.001)


def test_parse_dump_output_missing_values() -> None:
    assert parse_dump_output("nothing useful here") is None
    assert parse_dump_output("nsteps = 100") is None
