import json
from dataclasses import asdict

from experiment import Experiment


class Experiments:
    def __init__(self, experiments: list[Experiment] = None):
        self.experiments = experiments or []

    @classmethod
    def load(cls, filepath: str) -> "Experiments":
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = []

        experiments_list = [Experiment(**exp) for exp in data]
        return cls(experiments_list)

    def get_dicts(self) -> list[dict]:
        return [asdict(exp) for exp in self.experiments]

    def save(self, filepath: str) -> None:
        data = self.get_dicts()
        with open(filepath, "w") as f:
            # TODO: in production, use json.dump(data, f) to save space
            json.dump(data, f, indent=4)

    def add(self, experiment: Experiment) -> None:
        self.experiments.append(experiment)

    def remove(self, experiment_id: str) -> None:
        self.experiments = list(filter(lambda exp: exp.id != experiment_id, self.experiments))

    def get(self, experiment_id: str) -> Experiment:
        for exp in self.experiments:
            if exp.id == experiment_id:
                return exp
        return None


if __name__ == '__main__':
    experiments = Experiments.load("experiments.json")
    print(experiments.experiments)
    experiments.add(Experiment.from_pdb("test", "1crn"))
    experiments.save("experiments.json")
    print(experiments.experiments)
