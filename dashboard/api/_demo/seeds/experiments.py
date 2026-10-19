"""Seeded experiments with their notebooks (pod state lives in the fake Kubernetes)."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.enums import DeviceType, Engine, PodStatus, SourceType
from modules.models import Experiment, Notebook

from ..files import MDPOSIT_DEMO_PROJECT_URL
from ..state import E2E, build_model, demo_state

NOTEBOOKS_REPO = "https://github.com/CERIT-SC/mddash-notebooks.git"

MEMBRANE = "aaaaa"
ENZYME = "bbbbb"
PUBLISHED = "ccccc"
AMBER_FOLDING = "ddddd"
AMBER_DNA = "eeeee"
MDPOSIT_IMPORT = "fffff"
ARCHIVED = "ggggg"
E2E_AMBER_TETRA = "iiiii"


@dataclass(frozen=True)
class FinishedGmxStudy:
    """A FINISHED GMX experiment with manifest, files, and log — the shape E2E journeys own."""

    experiment_id: str
    name: str
    sim_name: str
    source_type: SourceType
    nsteps: int
    performance: float
    ranks: int
    threads: int
    nb: DeviceType
    age_days: int
    source_ref: str | None = None

    @property
    def tpr_name(self) -> str:
        """Run input of the study's single simulation."""
        return f"{self.sim_name}.tpr"


# E2E-only: the publish journey (hhhhh) and the MDPosit-handoff journey (jjjjj).
E2E_GMX_STUDIES = (
    FinishedGmxStudy(
        "hhhhh",
        "Alanine dipeptide free energy landscape",
        "alanine_dipeptide",
        SourceType.PDB,
        nsteps=100000,
        performance=87.4,
        ranks=2,
        threads=2,
        nb=DeviceType.CPU,
        age_days=6,
        source_ref="2JOF",
    ),
    FinishedGmxStudy(
        "jjjjj",
        "KIX domain folding benchmark",
        "kix_domain",
        SourceType.FILE,
        nsteps=250000,
        performance=112.8,
        ranks=4,
        threads=2,
        nb=DeviceType.GPU,
        age_days=4,
    ),
)


def _notebook(experiment: Experiment, token: str, status: PodStatus = PodStatus.DOWN) -> Notebook:
    demo_state.notebook_status[experiment.id] = status
    return build_model(Notebook, experiment_id=experiment.id, token=f"demo-token-{token}")


def seed_experiments(now: datetime) -> tuple[dict[str, Experiment], list[Notebook]]:
    """Build every seeded experiment (keyed by id) and its notebook."""
    membrane = build_model(
        Experiment,
        id=MEMBRANE,
        name="GPCR membrane protein in lipid bilayer",
        module_name="Membrane protein (BioBB)",
        module_category="membrane-protein",
        source_type=SourceType.FILE,
        source_files=["gpcr_membrane.tpr", "structure.pdb"],
        notebooks_repo=NOTEBOOKS_REPO,
        created_at=now - timedelta(days=3),
        updated_at=now - timedelta(days=2),
    )
    enzyme = build_model(
        Experiment,
        id=ENZYME,
        name="HIV protease inhibitor binding study",
        module_name="Protein",
        module_category="protein",
        source_type=SourceType.REPO,
        source_ref="https://zenodo.org/records/7261108",
        notebooks_repo=NOTEBOOKS_REPO,
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=1),
    )
    published = build_model(
        Experiment,
        id=PUBLISHED,
        name="Hen egg-white lysozyme folding stability",
        module_name="Protein",
        module_category="protein",
        source_type=SourceType.PDB,
        source_ref="1LYZ",
        notebooks_repo=NOTEBOOKS_REPO,
        mdrepo_id="8gahj-dh519",
        mdrepo_published=True,
        created_at=now - timedelta(days=10),
        updated_at=now - timedelta(days=8),
    )
    demo_state.mdrepo_records["8gahj-dh519"] = True
    amber_folding = build_model(
        Experiment,
        id=AMBER_FOLDING,
        name="AMBER villin headpiece folding",
        module_name="Protein (BioBB)",
        module_category="protein",
        source_type=SourceType.FILE,
        source_files=["villin.prmtop", "villin.inpcrd", "production.mdin"],
        notebooks_repo=NOTEBOOKS_REPO,
        engine=Engine.AMBER,
        created_at=now - timedelta(hours=6),
        updated_at=now - timedelta(hours=2),
    )
    amber_dna = build_model(
        Experiment,
        id=AMBER_DNA,
        name="AMBER DNA duplex stability",
        module_name="Nucleic Acid",
        module_category="nucleic-acids",
        source_type=SourceType.REPO,
        source_ref="https://doi.org/10.5281/zenodo.10440684",
        notebooks_repo=NOTEBOOKS_REPO,
        engine=Engine.AMBER,
        created_at=now - timedelta(days=7),
        updated_at=now - timedelta(days=5),
    )
    mdposit_import = build_model(
        Experiment,
        id=MDPOSIT_IMPORT,
        name="MDPosit imported lysozyme trajectory",
        source_type=SourceType.REPO,
        source_ref=MDPOSIT_DEMO_PROJECT_URL,
        notebooks_repo=NOTEBOOKS_REPO,
        created_at=now - timedelta(days=1, hours=6),
        updated_at=now - timedelta(days=1),
    )
    # Archived study: snapshot columns stand in for the deleted local dir (no files seeded).
    archived = build_model(
        Experiment,
        id=ARCHIVED,
        name="Finished lipid raft study (archived)",
        module_name="Membrane protein (BioBB)",
        module_category="membrane-protein",
        source_type=SourceType.FILE,
        source_files=["raft.tpr", "raft.pdb"],
        notebooks_repo="https://github.com/sb-ncbr/mddash-notebooks.git",
        created_at=now - timedelta(days=30),
        updated_at=now - timedelta(days=12),
        archived_at=now - timedelta(days=12),
        archived_size_bytes=8 * 1024**3,
        archived_step=4,
        archived_status="published",
        mdrepo_id="demo-archived-record",
        mdrepo_published=True,
    )
    # The mock record lookup must not report deleted, or the MDRepo sync clears the linkage.
    demo_state.mdrepo_records["demo-archived-record"] = True

    notebooks = [
        _notebook(membrane, "membrane"),
        # Fresh notebook so the controller bar shows a short ticking uptime on the experiment page.
        _notebook(enzyme, "enzyme", PodStatus.RUNNING),
        _notebook(published, "published"),
        _notebook(amber_folding, "amber", PodStatus.RUNNING),
        _notebook(amber_dna, "dna"),
        _notebook(mdposit_import, "mdposit"),
        _notebook(archived, "archived"),
    ]
    demo_state.notebook_started_at[enzyme.id] = datetime.now(timezone.utc) - timedelta(seconds=15)
    demo_state.notebook_started_at[amber_folding.id] = datetime.now(timezone.utc) - timedelta(minutes=40)

    experiments = [membrane, enzyme, published, amber_folding, amber_dna, mdposit_import, archived]
    if E2E:
        for study in E2E_GMX_STUDIES:
            experiment = build_model(
                Experiment,
                id=study.experiment_id,
                name=study.name,
                module_name="Protein",
                module_category="protein",
                source_type=study.source_type,
                source_ref=study.source_ref,
                source_files=[study.tpr_name, "structure.pdb"] if study.source_type is SourceType.FILE else None,
                notebooks_repo=NOTEBOOKS_REPO,
                created_at=now - timedelta(days=study.age_days),
                updated_at=now - timedelta(days=study.age_days - 1),
            )
            experiments.append(experiment)
            notebooks.append(_notebook(experiment, study.sim_name))
        # AMBER study with a valid simulation and no jobs yet: the manual AMBER run
        # journey (Tune → Manual configuration → Run Simulation) owns it.
        amber_tetra = build_model(
            Experiment,
            id=E2E_AMBER_TETRA,
            name="AMBER tetrapeptide conformational sampling",
            module_name="Protein (BioBB)",
            module_category="protein",
            source_type=SourceType.FILE,
            source_files=["tetrapeptide.prmtop", "tetrapeptide.inpcrd", "production.mdin"],
            notebooks_repo=NOTEBOOKS_REPO,
            engine=Engine.AMBER,
            created_at=now - timedelta(days=1),
            updated_at=now - timedelta(hours=3),
        )
        experiments.append(amber_tetra)
        notebooks.append(_notebook(amber_tetra, "tetra"))

    return {experiment.id: experiment for experiment in experiments}, notebooks
