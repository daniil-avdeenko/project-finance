from urllib.parse import urljoin, urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.forms import LoginForm
from app.models import User

auth_bp = Blueprint("auth", __name__, template_folder="../templates")


def is_safe_url(target):
    """
    Проверяет, является ли URL безопасным для редиректа.
    Защита от Open Redirect уязвимости.
    """
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Страница входа. При успешной аутентификации перенаправляет на главную
    или на переданный параметр `next` (только безопасный URL).
    """
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash("Неверное имя пользователя или пароль", "danger")
            return redirect(url_for("auth.login"))

        login_user(user, remember=form.remember_me.data)

        # Проверка безопасности перед редиректом
        next_page = request.args.get("next")
        if next_page and is_safe_url(next_page):
            return redirect(next_page)
        return redirect(url_for("main.index"))

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    """
    Выход из системы. Перенаправляет на страницу входа.
    """
    logout_user()
    flash("Вы вышли из системы", "info")
    return redirect(url_for("auth.login"))
