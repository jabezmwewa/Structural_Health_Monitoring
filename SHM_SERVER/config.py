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
