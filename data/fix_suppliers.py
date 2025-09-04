# data/fix_suppliers.py
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("salespro360.db")

# ---- Canonical merge map ----------------------------------------------------
# Each item: one "good" (canonical) supplier name and a list of variants that
# should be merged into it. Add more variants here any time you spot them.
MERGES = [
    # Previously requested
    {
        "good": "Haco Industries Ltd",
        "bad_variants": [
            "Haco Industries", "Haco Industries Limited", "Haco Industies",
            "Haco Indusries", "Haco Ind.", "Haco Ind", "Haco Industries LTD",
        ],
    },
    {
        "good": "Krystalline Salt Limited",
        "bad_variants": [
            "Krystalline", "Krystalline Salt", "Krystalline Salt LTD",
            "Krystaline Salt", "Krystaline", "Krystalline Salt Ltd",
        ],
    },

    # New cleanups based on your DB screenshot & uploads
    {
        "good": "Glaxo SmithKline Ltd",
        "bad_variants": [
            "Glaxco Smithkline LTD", "Glaxco Smithkline Ltd", "Glaxco Smithkline",
            "Glaxo Smithkline", "Glaxo Smith Kline", "Glaxo SmithKline",
            "Glaxo SmithKline LTD", "GSK",
        ],
    },
    {
        "good": "Kevian Kenya",
        "bad_variants": ["Kevian", "Kevian Kenya Ltd", "Kevian Kenya Limited"],
    },
    {
        "good": "Kam & Chin",
        "bad_variants": ["Kam & Chin Trading", "Kam and Chin", "KAM & CHIN", "Kam & Chin Trading Ltd"],
    },
    {
        "good": "Pwani Oil Ltd",
        "bad_variants": [
            "Pwani Oil LTD", "Pwani Oil", "Pwani Oil (V)",
            # Uncomment the next line only if you *do* want to fold this into the same vendor
            # "Pwani Tfk (V)",
        ],
    },
    {
        "good": "KETEPA TEA PACKERS LTD",
        "bad_variants": [
            "KETEPA", "KETEPA TEA PACKERS", "KETEPA TEA PACKERS LIMITED",
            "Kenya Tea Packers", "KETEPA PACKERS LTD",
        ],
    },
    {
        "good": "Tropical Brands",
        "bad_variants": [
            "Tropical Brands (Africa)", "Tropical Brands Africa", "Tropical Brands Africa Ltd",
            "Tropical Brands (A)",
        ],
    },
    {
        "good": "Yemken",
        "bad_variants": ["Yemkem", "Yemkem Trading", "Yemken Trading"],
    },
]

# ---- Helpers ----------------------------------------------------------------

def _norm(s: str) -> str:
    """Normalize a supplier name for comparison (case/space/trim tolerant)."""
    if s is None:
        return ""
    s = " ".join(str(s).split())          # collapse internal whitespace
    s = s.strip()
    return s.lower()

def find_supplier_by_normalized(cur, target_name):
    """Find supplier row by normalized name (case/space tolerant)."""
    tnorm = _norm(target_name)
    for sid, name in cur.execute("SELECT id, name FROM suppliers"):
        if _norm(name) == tnorm:
            return sid, name
    return None

def ensure_good_supplier(cur, good_name):
    row = find_supplier_by_normalized(cur, good_name)
    if row:
        return row[0]
    cur.execute("INSERT INTO suppliers(name) VALUES(?)", (good_name,))
    return cur.lastrowid

def merge_one(cur, good_name, bad_name):
    bad = find_supplier_by_normalized(cur, bad_name)
    if not bad:
        return {"bad_found": False, "moved": 0, "deleted": False, "renamed": False}

    bad_id, bad_db_name = bad
    good = find_supplier_by_normalized(cur, good_name)

    if not good:
        # Simple rename if the "good" row doesn't exist yet
        cur.execute("UPDATE suppliers SET name = ? WHERE id = ?", (good_name, bad_id))
        return {"bad_found": True, "moved": 0, "deleted": False, "renamed": True}

    good_id, _ = good
    if good_id == bad_id:
        return {"bad_found": True, "moved": 0, "deleted": False, "renamed": False}

    # Re-link products from bad supplier to good supplier
    cur.execute("UPDATE products SET supplier_id = ? WHERE supplier_id = ?", (good_id, bad_id))
    moved = cur.rowcount or 0

    # Delete the now-empty bad supplier row
    cur.execute("DELETE FROM suppliers WHERE id = ?", (bad_id,))
    return {"bad_found": True, "moved": moved, "deleted": True, "renamed": False}

def supplier_counts(cur):
    return cur.execute("""
        SELECT s.name, COUNT(p.id) AS product_count
        FROM suppliers s
        LEFT JOIN products p ON p.supplier_id = s.id
        GROUP BY s.id
        ORDER BY UPPER(s.name)
    """).fetchall()

# ---- Main -------------------------------------------------------------------

def main():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()

    print("Before merge (supplier -> product count):")
    for name, cnt in supplier_counts(cur):
        print(f"  {name} -> {cnt}")

    total_moved = total_deleted = total_renamed = checked = 0

    for merge in MERGES:
        good = " ".join(merge["good"].split()).strip()
        ensure_good_supplier(cur, good)
        for bad in merge["bad_variants"]:
            res = merge_one(cur, good, bad)
            checked += 1
            if res["bad_found"]:
                total_moved += res["moved"]
                total_deleted += 1 if res["deleted"] else 0
                total_renamed += 1 if res["renamed"] else 0

    con.commit()

    print("\n=== Fix complete ===")
    print(f"Checked variant pairs: {checked}")
    print(f"Products re-linked:    {total_moved}")
    print(f"Bad suppliers deleted: {total_deleted}")
    print(f"Rows renamed:          {total_renamed}")

    print("\nAfter merge (supplier -> product count):")
    for name, cnt in supplier_counts(cur):
        print(f"  {name} -> {cnt}")

    con.close()

if __name__ == "__main__":
    main()
