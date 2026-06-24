"""
Custom Flask CLI commands.

Run with:  flask <command>   (FLASK_APP=run.py)
"""

import click
from flask.cli import with_appcontext

from app import db
from app.models import Device, StructuralElement

# Placeholder rig layout — rename/extend to match the real structure, or seed
# your own elements. Each tuple is (element name, element type).
DEFAULT_ELEMENTS = [
    ('Column A', 'column'),
    ('Column B', 'column'),
    ('Slab 1',   'slab'),
]


@click.command('seed-demo')
@with_appcontext
def seed_demo():
    """Create a default device with placeholder structural elements (idempotent)."""
    device = Device.query.first()
    if device is None:
        device = Device(name='SHM Node 1', location='Unspecified')
        db.session.add(device)
        db.session.flush()
        click.echo(f'Created device #{device.id}: {device.name}')
    else:
        click.echo(f'Using existing device #{device.id}: {device.name}')

    existing = {e.name for e in device.elements}
    created = 0
    for name, etype in DEFAULT_ELEMENTS:
        if name not in existing:
            db.session.add(
                StructuralElement(device_id=device.id, name=name, element_type=etype)
            )
            created += 1
    db.session.commit()
    click.echo(f'Elements: {created} created, {len(existing)} already present.')
