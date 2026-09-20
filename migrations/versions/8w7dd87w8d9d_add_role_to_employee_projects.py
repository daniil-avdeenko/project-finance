"""add role to employee_projects and drop employees.position
"""
import sqlalchemy as sa
from alembic import op

revision = '0b97c8f23ba9'
down_revision = "d26b35a32a78"
branch_labels = None
depends_on = None


def upgrade():
    # Дропаем старую M2M-таблицу, создаём association object с role.
    # Данные теряются — для pet-проекта с seed.py это допустимо.
    op.drop_table("employee_projects")
    op.create_table(
        "employee_projects",
        sa.Column("employee_id", sa.Integer, nullable=False),
        sa.Column("project_id", sa.Integer, nullable=False),
        sa.Column("role", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("employee_id", "project_id"),
    )

    # Удаляем position из employees
    with op.batch_alter_table("employees") as batch_op:
        batch_op.drop_column("position")


def downgrade():
    with op.batch_alter_table("employees") as batch_op:
        batch_op.add_column(sa.Column("position", sa.String(100), nullable=True))

    op.drop_table("employee_projects")
    op.create_table(
        "employee_projects",
        sa.Column("employee_id", sa.Integer, nullable=False),
        sa.Column("project_id", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("employee_id", "project_id"),
    )
