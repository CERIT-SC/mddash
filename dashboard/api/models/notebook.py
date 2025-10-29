import logging
from uuid import uuid4
from flask import abort
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING
from kubernetes.client.rest import ApiException

from config import NAMESPACE, PREFIX
from clients import caddy, k8s
from extensions import db
from enums import PodStatus

if TYPE_CHECKING:
    from .experiment import Experiment


logger = logging.getLogger(__name__)


class Notebook(db.Model):  # type: ignore
    __tablename__ = 'notebooks'
    
    # ID of the notebook inside the database
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    # ID of the experiment this notebook belongs to
    experiment_id: Mapped[str] = mapped_column(db.String(5), db.ForeignKey('experiments.id'))
    # token for accessing jupyter notebook
    token: Mapped[str] = mapped_column(db.String(36), nullable=False, default=lambda: str(uuid4()))

    # back-reference to the parent experiment
    experiment: Mapped['Experiment'] = relationship('Experiment', back_populates='notebook')

    @property
    def path(self) -> str:
        '''Path to access the notebook via Caddy.'''
        return f'{PREFIX}/notebook/{self.experiment_id}/?token={self.token}'

    @property
    def status(self) -> PodStatus:
        '''Get the status of the notebook pod.'''
        pod_name = f'notebook-{self.experiment_id}'
        return k8s.get_pod_status(pod_name)

    def start(self) -> None:
        '''
        Start the notebook pod and service, and create a route in Caddy.

        :raises HTTPException: If the pod or service creation fails.
        :raises Exception: If the route creation fails.
        '''
        pod_name = f'notebook-{self.experiment_id}'
        svc_name = f'svc-{self.experiment_id}'

        try:
            k8s.create_notebook_pod(
                pod_name,
                self.experiment_id,
                f'{PREFIX}/notebook/{self.experiment_id}',
                self.token
            )
        except ApiException as e:
            if e.status == 403:
                abort(403, description='Resource quota exceeded. Please stop other notebooks.')
            elif e.status == 409:
                abort(409, description=f'Notebook pod already exists.')
            else:
                logger.error(f'Failed to create notebook pod.', exc_info=True)
                abort(500, description=f'Failed to create notebook pod: {e.reason}')

        try:
           k8s.create_service(svc_name, pod_name)
        except Exception:
            k8s.delete_pod(pod_name)
            raise

        route_id = caddy.add_proxy_route(
            path=f'{PREFIX}/notebook/{self.experiment_id}',
            upstream=f'{svc_name}.{NAMESPACE}.svc.cluster.local:80',
            route_id=f'route-{self.experiment_id}-notebook',
        )

        if route_id is None:
            k8s.delete_pod(pod_name)
            k8s.delete_service(svc_name)
            abort(500, description='Failed to create proxy connection to notebook.')

    def stop(self) -> None:
        '''
        Stop the notebook pod and service, and remove the route from Caddy.
        '''
        if self.status != PodStatus.RUNNING and self.status != PodStatus.PENDING:
            logger.warning(f'Notebook {self.experiment_id} is not running. No action taken.')
            return

        pod_name = f'notebook-{self.experiment_id}'
        svc_name = f'svc-{self.experiment_id}'
        route_id = f'route-{self.experiment_id}-notebook'

        try:
            k8s.delete_pod(pod_name)
        except Exception:
            logger.error(f'Failed to delete notebook pod.', exc_info=True)

        try:
            k8s.delete_service(svc_name)
        except Exception:
            logger.error(f'Failed to delete notebook service.', exc_info=True)

        if not caddy.remove_route(route_id):
            logger.error('Failed to remove route from Caddy.')
