"""add task_records table

Revision ID: d0eafc46e5cc
Revises: 71ea7229814a
Create Date: 2026-07-29 22:17:51.351806
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd0eafc46e5cc'
down_revision: Union[str, None] = '71ea7229814a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Only create task_records — other tables already exist
    op.create_table('task_records',
        sa.Column('task_type', sa.String(64), nullable=False),
        sa.Column('task_key', sa.String(256), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='pending'),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='core',
    )
    op.create_index(op.f('ix_core_task_records_id'), 'task_records', ['id'], unique=False, schema='core')
    op.create_index(op.f('ix_core_task_records_status'), 'task_records', ['status'], unique=False, schema='core')
    op.create_index(op.f('ix_core_task_records_task_key'), 'task_records', ['task_key'], unique=False, schema='core')
    op.create_index(op.f('ix_core_task_records_task_type'), 'task_records', ['task_type'], unique=False, schema='core')


def downgrade() -> None:
    op.drop_index(op.f('ix_core_task_records_task_type'), table_name='task_records', schema='core')
    op.drop_index(op.f('ix_core_task_records_task_key'), table_name='task_records', schema='core')
    op.drop_index(op.f('ix_core_task_records_status'), table_name='task_records', schema='core')
    op.drop_index(op.f('ix_core_task_records_id'), table_name='task_records', schema='core')
    op.drop_table('task_records', schema='core')
