# seed_products.py  (collision-safe)
import sqlite3, csv, sys, io, argparse
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "salespro360.db"

def has_column(conn, table, column):
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(c[1].lower() == column.lower() for c in cols)

def table_exists(conn, name):
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return bool(row)

# ---- same canonicalization as app.py ----
def _canon(text: str) -> str:
    if not text: return ""
    s = text.strip().lower()
    s = s.replace("\u00d7", "x")  # × -> x
    while "  " in s: s = s.replace("  ", " ")
    s = s.replace(" x ", "x").replace(" x", "x").replace("x ", "x")
    s = s.replace("pkt","pk").replace("pkts","pk")
    s = (s.replace(" gms"," g").replace(" gm"," g")
           .replace("gms","g").replace("gm","g"))
    s = s.replace(" kgs"," kg").replace("kgs","kg")
    s = s.replace(" mls"," ml").replace("mls","ml")
    s = s.replace("  "," ")
    if s.endswith(" z"): s = s[:-2] + "z"
    if s.endswith(" v"): s = s[:-2] + "v"
    return s

def _canon_pair(prod_name: str, pack: str) -> str:
    return _canon(f"{(prod_name or '').strip()} {(pack or '').strip()}".strip())

def _ensure_min_schema(conn):
    # non-destructive table creation (same as app)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS suppliers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            product_name TEXT,
            unit_pack_info TEXT,
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE
        )
    """)
    if table_exists(conn, "products"):
        if not has_column(conn, "products", "product_name"):
            conn.execute("ALTER TABLE products ADD COLUMN product_name TEXT")
            if has_column(conn, "products", "name"):
                conn.execute("""
                    UPDATE products
                    SET product_name = COALESCE(product_name, name)
                    WHERE product_name IS NULL OR product_name = ''
                """)
        if not has_column(conn, "products", "unit_pack_info"):
            conn.execute("ALTER TABLE products ADD COLUMN unit_pack_info TEXT")
        if not has_column(conn, "products", "supplier_id"):
            conn.execute("ALTER TABLE products ADD COLUMN supplier_id INTEGER")
    conn.commit()

def _upsert_supplier(conn, supplier_name: str) -> int:
    supplier_name = (supplier_name or "").strip()
    if not supplier_name: return 0
    row = conn.execute("SELECT id FROM suppliers WHERE lower(name)=lower(?)", (supplier_name,)).fetchone()
    if row: return row[0]
    cur = conn.execute("INSERT INTO suppliers(name) VALUES (?)", (supplier_name,))
    return cur.lastrowid

def load_headers(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise SystemExit("CSV appears empty or lacks a header row.")
    headers = {h.lower().strip(): h for h in reader.fieldnames}
    supplier_key = headers.get("supplier") or headers.get("supplier_name")
    pname_key    = headers.get("product_name") or headers.get("product")
    unit_key     = headers.get("unit_pack_info") or headers.get("unit") or headers.get("pack")
    if not supplier_key or not pname_key:
        raise SystemExit("CSV must include 'supplier' and 'product_name' columns.")
    return reader, supplier_key, pname_key, unit_key

def main():
    ap = argparse.ArgumentParser(description="Seed new products into SalesPro360 DB from CSV (collision-safe).")
    ap.add_argument("csv_path", help="CSV with columns: supplier, product_name, [unit_pack_info]")
    ap.add_argument("--dry-run", action="store_true", help="Preview without writing.")
    args = ap.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"DB not found at {DB_PATH}. Run from project root where data/salespro360.db exists.")

    # parse once to learn headers; we re-read below
    _, supplier_key, pname_key, unit_key = load_headers(args.csv_path)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_min_schema(conn)

        existing_by_supplier = {}
        def _load_existing(sid: int):
            if sid in existing_by_supplier: return
            rows = conn.execute(
                "SELECT COALESCE(product_name, name, '') AS n, COALESCE(unit_pack_info,'') AS u FROM products WHERE supplier_id=?",
                (sid,)
            ).fetchall()
            existing_by_supplier[sid] = set(_canon_pair(r["n"], r["u"]) for r in rows)

        # helper: check UNIQUE(supplier_id, name) without changing schema
        def name_exists(sid: int, nm: str) -> bool:
            if not has_column(conn, "products", "name"):
                return False
            r = conn.execute(
                "SELECT 1 FROM products WHERE supplier_id=? AND lower(name)=lower(?) LIMIT 1",
                (sid, nm.strip())
            ).fetchone()
            return bool(r)

        added, skipped, created_suppliers = 0, 0, 0
        # second pass over CSV
        text = Path(args.csv_path).read_text(encoding="utf-8-sig")
        rdr = csv.DictReader(io.StringIO(text))
        for r in rdr:
            supplier_name = (r.get(supplier_key) or "").strip()
            product_name  = (r.get(pname_key) or "").strip()
            unit_pack     = (r.get(unit_key) or "").strip() if unit_key else ""
            if not supplier_name or not product_name:
                skipped += 1
                continue

            # ensure supplier
            row = conn.execute("SELECT id FROM suppliers WHERE lower(name)=lower(?)", (supplier_name,)).fetchone()
            if row:
                sid = row["id"]
            else:
                if args.dry_run:
                    created_suppliers += 1
                    sid = -1  # fake id during dry-run
                else:
                    sid = _upsert_supplier(conn, supplier_name)
                    created_suppliers += 1

            # duplicate check on canonical pair
            if sid != -1:
                _load_existing(sid)
                cand = _canon_pair(product_name, unit_pack)
                if cand in existing_by_supplier[sid]:
                    skipped += 1
                    continue

            if args.dry_run:
                added += 1
                continue

            # build insert safely (respect legacy 'name' uniqueness if column exists)
            cols = ["supplier_id", "product_name", "unit_pack_info"]
            vals = [sid, product_name, (unit_pack or None)]

            if has_column(conn, "products", "name"):
                # smart legacy name: prefer product_name; if collides, try "product_name (pack)"; then suffix #2, #3...
                base = product_name.strip()
                legacy_name = base if base else product_name.strip()
                if name_exists(sid, legacy_name):
                    candidate = (f"{product_name} ({unit_pack})".strip() if unit_pack else product_name.strip())
                    legacy_name = candidate or base
                    i = 2
                    while name_exists(sid, legacy_name):
                        legacy_name = f"{candidate or base} #{i}"
                        i += 1
                cols.append("name")
                vals.append(legacy_name)

            placeholders = ",".join(["?"] * len(vals))
            sql = f"INSERT INTO products({','.join(cols)}) VALUES ({placeholders})"
            conn.execute(sql, vals)

            # update our in-memory set so subsequent rows see the new item
            cand2 = _canon_pair(product_name, unit_pack)
            existing_by_supplier.setdefault(sid, set()).add(cand2)
            added += 1

        if not args.dry_run:
            conn.commit()

        mode = "DRY-RUN" if args.dry_run else "APPLIED"
        print(f"[{mode}] Products to add: {added}, skipped: {skipped}, suppliers created: {created_suppliers}")
        if args.dry_run:
            print("Re-run without --dry-run to apply changes.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
