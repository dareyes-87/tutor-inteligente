"""actividad leccion_id y fragmentos_fuente_ids

Revision ID: a2a93c93a5e9
Revises: 4858c23833e7
Create Date: 2026-10-28 18:10:39.781516
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a2a93c93a5e9'
down_revision: Union[str, None] = '4858c23833e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('actividad', sa.Column('leccion_id', sa.Integer(), nullable=True))
    op.add_column('actividad', sa.Column('fragmentos_fuente_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index(op.f('ix_actividad_leccion_id'), 'actividad', ['leccion_id'], unique=False)
    op.create_foreign_key('fk_actividad_leccion_id', 'actividad', 'leccion', ['leccion_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_actividad_leccion_id', 'actividad', type_='foreignkey')
    op.drop_index(op.f('ix_actividad_leccion_id'), table_name='actividad')
    op.drop_column('actividad', 'fragmentos_fuente_ids')
    op.drop_column('actividad', 'leccion_id')
