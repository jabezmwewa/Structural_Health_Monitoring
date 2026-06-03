from datetime import datetime
from app import db


class SensorReading(db.Model):
    """Raw sensor readings from the ESP32."""
    __tablename__ = 'sensor_readings'

    id          = db.Column(db.Integer, primary_key=True)
    strain      = db.Column(db.Float, nullable=False)   # μm/m
    temperature = db.Column(db.Float, nullable=False)   # °C
    humidity    = db.Column(db.Float, nullable=False)   # %
    pressure    = db.Column(db.Float, nullable=False)   # kPa
    vibration   = db.Column(db.Float, nullable=True)    # mm/s (optional sensor)
    timestamp   = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':          self.id,
            'strain':      self.strain,
            'temperature': self.temperature,
            'humidity':    self.humidity,
            'pressure':    self.pressure,
            'vibration':   self.vibration,
            'timestamp':   self.timestamp.isoformat(),
        }


class HealthScore(db.Model):
    """Computed structural health index (0–100) per reading."""
    __tablename__ = 'health_scores'

    id         = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False)
    score      = db.Column(db.Float, nullable=False)    # 0 (critical) – 100 (healthy)
    label      = db.Column(db.String(20), nullable=False)  # "Healthy" | "Warning" | "Critical"
    timestamp  = db.Column(db.DateTime, default=datetime.utcnow)

    reading = db.relationship('SensorReading', backref='health_score')

    def to_dict(self):
        return {
            'id':         self.id,
            'reading_id': self.reading_id,
            'score':      self.score,
            'label':      self.label,
            'timestamp':  self.timestamp.isoformat(),
        }


class Alert(db.Model):
    """Triggered when a sensor value exceeds defined thresholds."""
    __tablename__ = 'alerts'

    id          = db.Column(db.Integer, primary_key=True)
    reading_id  = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=False)
    parameter   = db.Column(db.String(50), nullable=False)   # e.g. "temperature"
    value       = db.Column(db.Float, nullable=False)
    threshold   = db.Column(db.Float, nullable=False)
    severity    = db.Column(db.String(20), nullable=False)   # "warning" | "critical"
    message     = db.Column(db.String(255), nullable=False)
    resolved    = db.Column(db.Boolean, default=False)
    timestamp   = db.Column(db.DateTime, default=datetime.utcnow)

    reading = db.relationship('SensorReading', backref='alerts')

    def to_dict(self):
        return {
            'id':         self.id,
            'reading_id': self.reading_id,
            'parameter':  self.parameter,
            'value':      self.value,
            'threshold':  self.threshold,
            'severity':   self.severity,
            'message':    self.message,
            'resolved':   self.resolved,
            'timestamp':  self.timestamp.isoformat(),
        }
