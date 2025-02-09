from flask import Flask, request
from dataclasses import asdict

from config import STATE_FILE
from experiment import Experiment
from state import Experiments

experiments = Experiments.load(STATE_FILE)
app = Flask(__name__)


@app.route("/")
def index():
    return {"status": "success", "message": "FAIR MD Dash API"}


@app.route("/experiments", methods=["GET"])
def list_experiments():
    try:
        return {"status": "success", "data": experiments.get_dicts()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.route("/experiments", methods=["POST"])
def create_experiment():
    try:
        name = request.form.get("experiment-name")
        type = request.form.get("type")
        pdb = request.form.get("pdb-id")
        repo = request.form.get("repo-url")
        file = request.files.get("simulation-file")

        match type:
            case "pdb":
                experiment = Experiment.from_pdb(name, pdb)
            case "repo":
                experiment = Experiment.from_repo(name, repo)
            case "file":
                experiment = Experiment.from_tpr(name, file)
            case _:
                return {"status": "error", "message": "Invalid experiment type"}

        experiments.add(experiment)
        experiments.save(STATE_FILE)
        return {"status": "success", "message": "Experiment created", "data": asdict(experiment)}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.route("/experiments/<experiment_id>", methods=["DELETE"])
def delete_experiment(experiment_id):
    try:
        experiments.remove(experiment_id)
        experiments.save(STATE_FILE)
        return {"status": "success", "message": "Experiment deleted"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    app.run(port=3000)
