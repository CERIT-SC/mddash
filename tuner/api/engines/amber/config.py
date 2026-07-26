"""AMBER trial configuration."""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from api.config import AMBER_NP_OPTIONS, AMBER_NTOMP_OPTIONS, MAX_CPU, MAX_GPU


class AmberBinary(str, Enum):
    """AMBER pmemd binary variant."""

    PMEMD_CUDA = "pmemd.cuda"
    PMEMD_MPI = "pmemd.MPI"


class EwaldPreset(str, Enum):
    """Ewald summation performance preset applied to the &ewald mdin namelist."""

    DEFAULT = "default"  # netfrc=1, skin_permit=1.0
    OPTIMIZED = "optimized"  # netfrc=0, skin_permit=0.75 — ~15-20% GPU speedup


@dataclass
class AmberTrialConfig:
    """Configuration for a single AMBER pmemd trial."""

    binary: AmberBinary
    np: int
    ewald: EwaldPreset
    ntomp: int = 1

    @property
    def num_cpus(self) -> int:
        """Number of CPU slots required (1 for CUDA, np*ntomp for MPI)."""
        return 1 if self.binary == AmberBinary.PMEMD_CUDA else self.np * self.ntomp

    @property
    def num_gpus(self) -> int:
        """Number of GPU slots required (1 for CUDA, 0 for MPI)."""
        return 1 if self.binary == AmberBinary.PMEMD_CUDA else 0

    @classmethod
    def generate_all_configs(cls) -> list["AmberTrialConfig"]:
        """Generate all valid configs. GPU configs first (domain prior)."""
        configs = []

        # GPU configs (pmemd.cuda, single GPU, no OpenMP)
        if MAX_GPU >= 1:
            for ewald in EwaldPreset:
                configs.append(cls(binary=AmberBinary.PMEMD_CUDA, np=1, ntomp=1, ewald=ewald))

        # CPU configs: descending np to establish high baseline early
        for np in sorted(AMBER_NP_OPTIONS, reverse=True):
            for ntomp in AMBER_NTOMP_OPTIONS:
                if np * ntomp <= MAX_CPU:
                    for ewald in EwaldPreset:
                        configs.append(cls(binary=AmberBinary.PMEMD_MPI, np=np, ntomp=ntomp, ewald=ewald))

        return configs

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AmberTrialConfig":
        """Reconstruct an AmberTrialConfig from a plain dict (inverse of to_dict)."""
        return cls(
            binary=AmberBinary(data["binary"]),
            np=data["np"],
            ewald=EwaldPreset(data["ewald"]),
            ntomp=data.get("ntomp", 1),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for JSON storage."""
        return {
            "binary": self.binary.value,
            "np": self.np,
            "ewald": self.ewald.value,
            "ntomp": self.ntomp,
        }
