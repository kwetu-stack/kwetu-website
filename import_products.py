# import_products.py
import csv
import sqlite3
from pathlib import Path
import sys

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "salespro360.db"

def ensure_tables(conn):
    # Create suppliers/products if they don't already exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS suppliers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            unit_pack_info TEXT,
            UNIQUE(supplier_id, name)
        )
    """)
    conn.commit()

def get_or_create_supplier(conn, name: str) -> int:
    row = conn.execute("SELECT id FROM suppliers WHERE name=?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO suppliers(name) VALUES(?)", (name,))
    conn.commit()
    return cur.lastrowid

def upsert_product(conn, supplier_id: int, name: str, unit_pack: str):
    # Try find product
    row = conn.execute(
        "SELECT id, unit_pack_info FROM products WHERE supplier_id=? AND name=?",
        (supplier_id, name)
    ).fetchone()
    if row:
        if (row["unit_pack_info"] or "") != (unit_pack or ""):
            conn.execute(
                "UPDATE products SET unit_pack_info=? WHERE id=?",
                (unit_pack, row["id"])
            )
            return "updated"
        return "skipped"
    conn.execute(
        "INSERT INTO products(supplier_id, name, unit_pack_info) VALUES(?,?,?)",
        (supplier_id, name, unit_pack)
    )
    return "inserted"

def main(csv_path: Path):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_tables(conn)

    inserted = updated = skipped = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"supplier_name", "product_name", "unit_pack_info"}
        if set(h.strip() for h in reader.fieldnames or []) != required:
            print("❌ CSV must have EXACT headers: supplier_name,product_name,unit_pack_info")
            return

        for r in reader:
            supplier = (r["supplier_name"] or "").strip()
            product  = (r["product_name"] or "").strip()
            packinfo = (r["unit_pack_info"] or "").strip()

            if not supplier or not product:
                continue

            sid = get_or_create_supplier(conn, supplier)
            res = upsert_product(conn, sid, product, packinfo)
            if res == "inserted":
                inserted += 1
            elif res == "updated":
                updated += 1
            else:
                skipped += 1

    conn.commit()
    conn.close()
    print(f"✅ Done. Inserted: {inserted}, Updated: {updated}, Skipped: {skipped}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_products.py suppliers_products_clean.csv")
        sys.exit(1)
    csv_file = Path(sys.argv[1])
    if not csv_file.exists():
        print(f"❌ File not found: {csv_file}")
        sys.exit(1)
    main(csv_file)
