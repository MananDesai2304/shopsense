"""Create the products table for the WANDS catalog.

Revision ID: 0001
Revises:
Create Date: 2026-11-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        # WANDS supplies the ids, so no sequence.
        sa.Column("product_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("product_class", sa.Text, nullable=True),
        sa.Column("category_hierarchy", sa.Text, nullable=True),
        sa.Column("category_path", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("features_raw", sa.Text, nullable=False),
        sa.Column(
            "features",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("rating_count", sa.Integer, nullable=True),
        # Real values are 1.0 to 5.0 in half steps, always one decimal place.
        sa.Column("average_rating", sa.Numeric(2, 1), nullable=True),
        sa.Column("review_count", sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("products")
