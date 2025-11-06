"""
Demo API Flask application.
Initializes the app and starts the background simulator.
"""

from flask import Flask
from flask_cors import CORS

from routes import bp
from simulator import simulator


def create_demo_app() -> Flask:
    """Create and configure the demo Flask app."""
    app = Flask(__name__)
    CORS(app)
    
    # Register blueprint
    app.register_blueprint(bp)
    
    # Start simulator
    simulator.start()
    
    return app


def run_demo_app(host: str = '0.0.0.0', port: int = 8888, debug: bool = True):
    """Run the demo app."""
    app = create_demo_app()
    
    try:
        app.run(debug=debug, host=host, port=port)
    finally:
        simulator.stop()


if __name__ == '__main__':
    run_demo_app()
