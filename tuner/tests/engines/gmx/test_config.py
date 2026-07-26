from api.engines.gmx.config import GmxTrialConfig, NBMode, PMEMode


def test_nb_mode_values() -> None:
    assert NBMode.CPU == "cpu"
    assert NBMode.GPU == "gpu"
    assert NBMode.AUTO == "auto"


def test_pme_mode_values() -> None:
    assert PMEMode.CPU == "cpu"
    assert PMEMode.GPU == "gpu"


def test_valid_config_cpu_only() -> None:
    cfg = GmxTrialConfig(np=4, ntomp=2, nb=NBMode.CPU, pme=PMEMode.CPU)
    assert cfg.is_valid
    assert cfg.num_cpus == 8
    assert cfg.num_gpus == 0


def test_valid_config_gpu() -> None:
    cfg = GmxTrialConfig(np=1, ntomp=4, nb=NBMode.GPU, pme=PMEMode.GPU)
    assert cfg.is_valid
    assert cfg.num_gpus == 1


def test_invalid_pme_gpu_multi_rank() -> None:
    cfg = GmxTrialConfig(np=2, ntomp=2, nb=NBMode.GPU, pme=PMEMode.GPU)
    assert not cfg.is_valid


def test_invalid_nb_cpu_pme_gpu() -> None:
    cfg = GmxTrialConfig(np=1, ntomp=1, nb=NBMode.CPU, pme=PMEMode.GPU)
    assert not cfg.is_valid


def test_generate_all_configs_are_valid() -> None:
    configs = GmxTrialConfig.generate_all_configs()
    assert len(configs) > 0
    assert all(c.is_valid for c in configs)


def test_round_trip_dict() -> None:
    cfg = GmxTrialConfig(np=2, ntomp=4, nb=NBMode.GPU, pme=PMEMode.CPU)
    restored = GmxTrialConfig.from_dict(cfg.to_dict())
    assert restored == cfg


def test_to_dict_uses_enum_values() -> None:
    cfg = GmxTrialConfig(np=1, ntomp=1, nb=NBMode.CPU, pme=PMEMode.CPU)
    d = cfg.to_dict()
    assert d["nb"] == "cpu"
    assert d["pme"] == "cpu"
