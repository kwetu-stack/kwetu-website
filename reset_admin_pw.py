# reset_admin_pw.py
import sys
import getpass
import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

DB_PATH = Path("data") / "salespro360.db"

def set_admin_password(username: str, new_password: str):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    pw_hash = generate_password_hash(new_password)

    # ensure table exists just in case
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','rep')),
            created_at TEXT,
            full_name TEXT
        )
    """)

    cur.execute("SELECT id FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE users SET password_hash=?, role='admin' WHERE id=?",
            (pw_hash, row["id"])
        )
        msg = f"✅ Updated password for existing admin '{username}'."
    else:
        cur.execute(
            "INSERT INTO users(username, password_hash, role, created_at) "
            "VALUES (?,?, 'admin', datetime('now'))",
            (username, pw_hash)
        )
        msg = f"✅ Created new admin user '{username}'."

    conn.commit()
    conn.close()
    print(msg)

if __name__ == "__main__":
    username = sys.argv[1] if len(sys.argv) > 1 else "admin"
    if len(sys.argv) > 2:
        password = sys.argv[2]
    else:
        password = getpass.getpass(f"New password for {username}: ")

    set_admin_password(username, password)
