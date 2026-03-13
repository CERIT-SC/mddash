from dataclasses import dataclass, field
from typing import TypeVar

from enums import PodStatus

ModelType = TypeVar("ModelType")


@dataclass
class DemoState:
    initialized: bool = False
    notebook_status: dict[str, PodStatus] = field(default_factory=dict)
    mdrun_jobs: dict[str, dict[str, object]] = field(default_factory=dict)
    tuner_jobs: dict[str, dict[str, object]] = field(default_factory=dict)
    analysis_jobs: dict[str, dict[str, object]] = field(default_factory=dict)
    mdrepo_records: dict[str, bool] = field(default_factory=dict)
    mdrepo_counter: int = 1


demo_state = DemoState()


def build_model(model_cls: type[ModelType], **attrs: object) -> ModelType:
    model = model_cls()  # type: ignore[call-arg]
    for attr, value in attrs.items():
        setattr(model, attr, value)
    return model
