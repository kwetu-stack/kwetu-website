# export_suppliers.py
import sqlite3
import csv
from pathlib import Path

DB_PATH = Path("data") / "salespro360.db"
OUT_PATH = Path("data") / "suppliers_list.csv"

def export_suppliers():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT id, name FROM suppliers ORDER BY id")
    rows = cur.fetchall()

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["supplier_id", "name"])  # header
        for r in rows:
            writer.writerow([r["id"], r["name"]])

    print(f"✅ Exported {len(rows)} suppliers to {OUT_PATH}")

if __name__ == "__main__":
    export_suppliers()
