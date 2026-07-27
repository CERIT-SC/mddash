"""GMX trial configuration with hardware constraint validation."""

from dataclasses import dataclass
from enum import Enum
from itertools import product
from typing import Any

from api.config import MAX_CPU, MAX_GPU, NB_OPTIONS, NP_OPTIONS, NTOMP_OPTIONS, PME_OPTIONS


class NBMode(str, Enum):
    """Non-bonded calculation target for gmx mdrun."""

    AUTO = "auto"
    CPU = "cpu"
    GPU = "gpu"


class PMEMode(str, Enum):
    """PME calculation target for gmx mdrun."""

    AUTO = "auto"
    CPU = "cpu"
    GPU = "gpu"


@dataclass
class GmxTrialConfig:
    """Configuration for a single GMX mdrun trial."""

    np: int = 1
    ntomp: int = 0
    nb: NBMode = NBMode.AUTO
    pme: PMEMode = PMEMode.AUTO

    @property
    def is_valid(self) -> bool:
        """Check hardware constraints."""
        if self.num_cpus > MAX_CPU or self.num_gpus > MAX_GPU:
            return False
        if self.pme == PMEMode.GPU and self.np > 1:
            return False
        return not (self.nb == NBMode.CPU and self.pme == PMEMode.GPU)

    @property
    def num_cpus(self) -> int:
        """Total CPU slots required (np * ntomp, treating ntomp=0 as 1)."""
        return self.np * (self.ntomp if self.ntomp > 0 else 1)

    @property
    def num_gpus(self) -> int:
        """Number of GPU slots required (1 if nb or pme uses GPU, else 0)."""
        return int(self.nb == NBMode.GPU or self.pme == PMEMode.GPU)

    @classmethod
    def generate_all_configs(cls) -> list["GmxTrialConfig"]:
        """Generate all valid configurations for grid search."""
        configs = []
        for ntomp, np, nb, pme in product(NTOMP_OPTIONS, NP_OPTIONS, NB_OPTIONS, PME_OPTIONS):
            cfg = cls(ntomp=ntomp, np=np, nb=NBMode(nb), pme=PMEMode(pme))
            if cfg.is_valid:
                configs.append(cfg)
        return configs

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GmxTrialConfig":
        """Reconstruct a GmxTrialConfig from a plain dict (inverse of to_dict)."""
        return cls(
            ntomp=data["ntomp"],
            np=data["np"],
            nb=NBMode(data["nb"]),
            pme=PMEMode(data["pme"]),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for JSON storage."""
        return {"ntomp": self.ntomp, "np": self.np, "nb": self.nb.value, "pme": self.pme.value}
