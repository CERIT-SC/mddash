import json
from dataclasses import asdict

from experiment import Experiment


class Experiments:
    def __init__(self, experiments: dict[str, Experiment] = None):
        self.experiments = experiments or {}

    @classmethod
    def load(cls, filepath: str) -> "Experiments":
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}

        experiments_dict = {id: Experiment(**exp) for id, exp in data.items()}
        return cls(experiments_dict)

    def get_all(self) -> list[dict]:
        return [asdict(exp) for exp in self.experiments.values()]

    def save(self, filepath: str) -> None:
        data = {id: asdict(exp) for id, exp in self.experiments.items()}

        with open(filepath, "w") as f:
            # TODO: in production, use json.dump(data, f) (without indent to save space)
            json.dump(data, f, indent=4)

    def add(self, experiment: Experiment) -> None:
        self.experiments[experiment.id] = experiment

    def remove(self, experiment_id: str) -> None:
        if experiment_id not in self.experiments:
            raise ValueError(f"Experiment with id '{experiment_id}' not found")

        self.experiments[experiment_id].delete() # Clean up experiment directory
        del self.experiments[experiment_id]

    def get(self, experiment_id: str) -> Experiment:
        if experiment_id not in self.experiments:
            raise ValueError(f"Experiment with id '{experiment_id}' not found")

        return self.experiments[experiment_id]


if __name__ == '__main__':
    experiments = Experiments.load("experiments.json")
    print(experiments.experiments)
    experiments.add(Experiment.from_pdb("test", "1crn"))
    experiments.save("experiments.json")
    print(experiments.experiments)
