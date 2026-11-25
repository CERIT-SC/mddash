from enum import Enum


class PopulationPhase(str, Enum):
    """Worker phase carried in the population receipt and linked operation (name == wire value)."""

    starting = "starting"
    crawling = "crawling"
    downloading = "downloading"
    finalizing = "finalizing"
    cancelling = "cancelling"

    def __str__(self) -> str:
        return self.value
