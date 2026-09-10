"""add memory confidence and source

Revision ID: 4055081d1825
Revises: 1b967171e52e
Create Date: 2026-09-10 02:39:38.221072

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4055081d1825"
down_revision: Union[str, Sequence[str], None] = "1b967171e52e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "memories",
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default="1.0",
        ),
    )

    op.add_column(
        "memories",
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            server_default="user",
        ),
    )

    op.alter_column(
        "memories",
        "confidence",
        server_default=None,
    )

    op.alter_column(
        "memories",
        "source",
        server_default=None,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("memories", "source")
    op.drop_column("memories", "confidence")