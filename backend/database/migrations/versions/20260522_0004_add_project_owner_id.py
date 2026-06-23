"""add owner_id to projects

Revision ID: 20260522_0004
Revises: 20260520_0003
Create Date: 2026-05-22 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260522_0004"
down_revision = "20260520_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_cols = {col["name"] for col in inspector.get_columns("projects")}
    if "owner_id" not in existing_cols:
        op.add_column("projects", sa.Column("owner_id", sa.String(64), nullable=True))

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("projects")}
    if "ix_projects_owner_id" not in existing_indexes:
        op.create_index("ix_projects_owner_id", "projects", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_projects_owner_id", table_name="projects")
    op.drop_column("projects", "owner_id")
