from enum import Enum


class AnalysisType(str, Enum):
    """mwf analysis task names that can be passed to the -i (include) flag."""

    APL = "apl"
    CLUSTERS = "clusters"
    DENSITY = "density"
    DIST = "dist"
    ENERGIES = "energies"
    HBONDS = "hbonds"
    INTER = "inter"
    LINTER = "linter"
    LORDER = "lorder"
    PAIRWISE = "pairwise"
    PCA = "pca"
    PERRES = "perres"
    POCKETS = "pockets"
    RGYR = "rgyr"
    RMSDS = "rmsds"
    RMSF = "rmsf"
    SAS = "sas"
    THICKNESS = "thickness"
    TMSCORE = "tmscore"

    def __str__(self) -> str:
        return self.value
