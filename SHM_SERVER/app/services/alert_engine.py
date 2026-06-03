from app import db
from app.models import Alert
from config import Config


def check_thresholds(reading) -> list:
    """
    Compares sensor values against thresholds defined in Config.
    Creates Alert records for any breaches found.
    Returns a list of Alert objects (may be empty).
    """
    t      = Config.THRESHOLDS
    alerts = []

    checks = [
        # (parameter, value, warn_threshold, critical_threshold, direction)
        # direction: 'high' = alert when above, 'low' = alert when below
        ('strain',      reading.strain,      t['STRAIN_WARN'],      t['STRAIN_MAX'],       'high'),
        ('temperature', reading.temperature, t['TEMPERATURE_MAX'],  t['TEMPERATURE_MAX'],  'high'),
        ('temperature', reading.temperature, t['TEMPERATURE_MIN'],  t['TEMPERATURE_MIN'],  'low'),
        ('humidity',    reading.humidity,    t['HUMIDITY_MAX'],     t['HUMIDITY_MAX'],     'high'),
        ('humidity',    reading.humidity,    t['HUMIDITY_MIN'],     t['HUMIDITY_MIN'],     'low'),
        ('pressure',    reading.pressure,    t['PRESSURE_MAX'],     t['PRESSURE_MAX'],     'high'),
        ('pressure',    reading.pressure,    t['PRESSURE_MIN'],     t['PRESSURE_MIN'],     'low'),
    ]

    if reading.vibration is not None:
        checks.append(
            ('vibration', reading.vibration, t['VIBRATION_WARN'], t['VIBRATION_MAX'], 'high')
        )

    for param, value, warn_thresh, crit_thresh, direction in checks:
        if value is None:
            continue

        breached = (
            (direction == 'high' and value > warn_thresh) or
            (direction == 'low'  and value < warn_thresh)
        )

        if not breached:
            continue

        severity = 'critical' if (
            (direction == 'high' and value > crit_thresh) or
            (direction == 'low'  and value < crit_thresh)
        ) else 'warning'

        direction_word = 'exceeded' if direction == 'high' else 'dropped below'
        message = (
            f"{param.capitalize()} {direction_word} threshold: "
            f"{value:.2f} (limit: {warn_thresh})"
        )

        alert = Alert(
            reading_id=reading.id,
            parameter=param,
            value=value,
            threshold=warn_thresh,
            severity=severity,
            message=message,
        )
        db.session.add(alert)
        alerts.append(alert)

    return alerts
