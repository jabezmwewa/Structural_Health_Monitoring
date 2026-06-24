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
    """Computed structural health index (0–100) for a reading or a v2 sample."""
    __tablename__ = 'health_scores'

    id         = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=True)  # legacy
    sample_id  = db.Column(db.Integer, db.ForeignKey('samples.id'), nullable=True)          # v2
    score      = db.Column(db.Float, nullable=False)    # 0 (critical) – 100 (healthy)
    label      = db.Column(db.String(20), nullable=False)  # "Healthy" | "Warning" | "Critical"
    timestamp  = db.Column(db.DateTime, default=datetime.utcnow)

    reading = db.relationship('SensorReading', backref='health_score')

    def to_dict(self):
        return {
            'id':         self.id,
            'reading_id': self.reading_id,
            'sample_id':  self.sample_id,
            'score':      self.score,
            'label':      self.label,
            'timestamp':  self.timestamp.isoformat(),
        }


class Alert(db.Model):
    """
    A threshold breach. Legacy alerts link to a SensorReading; v2 alerts link to
    a device/element/sample and follow an active→resolved lifecycle: one active
    alert per (element, parameter), updated in place until the value returns to
    ok, then auto-resolved.
    """
    __tablename__ = 'alerts'

    id          = db.Column(db.Integer, primary_key=True)
    reading_id  = db.Column(db.Integer, db.ForeignKey('sensor_readings.id'), nullable=True)      # legacy
    device_id   = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=True)              # v2
    element_id  = db.Column(db.Integer, db.ForeignKey('structural_elements.id'), nullable=True)  # v2 (None = device-level)
    sample_id   = db.Column(db.Integer, db.ForeignKey('samples.id'), nullable=True)              # v2 (last triggering sample)
    parameter   = db.Column(db.String(50), nullable=False)   # e.g. "temperature", "strain"
    value       = db.Column(db.Float, nullable=False)        # value at first trigger
    last_value  = db.Column(db.Float, nullable=True)         # most recent value while active
    threshold   = db.Column(db.Float, nullable=False)        # breached boundary
    severity    = db.Column(db.String(20), nullable=False)   # "warning" | "critical"
    message     = db.Column(db.String(255), nullable=False)
    resolved    = db.Column(db.Boolean, default=False)
    timestamp   = db.Column(db.DateTime, default=datetime.utcnow)   # first seen
    last_seen   = db.Column(db.DateTime, default=datetime.utcnow)   # most recent breach
    resolved_at = db.Column(db.DateTime, nullable=True)

    reading = db.relationship('SensorReading', backref='alerts')
    element = db.relationship('StructuralElement')

    def to_dict(self):
        return {
            'id':          self.id,
            'reading_id':  self.reading_id,
            'device_id':   self.device_id,
            'element_id':  self.element_id,
            'element':     self.element.name if self.element else None,
            'sample_id':   self.sample_id,
            'parameter':   self.parameter,
            'value':       self.value,
            'last_value':  self.last_value,
            'threshold':   self.threshold,
            'severity':    self.severity,
            'message':     self.message,
            'resolved':    self.resolved,
            'timestamp':   self.timestamp.isoformat(),
            'last_seen':   self.last_seen.isoformat() if self.last_seen else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
        }


# ════════════════════════════════════════════════════════════════════════════
# v2 data model — per-element structure
# ----------------------------------------------------------------------------
# Mirrors the hardware: one Device (ESP32 node) hosts many StructuralElements
# (columns / slabs). Environment and device-level dynamics (temperature,
# humidity, vibration, sound) are captured once per Sample, while strain is
# recorded per element via StrainMeasurement. These tables are additive — the
# legacy SensorReading path above keeps working until ingestion is migrated.
# ════════════════════════════════════════════════════════════════════════════


class Device(db.Model):
    """A physical monitoring node (e.g. an ESP32)."""
    __tablename__ = 'devices'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(80), nullable=False)
    location   = db.Column(db.String(120), nullable=True)
    api_key    = db.Column(db.String(64), nullable=True)   # used for ingest auth later
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen  = db.Column(db.DateTime, nullable=True)

    elements = db.relationship('StructuralElement', backref='device', lazy=True)
    samples  = db.relationship('Sample', backref='device', lazy=True)

    def to_dict(self):
        return {
            'id':        self.id,
            'name':      self.name,
            'location':  self.location,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
        }


class StructuralElement(db.Model):
    """A monitored structural member belonging to a device (a column or slab)."""
    __tablename__ = 'structural_elements'

    id           = db.Column(db.Integer, primary_key=True)
    device_id    = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)
    name         = db.Column(db.String(80), nullable=False)    # e.g. "Column A"
    element_type = db.Column(db.String(20), nullable=False)    # "column" | "slab"
    description  = db.Column(db.String(255), nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':           self.id,
            'device_id':    self.device_id,
            'name':         self.name,
            'element_type': self.element_type,
            'description':  self.description,
        }


class Sample(db.Model):
    """One timestamped sample from a device: environment + device-level signals."""
    __tablename__ = 'samples'

    id          = db.Column(db.Integer, primary_key=True)
    device_id   = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)
    temperature = db.Column(db.Float, nullable=True)   # °C   (DHT22)
    humidity    = db.Column(db.Float, nullable=True)   # %    (DHT22)
    vibration   = db.Column(db.Float, nullable=True)   # mm/s (device-level sensor)
    sound       = db.Column(db.Float, nullable=True)   # acoustic level (repurposed from pressure)
    timestamp   = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    strains = db.relationship(
        'StrainMeasurement', backref='sample', lazy=True,
        cascade='all, delete-orphan',
    )

    def to_dict(self):
        return {
            'id':          self.id,
            'device_id':   self.device_id,
            'temperature': self.temperature,
            'humidity':    self.humidity,
            'vibration':   self.vibration,
            'sound':       self.sound,
            'timestamp':   self.timestamp.isoformat(),
            'strains':     [s.to_dict() for s in self.strains],
        }


class StrainMeasurement(db.Model):
    """Per-element strain reading captured within a Sample."""
    __tablename__ = 'strain_measurements'

    id          = db.Column(db.Integer, primary_key=True)
    sample_id   = db.Column(db.Integer, db.ForeignKey('samples.id'), nullable=False)
    element_id  = db.Column(db.Integer, db.ForeignKey('structural_elements.id'), nullable=False)
    microstrain = db.Column(db.Float, nullable=False)   # μm/m

    element = db.relationship('StructuralElement')

    def to_dict(self):
        return {
            'id':          self.id,
            'sample_id':   self.sample_id,
            'element_id':  self.element_id,
            'microstrain': self.microstrain,
        }
