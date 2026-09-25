"""Record exact ingestion membership; historical backfill is first observation only.

Reacquire old sources before publishing civic-v2 if unchanged rows from their
later runs were never recorded. Historical membership cannot be reconstructed
by treating every record from a source as belonging to every run.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    from openpali.storage.models import AcquisitionRecord
    bind = op.get_bind()
    AcquisitionRecord.__table__.create(bind, checkfirst=True)
    bind.execute(sa.text("ALTER TABLE civic.snapshot_property_state ADD COLUMN IF NOT EXISTS frozen_identity JSONB NOT NULL DEFAULT '{}'::jsonb"))
    bind.execute(sa.text("""
        INSERT INTO source.acquisition_record (acquisition_run_id, record_version_id)
        SELECT acquisition_run_id, record_version_id FROM source.source_record_version
        ON CONFLICT DO NOTHING
    """))


def downgrade():
    op.drop_column("snapshot_property_state", "frozen_identity", schema="civic")
    op.drop_table("acquisition_record", schema="source")
