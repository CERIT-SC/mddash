"""
E2E timing mode for the demo harness.

Set MDDASH_DEMO_E2E=1 to trade the demo's human-realistic timing for test speed:
single read point beside _demo/app.py so the mocks/seed/analysis modules share it.
Design: docs/specs/2026-09-22-e2e-testing-design.md
"""

import os

E2E = os.environ.get("MDDASH_DEMO_E2E") == "1"
