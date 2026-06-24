import os

from dotenv import load_dotenv

# Load variables from a local .env file (if present) so os.getenv() picks them up.
# python-dotenv is already a project dependency; this makes `.env` take effect when
# running via `python run.py` (Flask's CLI would auto-load it, but run.py does not).
load_dotenv()


class Config:
    # ── Flask ──────────────────────────────────────────────────────────────
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-change-in-production')
    DEBUG      = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'

    # ── Database ───────────────────────────────────────────────────────────
    # SQLite for development; swap for PostgreSQL/MySQL in production:
    #   postgresql://user:password@localhost/shm_db
    SQLALCHEMY_DATABASE_URI     = os.getenv('DATABASE_URL', 'sqlite:///shm.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── External APIs ──────────────────────────────────────────────────────
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

    # ── Sensor Thresholds ──────────────────────────────────────────────────
    # Edit these to match your structure's safe operating ranges.
    THRESHOLDS = {
        # Strain (μm/m)
        'STRAIN_MIN':       0,
        'STRAIN_WARN':    400,      # warning level
        'STRAIN_MAX':     500,      # critical level

        # Temperature (°C)
        'TEMPERATURE_MIN':  5.0,
        'TEMPERATURE_MAX': 45.0,

        # Humidity (%)
        'HUMIDITY_MIN':    20.0,
        'HUMIDITY_MAX':    85.0,

        # Pressure (kPa)
        'PRESSURE_MIN':    90.0,
        'PRESSURE_MAX':   110.0,

        # Vibration (mm/s)
        'VIBRATION_WARN':  15.0,    # warning level
        'VIBRATION_MAX':   25.0,    # critical level
    }

    # ── v2 threshold specs (per-parameter, with a warning band) ─────────────
    # Used by the v2 evaluation service. Each value's status is one of
    # ok | warning | critical. Keys per parameter (all optional):
    #   crit_low, warn_low, warn_high, crit_high
    # A value is "critical" below crit_low / above crit_high, "warning" below
    # warn_low / above warn_high, otherwise "ok". This single source of truth
    # drives both alerting and the health score, so they cannot disagree.
    THRESHOLD_SPECS = {
        'strain':      {'unit': 'μm/m', 'warn_high': 400, 'crit_high': 500},
        'temperature': {'unit': '°C',   'crit_low': 5,  'warn_low': 10, 'warn_high': 40, 'crit_high': 45},
        'humidity':    {'unit': '%',    'crit_low': 20, 'warn_low': 30, 'warn_high': 75, 'crit_high': 85},
        'vibration':   {'unit': 'mm/s', 'warn_high': 15, 'crit_high': 25},
        'sound':       {'unit': 'dB',   'warn_high': 70, 'crit_high': 85},   # placeholder levels
    }
