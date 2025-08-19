import logging
from flask import Blueprint, request
from flask_sqlalchemy import SQLAlchemy

from api_response import ApiResponse, Response
from models import Experiment
from schemas import ExperimentSchema

db = SQLAlchemy()
logger = logging.getLogger(__name__)
experiments_bp = Blueprint('experiments', __name__)


@experiments_bp.route('/api/experiments', methods=['GET'])
def list_experiments() -> Response:
    experiments: list[Experiment] = Experiment.query.all()
    schema = ExperimentSchema(many=True)
    return ApiResponse.success(schema.dump(experiments))


@experiments_bp.route('/api/experiments', methods=['POST'])
def create_experiment() -> Response:
    schema = ExperimentSchema()
    form = request.form

    try:
        name = form['experiment-name']
        pdb_id = form.get('pdb-id', 'XXX:fake')
        repo_url = form.get('repo-url')
        simulation_file = request.files.get('simulation-file')

        logger.debug(f'{request.form}')
        match form['type']:
            case 'pdb' if pdb_id:
                experiment = Experiment.from_pdb(name, pdb_id)
            case 'repo' if repo_url:
                experiment = Experiment.from_repo(name, repo_url)
            case 'file' if simulation_file:
                experiment = Experiment.from_tpr(name, simulation_file)
            case _:
                return ApiResponse.error('Invalid experiment type or missing data.')

        db.session.add(experiment)
        db.session.commit()
        return ApiResponse.success(schema.dump(experiment), code=201)

    except Exception as e:
        db.session.rollback()
        return ApiResponse.error(str(e), code=400, exc_info=True)


@experiments_bp.route('/api/experiments/<string:experiment_id>', methods=['GET'])
def get_experiment(experiment_id: str) -> Response:
    experiment: Experiment = Experiment.query.get_or_404(experiment_id)
    schema = ExperimentSchema()
    return ApiResponse.success(schema.dump(experiment))


@experiments_bp.route('/api/experiments/<string:experiment_id>', methods=['DELETE'])
def delete_experiment(experiment_id: str) -> Response:
    experiment: Experiment = Experiment.query.get_or_404(experiment_id)
    experiment.delete_resources()
    db.session.delete(experiment)
    db.session.commit()
    return ApiResponse.success(code=204)
