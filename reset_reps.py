# reset_reps.py
import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

DB = Path("data") / "salespro360.db"

# Final list of reps (edit here if you need to change names/usernames)
REPS = [
    {"username": "rep1", "full_name": "Ali Mzamssa",        "password": "123456"},
    {"username": "rep2", "full_name": "Hassan Mzamssa",     "password": "123456"},
    {"username": "rep3", "full_name": "Eric Mzamssa",       "password": "123456"},
    {"username": "rep4", "full_name": "John Mzamssa",       "password": "123456"},
    {"username": "rep5", "full_name": "Moses Mzamssa",      "password": "123456"},
    {"username": "rep6", "full_name": "Abdulkadir Mzamssa", "password": "123456"},
    {"username": "rep7", "full_name": "Frontdesk Mzamssa",  "password": "123456"},
]

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# 1) Remove any existing reps (but do NOT touch admins)
conn.execute("DELETE FROM users WHERE role='rep'")

# 2) Insert the 7 reps fresh
for r in REPS:
    conn.execute(
        "INSERT INTO users(username, password_hash, role, full_name, created_at) "
        "VALUES (?,?,?,?,datetime('now'))",
        (r["username"], generate_password_hash(r["password"]), "rep", r["full_name"])
    )

conn.commit()

# 3) Show the newly assigned rep IDs so you can use them in CSVs
rows = conn.execute(
    "SELECT id, username, full_name FROM users WHERE role='rep' ORDER BY id"
).fetchall()
conn.close()

print("✅ Re-seeded reps:")
for r in rows:
    print(f"{r['id']:>3}  {r['username']:<6}  {r['full_name']}")
