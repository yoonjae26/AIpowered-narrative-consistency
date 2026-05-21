"""create narrative tables

Revision ID: 20260520_0002
Revises: 20260520_0001
Create Date: 2026-05-20 00:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260520_0002"
down_revision = "20260520_0001"
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

    if "characters" not in existing_tables:
        op.create_table(
            "characters",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("traits", sa.JSON(), nullable=False),
            sa.Column("goals", sa.JSON(), nullable=False),
            sa.Column("background", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    ensure_index("characters", op.f("ix_characters_name"), ["name"])

    if "scenes" not in existing_tables:
        op.create_table(
            "scenes",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("beats", sa.JSON(), nullable=False),
            sa.Column("characters", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    ensure_index("scenes", op.f("ix_scenes_title"), ["title"])

    if "lore_facts" not in existing_tables:
        op.create_table(
            "lore_facts",
            sa.Column("key", sa.String(length=255), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("source", sa.String(length=255), nullable=True),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("key"),
        )

    if "timeline_events" not in existing_tables:
        op.create_table(
            "timeline_events",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("happened_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    ensure_index("timeline_events", op.f("ix_timeline_events_happened_at"), ["happened_at"])
    ensure_index("timeline_events", op.f("ix_timeline_events_title"), ["title"])

    if "relationships" not in existing_tables:
        op.create_table(
            "relationships",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("target", sa.String(length=64), nullable=False),
            sa.Column("relationship_type", sa.String(length=32), nullable=False),
            sa.Column("strength", sa.Float(), nullable=False),
            sa.Column("notes", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    ensure_index("relationships", op.f("ix_relationships_source"), ["source"])
    ensure_index("relationships", op.f("ix_relationships_target"), ["target"])

    if "canon_entries" not in existing_tables:
        op.create_table(
            "canon_entries",
            sa.Column("key", sa.String(length=255), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("immutable", sa.Boolean(), nullable=False),
            sa.Column("aliases", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("key"),
        )

    if "magic_rules" not in existing_tables:
        op.create_table(
            "magic_rules",
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("cost", sa.String(length=255), nullable=True),
            sa.Column("limitations", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("name"),
        )

    if "arc_progress" not in existing_tables:
        op.create_table(
            "arc_progress",
            sa.Column("character_id", sa.String(length=64), nullable=False),
            sa.Column("milestone", sa.String(length=255), nullable=False),
            sa.Column("progress", sa.Float(), nullable=False),
            sa.Column("notes", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("character_id"),
        )


def downgrade() -> None:
    op.drop_table("arc_progress")
    op.drop_table("magic_rules")
    op.drop_table("canon_entries")

    op.drop_index(op.f("ix_relationships_target"), table_name="relationships")
    op.drop_index(op.f("ix_relationships_source"), table_name="relationships")
    op.drop_table("relationships")

    op.drop_index(op.f("ix_timeline_events_title"), table_name="timeline_events")
    op.drop_index(op.f("ix_timeline_events_happened_at"), table_name="timeline_events")
    op.drop_table("timeline_events")

    op.drop_table("lore_facts")

    op.drop_index(op.f("ix_scenes_title"), table_name="scenes")
    op.drop_table("scenes")

    op.drop_index(op.f("ix_characters_name"), table_name="characters")
    op.drop_table("characters")
