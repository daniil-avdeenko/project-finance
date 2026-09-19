from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateTimeField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Optional, ValidationError


class LoginForm(FlaskForm):
    username = StringField("Имя пользователя", validators=[DataRequired()])
    password = PasswordField("Пароль", validators=[DataRequired()])
    remember_me = BooleanField("Запомнить меня")
    submit = SubmitField("Войти")


class ProjectForm(FlaskForm):
    name = StringField("Название проекта", validators=[DataRequired()])
    description = TextAreaField("Описание", validators=[Optional()])


class EmployeeForm(FlaskForm):
    name = StringField("ФИО сотрудника", validators=[DataRequired()])
    position = StringField("Должность", validators=[Optional()])
    phone = StringField("Телефон", validators=[Optional()])
    email = StringField("Email", validators=[Optional()])


class IncomeCategoryForm(FlaskForm):
    name = StringField("Название категории дохода", validators=[DataRequired()])


class ExpenseCategoryForm(FlaskForm):
    name = StringField("Название категории расхода", validators=[DataRequired()])


class TransactionForm(FlaskForm):
    type = SelectField(
        "Тип",
        choices=[("income", "Доход"), ("expense", "Расход")],
        validators=[DataRequired()],
    )
    project_id = SelectField("Проект", coerce=int, validators=[DataRequired()])
    category_id = SelectField("Категория", coerce=int, validators=[DataRequired()])
    amount = StringField("Сумма", validators=[DataRequired()])
    currency = SelectField(
        "Валюта", choices=[("RUB", "₽"), ("USD", "$"), ("EUR", "€")], default="RUB"
    )
    description = TextAreaField("Описание", validators=[Optional()])
    date = DateTimeField(
        "Дата и время",
        validators=[Optional()],
        format="%Y-%m-%dT%H:%M",
    )

    def validate_amount(self, field):
        """Очищает строку с суммой, преобразует в float и проверяет > 0"""
        if not field.data:
            raise ValidationError("Сумма не может быть пустой")

        cleaned = str(field.data).replace(" ", "").replace(",", ".")

        try:
            value = float(cleaned)
        except ValueError as err:
            raise ValidationError(
                "Введите корректное число (например, 200000 или 200000.50)"
            ) from err

        if value <= 0:
            raise ValidationError("Сумма должна быть больше 0")

        field.data = value
