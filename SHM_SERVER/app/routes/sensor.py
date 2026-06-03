from flask import Blueprint, request, jsonify
from app import db
from app.models import SensorReading
from app.services.health_score import compute_health_score
from app.services.alert_engine import check_thresholds

sensor_bp = Blueprint('sensor', __name__)


@sensor_bp.route('/api/data', methods=['POST'])
def receive_data():
    """
    Receives JSON payload from the ESP32.
    Expected body:
        {
            "strain":      float,   # μm/m
            "temperature": float,   # °C
            "humidity":    float,   # %
            "pressure":    float,   # kPa
            "vibration":   float    # mm/s  (optional)
        }
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({'error': 'Invalid or missing JSON body'}), 400

    required = ['strain', 'temperature', 'humidity', 'pressure']
    missing = [f for f in required if f not in payload]
    if missing:
        return jsonify({'error': f'Missing fields: {missing}'}), 400

    # 1. Save raw reading
    reading = SensorReading(
        strain      = payload['strain'],
        temperature = payload['temperature'],
        humidity    = payload['humidity'],
        pressure    = payload['pressure'],
        vibration   = payload.get('vibration'),
    )
    db.session.add(reading)
    db.session.flush()  # get reading.id before commit

    # 2. Compute health score
    compute_health_score(reading)

    # 3. Check thresholds and create alerts if needed
    check_thresholds(reading)

    db.session.commit()

    return jsonify({'status': 'ok', 'reading_id': reading.id}), 201


@sensor_bp.route('/api/latest', methods=['GET'])
def latest_reading():
    """Returns the most recent sensor reading."""
    reading = SensorReading.query.order_by(SensorReading.timestamp.desc()).first()
    if not reading:
        return jsonify({'error': 'No readings yet'}), 404
    return jsonify(reading.to_dict())


@sensor_bp.route('/api/readings', methods=['GET'])
def get_readings():
    """Returns the last N readings (default 24) for chart history."""
    limit = request.args.get('limit', 24, type=int)
    readings = (
        SensorReading.query
        .order_by(SensorReading.timestamp.desc())
        .limit(limit)
        .all()
    )
    # Return in chronological order for charts
    return jsonify([r.to_dict() for r in reversed(readings)])
