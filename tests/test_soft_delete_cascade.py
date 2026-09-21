"""Тесты каскадного soft delete и консистентности дашборда."""

from datetime import UTC, datetime

from app import db as _db
from app.models import IncomeCategory, Project, Transaction


def test_project_soft_delete_cascades_to_transactions(app):
    """При soft delete проекта его транзакции тоже помечаются."""
    with app.app_context():
        project = Project(name="P")
        cat = IncomeCategory(name="I")
        _db.session.add_all([project, cat])
        _db.session.commit()

        _db.session.add(
            Transaction(
                project_id=project.id,
                type="income",
                category_id=cat.id,
                amount=1000,
                currency="RUB",
                date=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )
        _db.session.add(
            Transaction(
                project_id=project.id,
                type="expense",
                category_id=cat.id,
                amount=500,
                currency="RUB",
                date=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )
        _db.session.commit()
        project_id = project.id

        # Soft delete проекта
        project.is_deleted = True
        _db.session.commit()

    with app.app_context():
        # Все транзакции проекта удалены каскадно
        active = Transaction.active().filter_by(project_id=project_id).all()
        assert len(active) == 0

        all_tx = Transaction.query.filter_by(project_id=project_id).all()
        assert len(all_tx) == 2
        assert all(t.is_deleted for t in all_tx)


def test_cascade_does_not_touch_other_projects(app):
    """Каскад удаляет транзакции только удаляемого проекта."""
    with app.app_context():
        p1 = Project(name="P1")
        p2 = Project(name="P2")
        cat = IncomeCategory(name="I")
        _db.session.add_all([p1, p2, cat])
        _db.session.commit()

        _db.session.add(
            Transaction(
                project_id=p1.id,
                type="income",
                category_id=cat.id,
                amount=1000,
                date=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )
        _db.session.add(
            Transaction(
                project_id=p2.id,
                type="income",
                category_id=cat.id,
                amount=2000,
                date=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )
        p1.is_deleted = True
        _db.session.commit()

        # Сохраняем ID до выхода из сессии
        p2_id = p2.id

    with app.app_context():
        # У P2 транзакция всё ещё активна
        active_p2 = Transaction.active().filter_by(project_id=p2_id).all()
        assert len(active_p2) == 1


def test_cascade_idempotent(app):
    """Повторное сохранение удалённого проекта не ломает каскад."""
    with app.app_context():
        project = Project(name="P", is_deleted=True)
        cat = IncomeCategory(name="I")
        _db.session.add_all([project, cat])
        _db.session.commit()

        _db.session.add(
            Transaction(
                project_id=project.id,
                type="income",
                category_id=cat.id,
                amount=1000,
                date=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )
        _db.session.commit()

        # Транзакция добавлена после удаления проекта — она активна.
        # Сохраняем проект снова — каскад сработает
        project.description = "обновление"
        _db.session.commit()

        project_id = project.id

    with app.app_context():
        active = Transaction.active().filter_by(project_id=project_id).all()
        assert len(active) == 0
