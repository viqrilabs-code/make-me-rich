"""add preferred llm provider to strategy config

Revision ID: 20260324_0002
Revises: 20260323_0001
Create Date: 2026-03-24 16:10:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260324_0002"
down_revision = "20260323_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("strategy_configs")}
    if "preferred_llm_provider" not in columns:
        op.add_column(
            "strategy_configs",
            sa.Column("preferred_llm_provider", sa.String(length=32), nullable=False, server_default="openai"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("strategy_configs")}
    if "preferred_llm_provider" in columns:
        op.drop_column("strategy_configs", "preferred_llm_provider")
