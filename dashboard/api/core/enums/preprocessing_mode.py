from enum import Enum


class PreprocessingMode(str, Enum):
    """Trajectory preprocessing modes supported by the analysis launcher."""

    AS_IS = "as_is"
    IMAGE = "image"
    IMAGE_FIT = "image_fit"

    def __str__(self) -> str:
        return self.value
