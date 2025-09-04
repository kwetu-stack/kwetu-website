# data/admin_update.py
from pathlib import Path
from datetime import datetime
import sqlite3

from werkzeug.security import generate_password_hash

DB = Path(__file__).resolve().parent / "salespro360.db"
con = sqlite3.connect(DB)
cur = con.cursor()

# --------------------------
# Suppliers to (up)insert
# --------------------------
suppliers_to_add = [
    # Existing four
    "KETEPA TEA PACKERS LTD",
    "Mzuri Sweets Limited",
    "Pwani Oil LTD",
    "Glaxco Smithkline LTD",
    # Additional you provided
    "Haco Industries",
    "Kevian Kenya",
    "Kilimanjaro",
    "Tropical Brands",
    "Kam & Chin",
    "Krystalline",
    "Yemken",
]

# --------------------------
# Rep display names (login -> name)
# Matches your screenshot
# --------------------------
rep_names = {
    "rep1": "Moses",
    "rep2": "Ali",
    "rep3": "Hassan",
    "rep4": "John",
    "rep5": "Eric",
    "rep6": "Abdulkadir",
    "rep7": "Frontoffice",
}

# --- Ensure users table has full_name column (safe to re-run) ---
cur.execute("PRAGMA table_info(users)")
cols = [r[1] for r in cur.fetchall()]
if "full_name" not in cols:
    cur.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
    con.commit()

# --- Create any missing rep users with default password 'rep123' ---
for uname in rep_names.keys():
    cur.execute("SELECT 1 FROM users WHERE username=?", (uname,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES(?,?,?,?)",
            (uname, generate_password_hash("rep123"), "rep", datetime.utcnow().isoformat()),
        )
con.commit()

# --- Set / update display names ---
for uname, full in rep_names.items():
    cur.execute("UPDATE users SET full_name=? WHERE username=?", (full, uname))
con.commit()

# --- Add suppliers (no duplicates) ---
for name in suppliers_to_add:
    cur.execute("INSERT OR IGNORE INTO suppliers(name) VALUES(?)", (name,))
con.commit()

# --- Summary ---
total_suppliers = cur.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0]
print(f"Done. Suppliers total now: {total_suppliers}")
print("Reps:")
for u, fn in cur.execute(
    "SELECT username, COALESCE(full_name,'') FROM users WHERE role='rep' ORDER BY username"
):
    print(f"  {u} → {fn}")

con.close()
