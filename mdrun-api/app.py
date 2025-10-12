from flask import Flask
from flask_cors import CORS

from config import DB_URL
from extensions import db, ma
from routes import mdrun_bp, health_bp
from polling import start_polling


def create_app() -> Flask:
    app = Flask(__name__)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = DB_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    CORS(app)
    
    db.init_app(app)
    ma.init_app(app)
    
    app.register_blueprint(mdrun_bp)
    app.register_blueprint(health_bp)
    
    with app.app_context():
        db.create_all()
    
    return app


app = create_app()

# Start job status polling in background thread
start_polling(app)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
