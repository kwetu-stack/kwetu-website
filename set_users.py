import sqlite3, datetime
from pathlib import Path

DB = Path(__file__).parent / "data" / "salespro360.db"

def hash_pw(pw: str) -> str:
    try:
        # Use Werkzeug if available (same as the app)
        from werkzeug.security import generate_password_hash
        return generate_password_hash(pw)  # pbkdf2:sha256
    except Exception:
        # Fallback for our two known passwords if Werkzeug isn't importable
        fixed = {
            "admin123": "pbkdf2:sha256:1000000$yvblkXbjIby778VE$f5a67b6f18915a8d98577268b0510c2b75874511717795e467655b4b808d7c26",
            "staff123": "pbkdf2:sha256:1000000$z6SH3wzv5FS0Zgse$5b15484be27577f5f250b0d8fd500f66932730e989085018d97eff3a8f25f607",
        }
        return fixed[pw]

def upsert_user(cur, username, plain_pw, role, full_name=None):
    cur.execute("""
    INSERT INTO users (username, password_hash, role, created_at, full_name)
    VALUES (?,?,?,?,?)
    ON CONFLICT(username) DO UPDATE SET
      password_hash = excluded.password_hash,
      role          = excluded.role,
      full_name     = COALESCE(excluded.full_name, users.full_name)
    """, (
        username,
        hash_pw(plain_pw),
        role,
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        full_name,
    ))

def main():
    con = sqlite3.connect(str(DB))
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()

    # Safety: ensure users table exists
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

    upsert_user(cur, "admin", "admin123", "admin", "Admin")
    upsert_user(cur, "staff", "staff123", "rep",   "Everyone")

    # OPTIONAL: uncomment to keep only admin/staff
    # cur.execute("DELETE FROM users WHERE username NOT IN ('admin','staff')")

    con.commit()

    rows = cur.execute("SELECT id, username, role FROM users ORDER BY id").fetchall()
    con.close()
    print("Users now in DB:")
    for r in rows:
        print(r)
    print("\nLogin with admin/admin123 or staff/staff123")

if __name__ == "__main__":
    main()
