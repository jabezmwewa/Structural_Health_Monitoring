from datetime import datetime

from flask import Blueprint, request, jsonify
from app import db
from app.models import (
    SensorReading,
    Device,
    StructuralElement,
    Sample,
    StrainMeasurement,
)
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


# ── v2 ingestion (per-element) ───────────────────────────────────────────────

@sensor_bp.route('/api/v2/ingest', methods=['POST'])
def ingest_v2():
    """
    Receives a per-element payload from a device and stores it as one Sample
    plus a StrainMeasurement per element.

    Expected body:
        {
            "device_id":   int,     # optional; defaults to the first device
            "temperature": float,   # °C   (optional)
            "humidity":    float,   # %    (optional)
            "vibration":   float,   # mm/s (optional)
            "sound":       float,   # acoustic level (optional)
            "strains": [            # optional list, one entry per element
                {"element_id": int, "microstrain": float},
                {"element": "Column A", "microstrain": float}  # name also accepted
            ]
        }

    Note: health scoring and alerting are not yet wired to this path — that
    arrives when the alert/health pipeline is migrated to the v2 model.
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({'error': 'Invalid or missing JSON body'}), 400

    # Resolve the device (explicit id, else the only/first registered device).
    if payload.get('device_id') is not None:
        device = db.session.get(Device, payload['device_id'])
    else:
        device = Device.query.order_by(Device.id).first()
    if device is None:
        return jsonify({
            'error': 'No device registered. Run `flask seed-demo` or create a device first.'
        }), 400

    sample = Sample(
        device_id   = device.id,
        temperature = payload.get('temperature'),
        humidity    = payload.get('humidity'),
        vibration   = payload.get('vibration'),
        sound       = payload.get('sound'),
    )
    db.session.add(sample)
    db.session.flush()  # need sample.id for strain rows

    # Attach per-element strains; collect any that can't be resolved.
    elements_by_name = {e.name: e for e in device.elements}
    unresolved = []
    for item in payload.get('strains', []):
        micro = item.get('microstrain')
        if micro is None:
            continue
        element = None
        if item.get('element_id') is not None:
            element = db.session.get(StructuralElement, item['element_id'])
        elif item.get('element'):
            element = elements_by_name.get(item['element'])
        if element is None or element.device_id != device.id:
            unresolved.append(item)
            continue
        db.session.add(StrainMeasurement(
            sample_id=sample.id, element_id=element.id, microstrain=micro,
        ))

    device.last_seen = datetime.utcnow()
    db.session.commit()

    response = {'status': 'ok', 'sample_id': sample.id, 'device_id': device.id}
    if unresolved:
        response['unresolved_strains'] = unresolved  # element_id/name not found on device
    return jsonify(response), 201
