"""production hardening

Revision ID: f3b97a2108b4
Revises: e2a87be9f906
Create Date: 2026-09-22 16:33:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3b97a2108b4"
down_revision: str | Sequence[str] | None = "e2a87be9f906"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "programs",
        sa.Column("decision_mode", sa.String(length=32), server_default="automatic", nullable=False),
    )
    op.create_unique_constraint("uq_programs_policy_version_rank", "programs", ["policy_version_id", "rank"])

    op.add_column("policy_rules", sa.Column("source_document", sa.String(length=300), nullable=True))
    op.add_column("policy_rules", sa.Column("source_quote", sa.Text(), nullable=True))
    op.add_column("policy_rules", sa.Column("source_page", sa.Integer(), nullable=True))

    op.add_column(
        "lender_match_results",
        sa.Column("decision", sa.String(length=32), server_default="ineligible", nullable=False),
    )

    op.alter_column(
        "criterion_results",
        "outcome",
        existing_type=sa.String(length=10),
        type_=sa.String(length=20),
        existing_nullable=False,
    )

    op.create_index(
        "uq_active_underwriting_run_per_application",
        "underwriting_runs",
        ["application_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_active_underwriting_run_per_application",
        table_name="underwriting_runs",
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.alter_column(
        "criterion_results",
        "outcome",
        existing_type=sa.String(length=20),
        type_=sa.String(length=10),
        existing_nullable=False,
    )
    op.drop_column("lender_match_results", "decision")
    op.drop_column("policy_rules", "source_page")
    op.drop_column("policy_rules", "source_quote")
    op.drop_column("policy_rules", "source_document")
    op.drop_constraint("uq_programs_policy_version_rank", "programs", type_="unique")
    op.drop_column("programs", "decision_mode")
