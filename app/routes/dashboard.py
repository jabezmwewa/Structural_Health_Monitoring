from flask import Blueprint, render_template
from app.models import SensorReading, HealthScore

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    """
    Serves the main SHM dashboard.
    Passes the last 24 readings and the latest health score
    into the template so charts render immediately on load.
    """
    readings = (
        SensorReading.query
        .order_by(SensorReading.timestamp.desc())
        .limit(24)
        .all()
    )
    readings_data = [r.to_dict() for r in reversed(readings)]

    latest_health = (
        HealthScore.query
        .order_by(HealthScore.timestamp.desc())
        .first()
    )

    return render_template(
        'dashboard.html',
        readings=readings_data,
        health_score=latest_health.to_dict() if latest_health else None,
    )
