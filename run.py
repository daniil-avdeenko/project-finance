from app import create_app, db
from app.models import Employee, ExpenseCategory, IncomeCategory, Project, Transaction

app = create_app()


@app.shell_context_processor
def make_shell_context():
    return {
        "db": db,
        "Project": Project,
        "Employee": Employee,
        "IncomeCategory": IncomeCategory,
        "ExpenseCategory": ExpenseCategory,
        "Transaction": Transaction,
    }


if __name__ == "__main__":
    app.run(debug=True)
