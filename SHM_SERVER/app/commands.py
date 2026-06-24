"""
Custom Flask CLI commands.

Run with:  flask <command>   (FLASK_APP=run.py)
"""

import math
import random
from datetime import datetime, timedelta

import click
from flask.cli import with_appcontext

from app import db
from app.models import Device, StructuralElement, Sample, StrainMeasurement
from app.services.evaluation import evaluate_sample

# Placeholder rig layout — rename/extend to match the real structure, or seed
# your own elements. Each tuple is (element name, element type).
DEFAULT_ELEMENTS = [
    ('Column A', 'column'),
    ('Column B', 'column'),
    ('Slab 1',   'slab'),
]


def ensure_default_device():
    """Return the first device, creating a default one with placeholder
    elements if none exists. Idempotent."""
    device = Device.query.order_by(Device.id).first()
    if device is None:
        device = Device(name='SHM Node 1', location='Unspecified')
        db.session.add(device)
        db.session.flush()
    existing = {e.name for e in device.elements}
    for name, etype in DEFAULT_ELEMENTS:
        if name not in existing:
            db.session.add(
                StructuralElement(device_id=device.id, name=name, element_type=etype)
            )
    db.session.commit()
    return device


@click.command('seed-demo')
@with_appcontext
def seed_demo():
    """Create a default device with placeholder structural elements (idempotent)."""
    before = StructuralElement.query.count()
    device = ensure_default_device()
    created = StructuralElement.query.count() - before
    click.echo(f'Device #{device.id}: {device.name} — {created} element(s) created, '
               f'{len(list(device.elements)) - created} already present.')


@click.command('simulate')
@click.option('--count', default=200, show_default=True, help='Number of samples to generate.')
@click.option('--hours', default=24.0, show_default=True, help='Spread samples over the last N hours.')
@click.option('--seed', 'rng_seed', default=None, type=int, help='RNG seed for reproducible output.')
@with_appcontext
def simulate(count, hours, rng_seed):
    """Generate realistic trending v2 samples (for demos without hardware)."""
    rng = random.Random(rng_seed)
    device = ensure_default_device()
    elements = list(device.elements)
    now = datetime.utcnow()
    span = timedelta(hours=hours)

    # one element develops a slow upward strain drift (a simulated defect)
    drifting = elements[0] if elements else None

    last_sample = None
    for i in range(count):
        frac = i / max(1, count - 1)            # 0 -> 1 across the window
        ts = now - span + span * frac
        temp = 22 + 6 * math.sin(2 * math.pi * frac) + rng.gauss(0, 0.6)
        humidity = 55 + 10 * math.sin(2 * math.pi * frac + 1) + rng.gauss(0, 1.5)
        vibration = max(0, 2.5 + rng.gauss(0, 0.8) + (6 if rng.random() < 0.02 else 0))
        sound = max(0, 42 + rng.gauss(0, 3))
        sample = Sample(
            device_id=device.id, timestamp=ts,
            temperature=round(temp, 2), humidity=round(humidity, 2),
            vibration=round(vibration, 2), sound=round(sound, 2),
        )
        db.session.add(sample)
        db.session.flush()
        for el in elements:
            micro = 120 + rng.gauss(0, 15)
            if el is drifting:
                micro += 380 * frac             # drifts toward ~critical by the end
            db.session.add(StrainMeasurement(
                sample_id=sample.id, element_id=el.id, microstrain=max(0, round(micro, 1)),
            ))
        last_sample = sample

    db.session.flush()
    # evaluate only the most recent sample so alerts/health reflect "now"
    if last_sample is not None:
        evaluate_sample(last_sample)
    db.session.commit()
    drift_name = drifting.name if drifting else 'n/a'
    click.echo(f'Generated {count} samples over {hours}h for device #{device.id} '
               f'({len(elements)} elements). Rising-strain drift on: {drift_name}.')
