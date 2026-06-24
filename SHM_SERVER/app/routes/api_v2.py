"""
api_v2.py — read endpoints for the v2 per-element model.

Powers the (Phase 2) dashboard: current per-element status, time-series history
for trend charts (with time-range filtering and downsampling), and alerts.
"""

from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify

from app.models import (
    Device, StructuralElement, Sample, StrainMeasurement, Alert, HealthScore,
)
from app.services.evaluation import classify
from app.services.trend_analysis import analyse_device
from app.services.diagnosis import rank_causes
from config import Config

api_v2_bp = Blueprint('api_v2', __name__, url_prefix='/api/v2')

_SPECS = Config.THRESHOLD_SPECS


def _status(param, value):
    return classify(value, _SPECS.get(param, {}))


def _first_device():
    return Device.query.order_by(Device.id).first()


@api_v2_bp.route('/elements', methods=['GET'])
def list_elements():
    """All structural elements (optionally for one device)."""
    query = StructuralElement.query
    device_id = request.args.get('device_id', type=int)
    if device_id is not None:
        query = query.filter_by(device_id=device_id)
    return jsonify([e.to_dict() for e in query.order_by(StructuralElement.id).all()])


@api_v2_bp.route('/latest', methods=['GET'])
def latest():
    """
    Current snapshot for the dashboard: device-level signals (with status),
    latest strain per element (with status), current health, active alert count.
    """
    device = _first_device()
    if device is None:
        return jsonify({'error': 'No device registered.'}), 404

    sample = (
        Sample.query.filter_by(device_id=device.id)
        .order_by(Sample.timestamp.desc())
        .first()
    )

    environment = {}
    if sample is not None:
        for param in ('temperature', 'humidity', 'vibration', 'sound'):
            value = getattr(sample, param)
            environment[param] = {'value': value, 'status': _status(param, value)}

    # latest strain per element (independent of which sample carried it)
    elements = []
    for el in StructuralElement.query.filter_by(device_id=device.id).order_by(StructuralElement.id):
        m = (
            StrainMeasurement.query.filter_by(element_id=el.id)
            .order_by(StrainMeasurement.id.desc())
            .first()
        )
        micro = m.microstrain if m else None
        elements.append({
            'id': el.id, 'name': el.name, 'element_type': el.element_type,
            'microstrain': micro, 'status': _status('strain', micro),
        })

    health = (
        HealthScore.query.filter(HealthScore.sample_id.isnot(None))
        .order_by(HealthScore.timestamp.desc())
        .first()
    )
    active_alerts = Alert.query.filter_by(device_id=device.id, resolved=False).count()

    return jsonify({
        'device': device.to_dict(),
        'timestamp': sample.timestamp.isoformat() if sample else None,
        'environment': environment,
        'elements': elements,
        'health': health.to_dict() if health else None,
        'active_alerts': active_alerts,
    })


@api_v2_bp.route('/history', methods=['GET'])
def history():
    """
    Time-series for trend charts.

    Query params:
        hours       lookback window in hours (default 24)
        element_id  include this element's strain series (optional)
        max_points  downsample to at most this many points (default 200)
    """
    device = _first_device()
    if device is None:
        return jsonify({'error': 'No device registered.'}), 404

    hours = request.args.get('hours', 24, type=int)
    max_points = max(1, request.args.get('max_points', 200, type=int))
    element_id = request.args.get('element_id', type=int)
    since = datetime.utcnow() - timedelta(hours=hours)

    samples = (
        Sample.query.filter(Sample.device_id == device.id, Sample.timestamp >= since)
        .order_by(Sample.timestamp.asc())
        .all()
    )

    # strain per element (all elements, or one if element_id is given)
    elements = StructuralElement.query.filter_by(device_id=device.id).order_by(StructuralElement.id).all()
    if element_id is not None:
        elements = [e for e in elements if e.id == element_id]

    strain_map = {}   # (sample_id, element_id) -> microstrain
    if elements and samples:
        sample_ids = [s.id for s in samples]
        elem_ids = [e.id for e in elements]
        for m in StrainMeasurement.query.filter(
            StrainMeasurement.sample_id.in_(sample_ids),
            StrainMeasurement.element_id.in_(elem_ids),
        ):
            strain_map[(m.sample_id, m.element_id)] = m.microstrain

    env_fields = ['temperature', 'humidity', 'vibration', 'sound']
    strain_fields = [f'strain:{e.id}' for e in elements]

    rows = []
    for s in samples:
        row = {
            'timestamp': s.timestamp,
            'temperature': s.temperature, 'humidity': s.humidity,
            'vibration': s.vibration, 'sound': s.sound,
        }
        for e in elements:
            row[f'strain:{e.id}'] = strain_map.get((s.id, e.id))
        rows.append(row)

    rows = _downsample(rows, env_fields + strain_fields, max_points)

    return jsonify({
        'device_id': device.id,
        'hours': hours,
        'element_id': element_id,
        'count': len(rows),
        'timestamps': [r['timestamp'].isoformat() for r in rows],
        'series': {f: [r[f] for r in rows] for f in env_fields},
        'strains': [
            {'element_id': e.id, 'name': e.name,
             'values': [r[f'strain:{e.id}'] for r in rows]}
            for e in elements
        ],
    })


def _downsample(rows, fields, max_points):
    """
    Reduce rows to <= max_points by averaging consecutive buckets. Each bucket's
    timestamp is its last row's timestamp; None values are ignored in the mean.
    """
    n = len(rows)
    if n <= max_points:
        return rows
    bucket = (n + max_points - 1) // max_points   # ceil(n / max_points)
    out = []
    for i in range(0, n, bucket):
        chunk = rows[i:i + bucket]
        agg = {'timestamp': chunk[-1]['timestamp']}
        for f in fields:
            vals = [r[f] for r in chunk if r[f] is not None]
            agg[f] = round(sum(vals) / len(vals), 3) if vals else None
        out.append(agg)
    return out


@api_v2_bp.route('/alerts', methods=['GET'])
def alerts():
    """
    Alerts with element names.

    Query params:
        active      'true' = unresolved only (default), 'false' = all
        element_id  filter to one element (optional)
        limit       max rows (default 50)
    """
    device = _first_device()
    if device is None:
        return jsonify([])

    active_only = request.args.get('active', 'true').lower() != 'false'
    element_id = request.args.get('element_id', type=int)
    limit = request.args.get('limit', 50, type=int)

    query = Alert.query.filter_by(device_id=device.id)
    if active_only:
        query = query.filter_by(resolved=False)
    if element_id is not None:
        query = query.filter_by(element_id=element_id)

    rows = query.order_by(Alert.last_seen.desc()).limit(limit).all()
    return jsonify([a.to_dict() for a in rows])


@api_v2_bp.route('/analysis', methods=['GET'])
def analysis():
    """Trend features per signal (early-warning view). hours = lookback (default 72)."""
    device = _first_device()
    if device is None:
        return jsonify({'error': 'No device registered.'}), 404
    hours = request.args.get('hours', 72, type=int)
    trends = analyse_device(device, hours)
    return jsonify({'trends': trends, 'diagnosis': rank_causes(trends)})
