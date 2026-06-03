from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')

    db.init_app(app)

    from app.routes.sensor import sensor_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.alerts import alerts_bp

    app.register_blueprint(sensor_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(alerts_bp)

    with app.app_context():
        db.create_all()

    return app
