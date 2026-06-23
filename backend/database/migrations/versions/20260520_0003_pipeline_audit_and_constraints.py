"""pipeline audit and constraints

Revision ID: 20260520_0003
Revises: 20260520_0002
Create Date: 2026-06-03 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260520_0003"
down_revision = "20260520_0002"
branch_labels = None
depends_on = None


LEGACY_ROLE_MAP = {
    "hero": "protagonist",
    "main": "protagonist",
    "lead": "protagonist",
    "villain": "antagonist",
    "enemy": "antagonist",
    "support": "supporting",
    "supporter": "supporting",
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "characters" in existing_tables:
        for legacy_role, canonical_role in LEGACY_ROLE_MAP.items():
            op.execute(
                sa.text(
                    "UPDATE characters SET role = :canonical_role WHERE lower(role) = :legacy_role"
                ).bindparams(canonical_role=canonical_role, legacy_role=legacy_role)
            )
        op.execute(
            sa.text(
                "UPDATE characters SET role = 'supporting' WHERE role IS NULL OR trim(role) = ''"
            )
        )
        op.execute(
            sa.text(
                "UPDATE characters SET role = 'supporting' WHERE lower(trim(role)) NOT IN ('protagonist', 'antagonist', 'supporting', 'extra')"
            )
        )
        with op.batch_alter_table("characters") as batch_op:
            batch_op.create_check_constraint(
                "ck_characters_role",
                "role IN ('protagonist', 'antagonist', 'supporting', 'extra')",
            )
            batch_op.create_check_constraint(
                "ck_characters_status",
                "status IN ('active', 'alive', 'dead', 'injured', 'absent', 'unknown')",
            )

    if "relationships" in existing_tables:
        with op.batch_alter_table("relationships") as batch_op:
            batch_op.create_foreign_key(
                "fk_relationships_source_characters",
                "characters",
                ["source"],
                ["id"],
                ondelete="CASCADE",
            )
            batch_op.create_foreign_key(
                "fk_relationships_target_characters",
                "characters",
                ["target"],
                ["id"],
                ondelete="CASCADE",
            )
            batch_op.create_check_constraint(
                "ck_relationships_strength",
                "strength >= 0.0 AND strength <= 1.0",
            )

    if "arc_progress" in existing_tables:
        with op.batch_alter_table("arc_progress") as batch_op:
            batch_op.create_foreign_key(
                "fk_arc_progress_character",
                "characters",
                ["character_id"],
                ["id"],
                ondelete="CASCADE",
            )

    if "pipeline_audit_trails" not in existing_tables:
        op.create_table(
            "pipeline_audit_trails",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("scene_id", sa.String(length=64), nullable=True),
            sa.Column("scene_title", sa.String(length=255), nullable=True),
            sa.Column("branch", sa.String(length=64), nullable=False),
            sa.Column("decision", sa.String(length=32), nullable=False),
            sa.Column("rejected_before_persist", sa.Boolean(), nullable=False),
            sa.Column("scene_hash", sa.String(length=128), nullable=True),
            sa.Column("gate", sa.JSON(), nullable=False),
            sa.Column("reasoning", sa.JSON(), nullable=False),
            sa.Column("verification", sa.JSON(), nullable=False),
            sa.Column("replay_verification", sa.JSON(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        with op.batch_alter_table("arc_progress") as batch_op:
            batch_op.drop_constraint("fk_arc_progress_character", type_="foreignkey")

        with op.batch_alter_table("relationships") as batch_op:
            batch_op.drop_constraint("ck_relationships_strength", type_="check")
            batch_op.drop_constraint("fk_relationships_target_characters", type_="foreignkey")
            batch_op.drop_constraint("fk_relationships_source_characters", type_="foreignkey")

        with op.batch_alter_table("characters") as batch_op:
            batch_op.drop_constraint("ck_characters_status", type_="check")
            batch_op.drop_constraint("ck_characters_role", type_="check")

    op.drop_table("pipeline_audit_trails")
