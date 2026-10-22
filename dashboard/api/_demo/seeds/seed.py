"""
Deterministic demo data, seeded per module after the startup migrations.

Experiments come first (the other seeds hang their rows on them); files and
logs are written after the rows commit, like a real run leaves them.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from ..state import demo_state
from .analysis import seed_analyses, start_analyses
from .experiments import seed_experiments
from .runs import seed_runs, write_run_outputs
from .simulations import seed_files, seed_manifests
from .tuner import seed_tuner_jobs


def seed_data(session: Session) -> None:
    """Seed the demo database, the fake upstream state, and the experiment files."""
    demo_state.reset()
    now = datetime.now()

    experiments, notebooks = seed_experiments(now)
    tuner_jobs = seed_tuner_jobs(experiments, now)
    runs = seed_runs(experiments, now)
    analyses = seed_analyses(experiments)
    session.add_all([*experiments.values(), *notebooks, *tuner_jobs, *runs, *analyses])
    session.commit()

    start_analyses(analyses)
    seed_files()
    write_run_outputs(now)
    seed_manifests()
