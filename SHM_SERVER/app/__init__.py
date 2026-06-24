from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

from config import Config


db = SQLAlchemy()
migrate = Migrate()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    # Import models so Alembic autogenerate can see them, then register the
    # migration engine. The schema is managed by Flask-Migrate (`flask db
    # upgrade`) — not db.create_all() — so changes are versioned and reversible.
    from app import models  # noqa: F401
    migrate.init_app(app, db)

    from app.routes.alerts import alerts_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.sensor import sensor_bp

    app.register_blueprint(alerts_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(sensor_bp)

    return app
