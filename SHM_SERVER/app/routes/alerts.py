from flask import Blueprint, jsonify, request
from app import db
from app.models import Alert

alerts_bp = Blueprint('alerts', __name__)


@alerts_bp.route('/api/alerts', methods=['GET'])
def get_alerts():
    """
    Returns recent alerts.
    Query params:
        limit    int  – number of alerts to return (default 20)
        resolved bool – include resolved alerts (default false)
    """
    limit    = request.args.get('limit', 20, type=int)
    resolved = request.args.get('resolved', 'false').lower() == 'true'

    query = Alert.query
    if not resolved:
        query = query.filter_by(resolved=False)

    alerts = query.order_by(Alert.timestamp.desc()).limit(limit).all()
    return jsonify([a.to_dict() for a in alerts])


@alerts_bp.route('/api/alerts/<int:alert_id>/resolve', methods=['PATCH'])
def resolve_alert(alert_id):
    """Marks a single alert as resolved."""
    alert = Alert.query.get_or_404(alert_id)
    alert.resolved = True
    db.session.commit()
    return jsonify({'status': 'resolved', 'id': alert.id})
