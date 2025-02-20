# vim: set ai ts=4 expandtab :

from flask import Flask, Blueprint, request, send_from_directory
from dataclasses import asdict

from config import STATE_FILE
from experiment import Experiment
from state import Experiments

import os

experiments = Experiments.load(STATE_FILE)
prefix = f'/user/{os.environ["JUPYTERHUB_USER"]}'

#from flask_cors import CORS # DEV ONLY
#CORS(app)   # DEV ONLY

bp = Blueprint('dash',__name__,
    url_prefix = prefix,
    )

@bp.route("/")
def index():
    return {"status": "success", "message": "FAIR MD Dashboard & API"}

@bp.route("/dash", defaults={'path':''})
@bp.route("/dash/<path:path>")
def static(path):
    if path == '' or path.endswith('/'):
        return send_from_directory('/var/tmp/dash','index.html')
    else:
        return send_from_directory('/var/tmp/dash',path)

@bp.route("/api/experiments", methods=["GET"])
def list_experiments():
    try:
        return {"status": "success", "data": experiments.get_all()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@bp.route("/api/experiments/<experiment_id>", methods=["GET"])
def get_experiment(experiment_id):
    try:
        return {"status": "success", "data": experiments.get(experiment_id)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@bp.route("/api/experiments", methods=["POST"])
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


@bp.route("/api/experiments/<experiment_id>", methods=["DELETE"])
def delete_experiment(experiment_id):
    try:
        experiments.remove(experiment_id)
        experiments.save(STATE_FILE)
        return {"status": "success", "message": "Experiment deleted"}

    except Exception as e:
        return {"status": "error", "message": str(e)}

app = Flask(__name__)
app.register_blueprint(bp,url_prefix=prefix)


if __name__ == "__main__":
    app.run(host='0.0.0.0',port=8888,debug=True)
