"""create baseline tables users/projects

Revision ID: 20260520_0001
Revises:
Create Date: 2026-05-20 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260520_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    def ensure_index(table_name: str, index_name: str, columns: list[str]) -> None:
        existing_indexes = {item["name"] for item in inspector.get_indexes(table_name)}
        if index_name not in existing_indexes:
            op.create_index(index_name, table_name, columns, unique=False)

    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("username", sa.String(length=64), nullable=False),
            sa.Column("email", sa.String(length=320), nullable=True),
            sa.Column("display_name", sa.String(length=200), nullable=True),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    ensure_index("users", op.f("ix_users_username"), ["username"])

    if "projects" not in existing_tables:
        op.create_table(
            "projects",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    ensure_index("projects", op.f("ix_projects_title"), ["title"])

def downgrade() -> None:
    op.drop_index(op.f("ix_projects_title"), table_name="projects")
    op.drop_table("projects")

    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")