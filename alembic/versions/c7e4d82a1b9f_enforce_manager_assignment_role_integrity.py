"""enforce_manager_assignment_role_integrity

Revision ID: c7e4d82a1b9f
Revises: 36094e551167
Create Date: 2026-10-31 21:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e4d82a1b9f'
down_revision: Union[str, Sequence[str], None] = '36094e551167'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enforce relational role constraints on manager_tenant_assignments."""
    # 1. Unique constraint on users (id, role) to support composite foreign key
    op.create_unique_constraint(
        'uq_users_id_role',
        'users',
        ['id', 'role'],
    )

    # 2. Add user_role column to manager_tenant_assignments with default 'store_manager'
    op.add_column(
        'manager_tenant_assignments',
        sa.Column(
            'user_role',
            sa.String(length=50),
            server_default='store_manager',
            nullable=False,
        ),
    )

    # 3. Check constraint ensuring user_role is always 'store_manager'
    op.create_check_constraint(
        'ck_manager_tenant_assignments_role_is_manager',
        'manager_tenant_assignments',
        "user_role = 'store_manager'",
    )

    # 4. Composite foreign key guaranteeing that only users with role='store_manager' receive assignments
    op.create_foreign_key(
        'fk_manager_tenant_assignments_user_role',
        'manager_tenant_assignments',
        'users',
        ['user_id', 'user_role'],
        ['id', 'role'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    """Revert relational role constraints."""
    op.drop_constraint(
        'fk_manager_tenant_assignments_user_role',
        'manager_tenant_assignments',
        type_='foreignkey',
    )
    op.drop_constraint(
        'ck_manager_tenant_assignments_role_is_manager',
        'manager_tenant_assignments',
        type_='check',
    )
    op.drop_column('manager_tenant_assignments', 'user_role')
    op.drop_constraint('uq_users_id_role', 'users', type_='unique')
