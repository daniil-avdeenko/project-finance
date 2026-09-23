"""backfill is_deleted for orphaned transactions
Одноразовая уборка: помечает удалёнными транзакции, чьи проекты
уже is_deleted=True. До каскадного soft delete такие транзакции
оставались активными и учитывались в расчётах дашборда.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "3342af4e19d8"
down_revision = "0b97c8f23ba9"
branch_labels = None
depends_on = None


def upgrade():
    """Помечает удалёнными транзакции удалённых проектов."""
    connection = op.get_bind()
    result = connection.execute(
        sa.text(
            """
            UPDATE transactions
            SET is_deleted = true
            WHERE project_id IN (
                SELECT id FROM projects WHERE is_deleted = true
            )
            AND is_deleted = false
            """
        )
    )
    print(f"  → Обновлено транзакций: {result.rowcount}")


def downgrade():
    """
    Не откатываем: невозможно отличить транзакции, попавшие в backfill,
    от тех, что были помечены удалёнными вручную.
    """
    pass
