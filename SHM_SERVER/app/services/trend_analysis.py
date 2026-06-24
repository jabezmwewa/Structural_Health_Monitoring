"""
trend_analysis.py — trend / early-warning features per signal.

Pure-Python rolling statistics over recent samples (no numpy — the data volume
is small): baseline, linear-regression slope, EWMA, z-score, and a projection of
when a rising signal would cross its warning/critical threshold. This is what
lets the system flag a developing issue BEFORE a fixed threshold is crossed —
the core of the "trends, not thresholds" requirement.
"""

from datetime import datetime, timedelta
from statistics import mean, pstdev

from app.models import Sample, StructuralElement, StrainMeasurement
from config import Config

ENV_PARAMS = ('temperature', 'humidity', 'vibration', 'sound')


def _slope(xs, ys):
    """Least-squares slope of ys vs xs (units of y per unit x). 0 if degenerate."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = mean(xs), mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def _ewma(values, alpha=0.3):
    it = iter(values)
    e = next(it)
    for v in it:
        e = alpha * v + (1 - alpha) * e
    return e


def analyse_series(times, values, spec):
    """
    times: chronological list[datetime]; values: aligned list[float|None].
    Returns trend features, or None if there isn't enough data.
    """
    pairs = [(t, v) for t, v in zip(times, values) if v is not None]
    if len(pairs) < 3:
        return None
    times = [t for t, _ in pairs]
    values = [v for _, v in pairs]

    t0 = times[0]
    hrs = [(t - t0).total_seconds() / 3600 for t in times]
    current = values[-1]
    baseline = mean(values[:max(1, len(values) // 4)])   # earliest quarter
    avg = mean(values)
    sd = pstdev(values) or 1e-9
    slope_hr = _slope(hrs, values)                        # units per hour
    span = (hrs[-1] - hrs[0]) or 1.0
    delta = slope_hr * span

    direction = 'stable'
    if abs(delta) > 0.5 * sd:
        direction = 'rising' if delta > 0 else 'falling'

    def project(limit):
        if limit is None or slope_hr <= 1e-9 or current >= limit:
            return None
        return round((limit - current) / slope_hr, 1)

    return {
        'current':        round(current, 2),
        'baseline':       round(baseline, 2),
        'mean':           round(avg, 2),
        'ewma':           round(_ewma(values), 2),
        'slope_per_hour': round(slope_hr, 4),
        'slope_per_day':  round(slope_hr * 24, 3),
        'pct_change':     round((current - baseline) / abs(baseline) * 100, 1) if baseline else 0.0,
        'zscore':         round((current - avg) / sd, 2),
        'direction':      direction,
        'hours_to_warn':  project(spec.get('warn_high')),
        'hours_to_crit':  project(spec.get('crit_high')),
        'n':              len(values),
    }


def analyse_device(device, hours=72):
    """Trend features for every signal on a device over the last `hours`."""
    since = datetime.utcnow() - timedelta(hours=hours)
    samples = (
        Sample.query.filter(Sample.device_id == device.id, Sample.timestamp >= since)
        .order_by(Sample.timestamp.asc())
        .all()
    )
    times = [s.timestamp for s in samples]
    specs = Config.THRESHOLD_SPECS

    out = {'device_id': device.id, 'hours': hours, 'environment': {}, 'elements': []}

    for param in ENV_PARAMS:
        feats = analyse_series(times, [getattr(s, param) for s in samples], specs.get(param, {}))
        if feats:
            out['environment'][param] = feats

    elements = (
        StructuralElement.query.filter_by(device_id=device.id)
        .order_by(StructuralElement.id).all()
    )
    strain_by_elem = {e.id: {} for e in elements}
    if samples:
        sample_ids = [s.id for s in samples]
        for m in StrainMeasurement.query.filter(StrainMeasurement.sample_id.in_(sample_ids)):
            strain_by_elem.setdefault(m.element_id, {})[m.sample_id] = m.microstrain

    strain_spec = specs.get('strain', {})
    for e in elements:
        series = [strain_by_elem.get(e.id, {}).get(s.id) for s in samples]
        feats = analyse_series(times, series, strain_spec)
        if feats:
            out['elements'].append({
                'element_id': e.id, 'name': e.name,
                'element_type': e.element_type, 'strain': feats,
            })

    return out
