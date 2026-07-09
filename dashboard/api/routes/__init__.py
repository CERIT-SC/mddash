"""Routes for the dashboard API."""

from .amber import amber_bp
from .analysis import analysis_bp
from .experiments import experiments_bp
from .files import files_bp
from .gmx import gmx_bp
from .mdrepo import mdrepo_bp
from .misc import misc_bp
from .notebook import notebook_bp, notebook_config_bp
from .simulations import simulations_bp
from .tuner import tuner_bp

__all__ = [
    "amber_bp",
    "analysis_bp",
    "experiments_bp",
    "files_bp",
    "gmx_bp",
    "mdrepo_bp",
    "misc_bp",
    "notebook_bp",
    "notebook_config_bp",
    "simulations_bp",
    "tuner_bp",
]
