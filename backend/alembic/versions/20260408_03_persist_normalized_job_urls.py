"""persist normalized job urls on sightings

Revision ID: 20260408_03
Revises: 20260403_02
Create Date: 2026-04-08 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.domains.jobs.deduplication import normalize_url


# revision identifiers, used by Alembic.
revision: str = "20260408_03"
down_revision: Union[str, Sequence[str], None] = "20260403_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = {column["name"] for column in inspector.get_columns("job_sightings")}
    indexes = {index["name"] for index in inspector.get_indexes("job_sightings")}

    if "normalized_url" not in columns:
        op.add_column(
            "job_sightings",
            sa.Column("normalized_url", sa.String(length=500), nullable=False, server_default=""),
        )

    if "ix_job_sightings_normalized_url" not in indexes:
        op.create_index("ix_job_sightings_normalized_url", "job_sightings", ["normalized_url"], unique=False)

    rows = connection.execute(
        sa.text("SELECT id, listing_url, apply_url FROM job_sightings")
    ).fetchall()
    for row in rows:
        normalized_url = normalize_url(row.apply_url or row.listing_url)
        connection.execute(
            sa.text(
                "UPDATE job_sightings SET normalized_url = :normalized_url WHERE id = :id"
            ),
            {"id": row.id, "normalized_url": normalized_url},
        )


def downgrade() -> None:
    op.drop_index("ix_job_sightings_normalized_url", table_name="job_sightings")
    op.drop_column("job_sightings", "normalized_url")
