"""
evaluation.py — v2 structural evaluation.

A single classify() maps each parameter value to ok | warning | critical using
the threshold specs in Config. The SAME classification drives both the alert
lifecycle and the health score, so an active "critical" alert and a "Healthy"
label can never coexist (the bug in the legacy split between alert_engine and
health_score).
"""

from datetime import datetime

from app import db
from app.models import Alert, HealthScore
from config import Config

# status → penalty applied to the health score (per breaching parameter)
_PENALTY = {'ok': 0.0, 'warning': 15.0, 'critical': 40.0}


def classify(value, spec):
    """Return 'ok' | 'warning' | 'critical' for a value given a parameter spec."""
    if value is None:
        return 'ok'
    if 'crit_low' in spec and value < spec['crit_low']:
        return 'critical'
    if 'crit_high' in spec and value > spec['crit_high']:
        return 'critical'
    if 'warn_low' in spec and value < spec['warn_low']:
        return 'warning'
    if 'warn_high' in spec and value > spec['warn_high']:
        return 'warning'
    return 'ok'


def _breached_threshold(value, spec, status):
    """The boundary the value crossed (for display / the Alert.threshold field)."""
    if status == 'critical':
        if 'crit_low' in spec and value < spec['crit_low']:
            return spec['crit_low']
        if 'crit_high' in spec and value > spec['crit_high']:
            return spec['crit_high']
    if status == 'warning':
        if 'warn_low' in spec and value < spec['warn_low']:
            return spec['warn_low']
        if 'warn_high' in spec and value > spec['warn_high']:
            return spec['warn_high']
    return None


def evaluate_sample(sample):
    """
    Classify every signal on a v2 Sample, drive the alert lifecycle, and write a
    reconciled HealthScore. Returns a summary dict. The caller commits.
    """
    specs = Config.THRESHOLD_SPECS
    statuses = []   # collected statuses feeding the health score

    # device-level signals
    for param in ('temperature', 'humidity', 'vibration', 'sound'):
        value = getattr(sample, param)
        if value is None:
            continue
        spec = specs.get(param, {})
        status = classify(value, spec)
        statuses.append(status)
        _apply_alert(sample, None, param, value, status, spec)

    # element-level strain
    strain_spec = specs.get('strain', {})
    for m in sample.strains:
        status = classify(m.microstrain, strain_spec)
        statuses.append(status)
        _apply_alert(sample, m.element, 'strain', m.microstrain, status, strain_spec)

    # health score from the SAME statuses (label = worst status → can't disagree)
    score = max(0.0, 100.0 - sum(_PENALTY[s] for s in statuses))
    if any(s == 'critical' for s in statuses):
        label = 'Critical'
    elif any(s == 'warning' for s in statuses):
        label = 'Warning'
    else:
        label = 'Healthy'

    db.session.add(HealthScore(sample_id=sample.id, score=round(score, 2), label=label))
    return {'health': {'score': round(score, 2), 'label': label}, 'statuses': statuses}


def _apply_alert(sample, element, param, value, status, spec):
    """
    Maintain a single active alert per (element, parameter): create on first
    breach, update in place while it persists (including warning↔critical changes),
    and auto-resolve when the value returns to ok.
    """
    element_id = element.id if element is not None else None
    active = (
        Alert.query
        .filter_by(device_id=sample.device_id, element_id=element_id,
                   parameter=param, resolved=False)
        .first()
    )
    now = datetime.utcnow()

    if status == 'ok':
        if active is not None:
            active.resolved = True
            active.resolved_at = now
            active.last_value = value
            active.last_seen = now
        return

    threshold = _breached_threshold(value, spec, status)
    unit = spec.get('unit', '')
    # Element context is carried by element_id; keep the message about the signal.
    message = f"{param} {status}: {value:.2f} {unit} (limit {threshold})".strip()

    if active is None:
        db.session.add(Alert(
            device_id=sample.device_id, element_id=element_id, sample_id=sample.id,
            parameter=param, value=value, last_value=value,
            threshold=threshold if threshold is not None else value,
            severity=status, message=message,
            timestamp=now, last_seen=now,
        ))
    else:
        active.last_value = value
        active.last_seen = now
        active.sample_id = sample.id
        active.severity = status   # escalation / de-escalation while active
        active.message = message
        if threshold is not None:
            active.threshold = threshold
