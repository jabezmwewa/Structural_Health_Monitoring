from app import db
from app.models import HealthScore
from config import Config


def compute_health_score(reading) -> HealthScore:
    """
    Computes a Health Index (0–100) from a SensorReading.

    Scoring logic (equal-weight penalty per parameter):
      - Each parameter starts at 100.
      - Score is reduced proportionally the further a value
        drifts outside its safe range.
      - Final score is the average across all parameters.

    Labels:
      80–100  → Healthy
      50–79   → Warning
      0–49    → Critical
    """
    penalties = []

    def _penalty(value, low, high):
        """Returns 0 (no penalty) to 100 (maximum penalty)."""
        if value is None:
            return None
        if low <= value <= high:
            return 0.0
        range_size = high - low
        if value < low:
            drift = (low - value) / range_size
        else:
            drift = (value - high) / range_size
        return min(drift * 100, 100)

    t = Config.THRESHOLDS

    for param, lo_key, hi_key, val in [
        ('strain',      'STRAIN_MIN',      'STRAIN_MAX',      reading.strain),
        ('temperature', 'TEMPERATURE_MIN', 'TEMPERATURE_MAX', reading.temperature),
        ('humidity',    'HUMIDITY_MIN',    'HUMIDITY_MAX',    reading.humidity),
        ('pressure',    'PRESSURE_MIN',    'PRESSURE_MAX',    reading.pressure),
    ]:
        p = _penalty(val, t[lo_key], t[hi_key])
        if p is not None:
            penalties.append(p)

    if reading.vibration is not None:
        p = _penalty(reading.vibration, 0, t['VIBRATION_MAX'])
        penalties.append(p)

    avg_penalty = sum(penalties) / len(penalties) if penalties else 0
    score = max(0.0, 100.0 - avg_penalty)

    if score >= 80:
        label = 'Healthy'
    elif score >= 50:
        label = 'Warning'
    else:
        label = 'Critical'

    health = HealthScore(
        reading_id=reading.id,
        score=round(score, 2),
        label=label,
    )
    db.session.add(health)
    return health
