# seed_reps.py
import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

DB = Path("data") / "salespro360.db"

# 👇 Edit these 7 entries to match your reps (usernames are unique)
REPS = [
    {"username": "rep1", "ali_mzamssa": "Rep One",   "password": "123456"},
    {"username": "rep2", "hassan_mzamssa": "Rep Two",   "password": "123456"},
    {"username": "rep3", "eric_mzamssa": "Rep Three", "password": "123456"},
    {"username": "rep4", "john_mzamssa": "Rep Four",  "password": "123456"},
    {"username": "rep5", "moses_mzamssa": "Rep Five",  "password": "123456"},
    {"username": "rep6", "abdulkadir_mzamssa": "Rep Six",   "password": "123456"},
    {"username": "rep7", "frontdesk_mzamssa": "Rep Seven", "password": "123456"},
]

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

added = 0
for r in REPS:
    exists = conn.execute("SELECT 1 FROM users WHERE username=?", (r["username"],)).fetchone()
    if exists:
        continue
    conn.execute(
        "INSERT INTO users(username, password_hash, role, full_name, created_at) "
        "VALUES (?,?,?,?,datetime('now'))",
        (r["username"], generate_password_hash(r["password"]), "rep", r["full_name"]),
    )
    added += 1

conn.commit()
conn.close()
print(f"✅ Added {added} rep user(s).")
