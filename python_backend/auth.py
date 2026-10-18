
import sqlite3
import re
import os
from flask import session, send_from_directory
from flask_session import Session
from datetime import timedelta


from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash

# Store the user database inside python_backend.
DATABASE_PATH = Path(__file__).resolve().parent / "users.db"


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    """Create the users table if it does not exist."""
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


def register_user(username, email, password):
    """Validate details and create a new user account."""
    if not all(isinstance(value, str) for value in
               (username, email, password)):
        return False, "All fields are required."

    username = username.strip()
    email = email.strip().lower()

    if not username or not email or not password:
        return False, "All fields are required."

    if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
        return False, (
            "Username must be 3–30 characters and contain only "
            "letters, numbers or underscores."
        )

    if len(email) > 254 or not re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+", email
    ):
        return False, "Enter a valid email address."

    if len(password) < 8:
        return False, "Password must contain at least 8 characters."

    if len(password) > 1024:
        return False, "Password is too long."

    password_hash = generate_password_hash(password)

    try:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
                """,
                (username, email, password_hash)
            )
        return True, "Account created successfully."

    except sqlite3.IntegrityError:
        return False, "Username or email is already registered."


def authenticate_user(username_or_email, password):
    """Verify credentials without exposing the stored password."""
    if not isinstance(username_or_email, str) or not isinstance(
        password, str
    ):
        return None

    identifier = username_or_email.strip()

    if not identifier or not password:
        return None

    with get_connection() as connection:
        user = connection.execute(
            """
            SELECT id, username, email, password_hash
            FROM users
            WHERE username = ? COLLATE NOCASE
               OR email = ? COLLATE NOCASE
            """,
            (identifier, identifier)
        ).fetchone()

    if user and check_password_hash(user["password_hash"], password):
        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"]
        }

    return None
