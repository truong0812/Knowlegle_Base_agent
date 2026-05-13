"""Sample Python source for parser testing."""

import os
from typing import Optional


class UserService:
    """Manages user accounts."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def create_user(self, name: str, email: str) -> dict:
        """Create a new user and return user dict."""
        user = {"name": name, "email": email}
        self._save(user)
        return user

    def get_user(self, email: str) -> Optional[dict]:
        """Look up user by email."""
        return None

    def _save(self, user: dict) -> None:
        pass


def validate_email(email: str) -> bool:
    """Check if email format is valid."""
    return "@" in email


def format_user_display(user: dict) -> str:
    return f"{user['name']} <{user['email']}>"
