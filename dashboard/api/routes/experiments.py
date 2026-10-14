import asyncio
from http import HTTPStatus
from typing import Annotated, Literal

from config import API_PREFIX, DEFAULT_NOTEBOOKS_REPO
from dependencies import ExperimentDep, SessionDep, dump, dump_many, list_experiments, mdrepo_token
from enums import Engine
from errors import BadRequest, Conflict, Unauthorized
from fastapi import APIRouter, File, Form, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from models import Experiment
from notebook_modules import load_catalog
from pydantic import TypeAdapter
from schemas.experiment import (
    ArchiveAttempt,
    ArchiveStatus,
    MDPositPublication,
    MDRepoPublication,
    PublishRequest,
    PublishStatus,
    UpdateExperiment,
)
from schemas.experiment import Experiment as ExperimentOut
from token_manager import MDRepoTokenManager
from validators import validate_git_url

from routes._responses import problems

router = APIRouter(prefix=f"{API_PREFIX}/experiments", tags=["Experiments"])

_publish_status = TypeAdapter(PublishStatus)
_archive_status = TypeAdapter(ArchiveStatus)


@router.get(
    "",
    summary="List experiments",
    operation_id="listExperiments",
    response_description="Experiments",
    responses=problems(),
)
async def list_all(request: Request, session: SessionDep) -> list[ExperimentOut]:
    """
    List all experiments.

    The dashboard polls this every 5s while any job is live; remote state of
    all experiments is fetched concurrently.
    """
    experiments = await list_experiments(session)
    token = await mdrepo_token(request, experiments)
    await asyncio.gather(*(experiment.refresh(token) for experiment in experiments))
    return await dump_many(session, ExperimentOut, experiments)


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    summary="Create an experiment",
    operation_id="createExperiment",
    response_description="Created experiment",
    responses=problems(400),
)
async def create(
    request: Request,
    session: SessionDep,
    experiment_name: Annotated[str, Form(alias="experiment-name", min_length=1)],
    source_type: Annotated[Literal["pdb", "repo", "file"], Form(alias="type")],
    simulation_files: Annotated[list[UploadFile], File(alias="simulation-files", default_factory=list)],
    pdb: Annotated[str | None, Form()] = None,
    repo_url: Annotated[str | None, Form(alias="repo-url")] = None,
    notebooks_repo: Annotated[str | None, Form(alias="notebooks-repo")] = None,
    access_token: Annotated[str | None, Form(alias="access-token")] = None,
    notebook_module_id: Annotated[str | None, Form(alias="notebook-module")] = None,
    engine: Annotated[Engine, Form()] = Engine.GMX,
) -> ExperimentOut:
    """
    Create a new experiment from PDB, repository URL, or uploaded files.

    Raises:
        BadRequest: If the notebook module, repository, or source data is invalid.
    """
    repo = notebooks_repo if notebooks_repo is not None else DEFAULT_NOTEBOOKS_REPO
    module = None
    if notebook_module_id:
        # Curated mode: server resolves module and repository; no client URL trusted.
        module = load_catalog().get_module_for_engine(notebook_module_id, engine.value)
        if module is None:
            raise BadRequest(f"Unknown or incompatible notebook module: {notebook_module_id}")
        repo = module.repository or DEFAULT_NOTEBOOKS_REPO
        if module.repository is not None:
            # Guard against unsafe schemes even on trusted catalog URLs.
            validate_git_url(module.repository)
        # Never forward a client token to a curated (server-trusted) repository.
        access_token = None
    else:
        validate_git_url(repo)

    match source_type:
        case "pdb" if pdb:
            experiment = await Experiment.from_pdb(
                session, experiment_name, pdb, repo, access_token, engine=engine, notebook_module=module
            )
        case "repo" if repo_url:
            experiment = await Experiment.from_repo(
                session, experiment_name, repo_url, repo, access_token, engine=engine, notebook_module=module
            )
        case "file" if simulation_files:
            experiment = await Experiment.from_files(
                session, experiment_name, simulation_files, repo, access_token, engine=engine, notebook_module=module
            )
        case _:
            raise BadRequest("Invalid experiment type or missing data.")

    await experiment.refresh(await mdrepo_token(request, [experiment]))
    return await dump(session, ExperimentOut, experiment)


@router.get(
    "/{experiment_id}",
    summary="Get an experiment",
    operation_id="getExperiment",
    response_description="Experiment",
    responses=problems(404),
)
async def get(request: Request, session: SessionDep, experiment: ExperimentDep) -> ExperimentOut:
    """Get an experiment by ID."""
    await experiment.refresh(await mdrepo_token(request, [experiment]))
    return await dump(session, ExperimentOut, experiment)


@router.patch(
    "/{experiment_id}",
    summary="Update an experiment",
    operation_id="updateExperiment",
    response_description="Updated experiment",
    responses=problems(400, 404),
)
async def update(
    request: Request, session: SessionDep, experiment: ExperimentDep, body: UpdateExperiment
) -> ExperimentOut:
    """Update experiment properties (currently only the name)."""
    experiment.name = body.name
    await session.commit()
    await experiment.refresh(await mdrepo_token(request, [experiment]))
    return await dump(session, ExperimentOut, experiment)


@router.delete(
    "/{experiment_id}",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Delete an experiment",
    operation_id="deleteExperiment",
    response_description="Operation completed successfully",
    responses=problems(404),
)
async def delete(session: SessionDep, experiment: ExperimentDep) -> None:
    """Delete an experiment and all associated resources."""
    await experiment.delete()
    await session.delete(experiment)
    await session.commit()


@router.post(
    "/{experiment_id}/publish",
    summary="Publish an experiment",
    operation_id="publishExperiment",
    response_model=None,
    responses={
        201: {"model": MDPositPublication, "description": "MDPosit publication package"},
        202: {"model": MDRepoPublication, "description": "MDRepo publication accepted"},
        **problems(400, 401, 404),
    },
)
async def publish(
    request: Request, session: SessionDep, experiment: ExperimentDep, body: PublishRequest | None = None
) -> JSONResponse:
    """
    Publish experiment to the requested target.

    Raises:
        BadRequest: If MDPosit publishing lacks a simulation_path.
        Unauthorized: If the user is not authenticated with MDRepo for Invenio publishing.
        Conflict: If there is nothing publishable yet.
    """
    body = body or PublishRequest()

    if body.target == "invenio":
        credentials = await MDRepoTokenManager(request.session).get_credentials()
        if credentials is None:
            raise Unauthorized("Not authenticated with MDRepo. Please authenticate first.")

        # Same gate as the wizard's can_publish unlock. A stale URL/bookmark
        # must not create an MDRepo draft for an experiment with nothing publishable.
        await experiment.refresh_jobs()
        if not experiment.can_publish:
            raise Conflict("Nothing to publish yet: no finished or stopped run and no existing publication.")

        # TODO: Add endpoint to fetch available communities from MDRepo and allow user to select from a dropdown in the publish UI.
        #       Pass the selected community to this endpoint and use it when publishing the experiment instead of hardcoding 'ceitec'.
        result = await experiment.publish(session, target="invenio", community="ceitec", credentials=credentials)
        await session.commit()
        return JSONResponse(result, status_code=HTTPStatus.ACCEPTED)

    if not body.simulation_path:
        raise BadRequest("MDPosit publish requires simulation_path.")
    result = await experiment.publish(session, target="mdposit", simulation_path=body.simulation_path)
    await session.commit()
    return JSONResponse(result, status_code=HTTPStatus.CREATED)


@router.get(
    "/{experiment_id}/publish/status",
    summary="Get MDRepo upload status",
    operation_id="getPublishStatus",
    response_description="Publication status",
    responses=problems(404),
)
async def publish_status(experiment: ExperimentDep) -> PublishStatus:
    """Durable MDRepo upload status: the PVC state document merged with live Kubernetes Job state."""
    return _publish_status.validate_python(await experiment.get_publish_status())


@router.post(
    "/{experiment_id}/archive",
    status_code=HTTPStatus.ACCEPTED,
    summary="Archive an experiment",
    description="Mirror the experiment to S3 at _archives/<id>/ and free the local PVC (verified before deletion).",
    operation_id="archiveExperiment",
    response_description="Archive accepted",
    responses=problems(400, 404, 409),
)
async def archive(session: SessionDep, experiment: ExperimentDep) -> ArchiveAttempt:
    """Archive an experiment."""
    attempt_id = await experiment.archive(session)
    return {"attempt_id": attempt_id}


@router.post(
    "/{experiment_id}/restore",
    status_code=HTTPStatus.ACCEPTED,
    summary="Restore an archived experiment",
    description="Copy the S3 archive back onto the local PVC and unfreeze the experiment.",
    operation_id="restoreExperiment",
    response_description="Restore accepted",
    responses=problems(400, 404, 409),
)
async def restore(session: SessionDep, experiment: ExperimentDep) -> ArchiveAttempt:
    """Restore an archived experiment."""
    attempt_id = await experiment.restore()
    await session.commit()
    return {"attempt_id": attempt_id}


@router.get(
    "/{experiment_id}/archive/status",
    summary="Get archive/restore status",
    operation_id="getArchiveStatus",
    response_description="Archive status",
    responses=problems(404),
)
async def archive_status(session: SessionDep, experiment: ExperimentDep) -> ArchiveStatus:
    """Archive/restore status (status doc reconciled with live Jobs)."""
    status = await experiment.get_archive_status()
    await session.commit()
    return _archive_status.validate_python(status)
