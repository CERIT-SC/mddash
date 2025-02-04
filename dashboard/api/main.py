from flask import Flask, request

from config import STATE_FILE
from experiment import Experiment
from state import Experiments

experiments = Experiments.load(STATE_FILE)
app = Flask(__name__)


@app.route("/")
def index():
    return {"status": "success", "message": "Dashboard API"}


@app.route("/new", methods=["POST"])
def create_experiment():
    try:
        name = request.form.get("name")
        type = request.form.get("type")
        pdb = request.form.get("pdb")
        repo = request.form.get("repo")
        file = request.files.get("file")

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
        return {"status": "success", "message": "Experiment created"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    app.run(port=3000)
