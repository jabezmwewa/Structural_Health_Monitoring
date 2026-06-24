"""v2 alert lifecycle + health/sample links

Revision ID: 2dec8a0b870b
Revises: 08757dba0030
Create Date: 2026-06-24 07:09:52.755757

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2dec8a0b870b'
down_revision = '08757dba0030'
branch_labels = None
depends_on = None

# Names the existing unnamed FKs during the SQLite batch table rebuild.
naming_convention = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def upgrade():
    with op.batch_alter_table('alerts', schema=None,
                              naming_convention=naming_convention) as batch_op:
        batch_op.add_column(sa.Column('device_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('element_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('sample_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_value', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('last_seen', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('resolved_at', sa.DateTime(), nullable=True))
        batch_op.alter_column('reading_id', existing_type=sa.INTEGER(), nullable=True)
        batch_op.create_foreign_key(
            'fk_alerts_sample_id_samples', 'samples', ['sample_id'], ['id'])
        batch_op.create_foreign_key(
            'fk_alerts_device_id_devices', 'devices', ['device_id'], ['id'])
        batch_op.create_foreign_key(
            'fk_alerts_element_id_structural_elements',
            'structural_elements', ['element_id'], ['id'])

    with op.batch_alter_table('health_scores', schema=None,
                              naming_convention=naming_convention) as batch_op:
        batch_op.add_column(sa.Column('sample_id', sa.Integer(), nullable=True))
        batch_op.alter_column('reading_id', existing_type=sa.INTEGER(), nullable=True)
        batch_op.create_foreign_key(
            'fk_health_scores_sample_id_samples', 'samples', ['sample_id'], ['id'])


def downgrade():
    with op.batch_alter_table('health_scores', schema=None,
                              naming_convention=naming_convention) as batch_op:
        batch_op.drop_constraint('fk_health_scores_sample_id_samples', type_='foreignkey')
        batch_op.alter_column('reading_id', existing_type=sa.INTEGER(), nullable=False)
        batch_op.drop_column('sample_id')

    with op.batch_alter_table('alerts', schema=None,
                              naming_convention=naming_convention) as batch_op:
        batch_op.drop_constraint('fk_alerts_element_id_structural_elements', type_='foreignkey')
        batch_op.drop_constraint('fk_alerts_device_id_devices', type_='foreignkey')
        batch_op.drop_constraint('fk_alerts_sample_id_samples', type_='foreignkey')
        batch_op.alter_column('reading_id', existing_type=sa.INTEGER(), nullable=False)
        batch_op.drop_column('resolved_at')
        batch_op.drop_column('last_seen')
        batch_op.drop_column('last_value')
        batch_op.drop_column('sample_id')
        batch_op.drop_column('element_id')
        batch_op.drop_column('device_id')
