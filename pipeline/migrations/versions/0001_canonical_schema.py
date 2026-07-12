"""Canonical OpenPali schema: source, civic, analytics, ml, spatial, ops.

Revision ID: 0001
Revises:
Create Date: 2026-07-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))
    from openpali.storage.models import SCHEMAS, Base

    for schema in SCHEMAS:
        bind.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    Base.metadata.create_all(bind=bind)
    # Seed the singleton current-release authority row.
    bind.execute(sa.text(
        "INSERT INTO ops.current_release (id, current_release_id, lkg_release_id, created_at, updated_at) "
        "VALUES (1, NULL, NULL, now(), now()) ON CONFLICT (id) DO NOTHING"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    from openpali.storage.models import SCHEMAS, Base

    Base.metadata.drop_all(bind=bind)
    for schema in SCHEMAS:
        bind.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
