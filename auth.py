from __future__ import annotations

import os

from flask_login import LoginManager, UserMixin
from werkzeug.security import check_password_hash

ADMIN_ID = "admin"

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Connectez-vous pour effectuer cette action."
login_manager.login_message_category = "warning"


class AdminUser(UserMixin):
    """Single in-memory admin account — credentials come from the environment.

    No `users` table: the app only ever needs one admin account (see project
    decision), so Flask-Login's user_loader just re-hands out this singleton.
    """

    id = ADMIN_ID

    def __init__(self, username: str) -> None:
        self.username = username


def _load_admin_username() -> str:
    return os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"


ADMIN_USER = AdminUser(_load_admin_username())


@login_manager.user_loader
def load_user(user_id: str) -> AdminUser | None:
    if user_id == ADMIN_USER.id:
        return ADMIN_USER
    return None


def verify_credentials(username: str, password: str) -> bool:
    expected_username = _load_admin_username()
    password_hash = os.getenv("ADMIN_PASSWORD_HASH", "")

    if not password_hash:
        return False
    if not username or username.strip() != expected_username:
        return False

    return check_password_hash(password_hash, password)
