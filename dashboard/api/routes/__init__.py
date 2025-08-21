"""Routes for the dashboard API."""

from .experiments import experiments_bp
from .notebook import notebook_bp
from .tuner import tuner_bp
from .gmx import gmx_bp
from .files import files_bp
from .misc import misc_bp


__all__ = [
    'experiments_bp',
    'notebook_bp',
    'tuner_bp',
    'gmx_bp',
    'files_bp',
    'misc_bp'
]
