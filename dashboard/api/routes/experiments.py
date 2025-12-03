from http import HTTPStatus
from flask import Blueprint, Response, request

from config import API_PREFIX
from api_response import ApiResponse
from models import Experiment
from schemas import ExperimentSchema
from extensions import db
from decorators import handle_exceptions
from routes.mdrepo import get_mdrepo_token


experiments_bp = Blueprint(
    'experiments',
    __name__,
    url_prefix=f'{API_PREFIX}/experiments'
)


@experiments_bp.route('', methods=['GET'])
@handle_exceptions()
def list_experiments() -> Response:
    experiments: list[Experiment] = Experiment.query.all()
    schema = ExperimentSchema(many=True)
    return ApiResponse.success(schema.dump(experiments))


@experiments_bp.route('', methods=['POST'])
@handle_exceptions(rollback=True)
def create_experiment() -> Response:
    schema = ExperimentSchema()
    form = request.form

    name = form['experiment-name']
    pdb_id = form.get('pdb-id')
    repo_url = form.get('repo-url')
    simulation_file = request.files.get('simulation-file')

    match form['type']:
        case 'pdb' if pdb_id:
            experiment = Experiment.from_pdb(name, pdb_id)
        case 'repo' if repo_url:
            experiment = Experiment.from_repo(name, repo_url)
        case 'file' if simulation_file:
            experiment = Experiment.from_tpr(name, simulation_file)
        case _:
            return ApiResponse.error('Invalid experiment type or missing data.', HTTPStatus.BAD_REQUEST)

    db.session.add(experiment)
    db.session.commit()
    return ApiResponse.success(schema.dump(experiment), HTTPStatus.CREATED)


@experiments_bp.route('/<experiment_id>', methods=['GET'])
@handle_exceptions()
def get_experiment(experiment_id: str) -> Response:
    experiment: Experiment = Experiment.query.get_or_404(experiment_id, description=f'Experiment {experiment_id} not found')
    schema = ExperimentSchema()
    return ApiResponse.success(schema.dump(experiment))


@experiments_bp.route('/<experiment_id>', methods=['DELETE'])
@handle_exceptions(rollback=True)
def delete_experiment(experiment_id: str) -> Response:
    experiment: Experiment = Experiment.query.get_or_404(experiment_id, description=f'Experiment {experiment_id} not found')
    experiment.delete()
    db.session.delete(experiment)
    db.session.commit()
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)


@experiments_bp.route('/<experiment_id>', methods=['PATCH'])
@handle_exceptions(rollback=True)
def edit_experiment(experiment_id: str) -> Response:
    experiment: Experiment = Experiment.query.get_or_404(experiment_id, description=f'Experiment {experiment_id} not found')
    data = request.get_json()
    if not data:
        return ApiResponse.error('No data provided.', HTTPStatus.BAD_REQUEST)

    updated = False
    # Currently only name can be edited
    if 'name' in data:
        experiment.name = data['name']
        updated = True

    if not updated:
        return ApiResponse.error('No valid fields to update.', HTTPStatus.BAD_REQUEST)

    db.session.commit()
    schema = ExperimentSchema()
    return ApiResponse.success(schema.dump(experiment))


@experiments_bp.route('/<experiment_id>/publish', methods=['POST'])
@handle_exceptions(rollback=True)
def publish_experiment(experiment_id: str) -> Response:
    """Publish experiment to MDRepo. Requires MDRepo OAuth authentication."""
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, 
        description=f'Experiment {experiment_id} not found'
    )

    token = get_mdrepo_token()
    if not token:
        return ApiResponse.error(
            'Not authenticated with MDRepo. Please authenticate first.',
            HTTPStatus.UNAUTHORIZED
        )

    # TODO: Allow user to select community
    mdrepo_experiment = experiment.publish(
        token=token,
        community='ceitec'
    )

    return ApiResponse.success(mdrepo_experiment, HTTPStatus.CREATED)


@experiments_bp.route('/<experiment_id>/step', methods=['GET'])
@handle_exceptions()
def get_experiment_step(experiment_id: str) -> Response:
    experiment: Experiment = Experiment.query.get_or_404(experiment_id, description=f'Experiment {experiment_id} not found')
    return ApiResponse.success(experiment.step)
