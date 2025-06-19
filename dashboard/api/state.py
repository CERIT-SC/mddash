import json
from dataclasses import asdict
from pathlib import Path

from experiment import Experiment
from config import STATE_FILE


class Experiments:
    def __init__(self, experiments: dict[str, Experiment] = {}):
        self.experiments = experiments

    @classmethod
    def load(cls, filepath: Path | str) -> "Experiments":
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}

        experiments_dict = {id: Experiment(**exp) for id, exp in data.items()}
        return cls(experiments_dict)

    def get_all(self) -> list[dict]:
        return [asdict(self.get(exp_id)) for exp_id in self.experiments.keys()]

    def save(self, filepath: Path | str) -> None:
        data = {id: asdict(exp) for id, exp in self.experiments.items()}

        with open(filepath, "w") as f:
            # TODO: in production, use json.dump(data, f) (without indent to save space)
            json.dump(data, f, indent=4)

    def add(self, experiment: Experiment) -> None:
        self.experiments[experiment.id] = experiment

    def remove(self, experiment_id: str) -> None:
        '''
        Remove an experiment by its ID and clean up its directory.

        :param experiment_id: The ID of the experiment to remove.
        :raise ValueError: If the experiment ID is not found.
        '''
        if experiment_id not in self.experiments:
            raise ValueError(f"Experiment with id '{experiment_id}' not found")

        self.experiments[experiment_id].delete() # Clean up experiment directory
        del self.experiments[experiment_id]

    def get(self, experiment_id: str) -> Experiment:
        '''
        Get an experiment by its ID.

        :param experiment_id: The ID of the experiment to retrieve.
        :return: The experiment object.
        :raise ValueError: If the experiment ID is not found.
        '''
        if experiment_id not in self.experiments:
            raise ValueError(f"Experiment with id '{experiment_id}' not found")
        
        # update step and status
        old_step = self.experiments[experiment_id].step
        self.experiments[experiment_id].update_step()

        # save if step changed
        if self.experiments[experiment_id].step != old_step:
            self.save(STATE_FILE)

        return self.experiments[experiment_id]


if __name__ == '__main__':
    experiments = Experiments.load("experiments.json")
    print(experiments.experiments)
    experiments.add(Experiment.from_pdb("test", "1crn"))
    experiments.save("experiments.json")
    print(experiments.experiments)
