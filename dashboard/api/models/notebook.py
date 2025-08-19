import logging
from sqlalchemy.orm import Mapped, mapped_column, relationship
from flask_sqlalchemy import SQLAlchemy
from typing import TYPE_CHECKING

from config import NAMESPACE, PREFIX, NOTEBOOK_IMAGE, PVC_NAME
from clients import caddy, k8s

if TYPE_CHECKING:
    from enums import PodStatus
    from .experiment import Experiment


db = SQLAlchemy()
logger = logging.getLogger(__name__)


class Notebook(db.Model):
    __tablename__ = 'notebooks'
    
    # ID of the notebook inside the database
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    # ID of the experiment this notebook belongs to
    experiment_id: Mapped[str] = mapped_column(db.String(5), db.ForeignKey('experiments.id'))
    # token for accessing jupyter notebook
    token: Mapped[str] = mapped_column(db.String(36), nullable=False)

    # back-reference to the parent experiment
    experiment: Mapped['Experiment'] = relationship('Experiment', back_populates='notebooks')

    @property
    def path(self) -> str:
        '''Path to access the notebook via Caddy.'''
        return f'{PREFIX}/notebook/{self.experiment_id}/?token={self.token}'

    @property
    def status(self) -> PodStatus:
        '''Get the status of the notebook pod.'''
        pod_name = f'notebook-{self.experiment_id}'
        return k8s.get_pod_status(NAMESPACE, pod_name)

    def start(self) -> None:
        '''Start the notebook pod and service, and create a route in Caddy.'''
        pod_name = f'notebook-{self.experiment_id}'
        svc_name = f'svc-{self.experiment_id}'

        k8s.create_notebook_pod(
            NOTEBOOK_IMAGE,
            NAMESPACE,
            PVC_NAME,
            pod_name,
            self.experiment_id,
            f'{PREFIX}/notebook/{self.experiment_id}',
            self.token
        )

        try:
           k8s. create_service(NAMESPACE, svc_name, pod_name)
        except Exception:
            k8s.delete_pod(NAMESPACE, pod_name)
            raise

        route_id = caddy.add_proxy_route(
            path=f'{PREFIX}/notebook/{self.experiment_id}',
            upstream=f'{svc_name}.{NAMESPACE}.svc.cluster.local:80',
            route_id=f'route-{self.experiment_id}-notebook',
        )
        
        if route_id is None:
            k8s.delete_pod(NAMESPACE, pod_name)
            k8s.delete_service(NAMESPACE, svc_name)
            raise Exception('Failed to create proxy connection to notebook.')

    def stop(self) -> None:
        '''Stop the notebook pod and service, and remove the route from Caddy.'''
        pod_name = f'notebook-{self.experiment_id}'
        svc_name = f'svc-{self.experiment_id}'
        route_id = f'route-{self.experiment_id}-notebook'

        try:
            k8s.delete_pod(NAMESPACE, pod_name)
        except Exception:
            logger.error(f'Failed to delete notebook pod.', exc_info=True)

        try:
            k8s.delete_service(NAMESPACE, svc_name)
        except Exception:
            logger.error(f'Failed to delete notebook service.', exc_info=True)

        if not caddy.remove_route(route_id):
            logger.error('Failed to remove route from Caddy.')
