"""
Authentication module — SQLite-backed users with bcrypt password hashing.
Stores: email, password_hash, is_premium, is_admin, created_at, last_login.
"""
import os
import sqlite3
import bcrypt
from datetime import datetime
from contextlib import contextmanager

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "users.db")


def _ensure_db_dir():
    os.makedirs(DB_DIR, exist_ok=True)


@contextmanager
def get_conn():
    _ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create users + scrape_log tables if they don't exist."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                email           TEXT UNIQUE NOT NULL,
                password_hash   TEXT NOT NULL,
                is_premium      INTEGER NOT NULL DEFAULT 0,
                is_admin        INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL,
                last_login      TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scrape_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                keyword     TEXT NOT NULL,
                city        TEXT NOT NULL,
                rows_found  INTEGER NOT NULL,
                created_at  TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def register_user(email: str, password: str, is_premium: bool = False, is_admin: bool = False):
    """Create a new user. Returns (success, message)."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return False, "Please enter a valid email address."
    if not password or len(password) < 6:
        return False, "Password must be at least 6 characters."

    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO users (email, password_hash, is_premium, is_admin, created_at) VALUES (?, ?, ?, ?, ?)",
                (email, _hash_password(password), int(is_premium), int(is_admin), datetime.utcnow().isoformat()),
            )
        return True, "Account created. Please log in."
    except sqlite3.IntegrityError:
        return False, "An account with that email already exists."
    except Exception as e:
        return False, f"Could not create account: {e}"


def authenticate(email: str, password: str):
    """Return user dict on success, None on failure."""
    email = (email or "").strip().lower()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row:
            return None
        if not _verify_password(password, row["password_hash"]):
            return None
        conn.execute("UPDATE users SET last_login = ? WHERE id = ?",
                     (datetime.utcnow().isoformat(), row["id"]))
        return dict(row)


def get_user(user_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def list_users():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, email, is_premium, is_admin, created_at, last_login FROM users ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_user_by_email(email: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", ((email or "").strip().lower(),)).fetchone()
        return dict(row) if row else None


def set_premium(user_id, is_premium):
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_premium = ? WHERE id = ?", (int(is_premium), user_id))


def set_admin(user_id, is_admin):
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (int(is_admin), user_id))


def delete_user(user_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM scrape_log WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def change_password(user_id, new_password):
    if not new_password or len(new_password) < 6:
        return False, "Password must be at least 6 characters."
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (_hash_password(new_password), user_id))
    return True, "Password updated."


def log_scrape(user_id, keyword, city, rows_found):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO scrape_log (user_id, keyword, city, rows_found, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, keyword, city, rows_found, datetime.utcnow().isoformat()),
        )


def list_scrape_log(limit=100):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT s.id, u.email, s.keyword, s.city, s.rows_found, s.created_at
            FROM scrape_log s
            JOIN users u ON u.id = s.user_id
            ORDER BY s.created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def _read_secret(key: str) -> str:
    """Read from OS env first, then Streamlit secrets. Returns '' if missing."""
    val = os.getenv(key, "").strip()
    if val:
        return val
    try:
        import streamlit as st  # type: ignore
        return (st.secrets.get(key, "") or "").strip()
    except Exception:
        return ""


def bootstrap_admin_from_env() -> str:
    """
    Idempotent admin bootstrap. Runs on every launch.
    - If no users exist and ADMIN_EMAIL/ADMIN_PASSWORD are set, create the admin.
    - If the admin email exists but isn't admin/premium, elevate it.
    Returns a short status message (for logs).
    """
    email = _read_secret("ADMIN_EMAIL").lower()
    password = _read_secret("ADMIN_PASSWORD")
    if not email or not password:
        return "no ADMIN_EMAIL/ADMIN_PASSWORD set — skipping bootstrap"

    existing = get_user_by_email(email)
    if existing is None:
        ok, msg = register_user(email, password, is_premium=True, is_admin=True)
        return f"admin bootstrap: {msg}"
    # already exists — make sure flags are right, but do NOT overwrite password
    if not existing["is_admin"] or not existing["is_premium"]:
        set_admin(existing["id"], True)
        set_premium(existing["id"], True)
        return "admin bootstrap: promoted existing account to admin+premium"
    return "admin bootstrap: already provisioned"
