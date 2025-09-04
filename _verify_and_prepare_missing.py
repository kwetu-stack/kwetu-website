import sqlite3, csv
from pathlib import Path

EXPECTED = [
    "Kreams Gold Chocolate 60x2",
    "Kreams Gold Chocolate 72pkt x 13 7g",
    "Kreams Gold Strawberry 60x2",
    "Kreams Gold Straberry 72pk x 13 7g",
    "Kreams Gold Vanilla 60x2",
    "Kreams Gold Vanilla 72pkt x 13 7g",
    "Milk Power 300pc Loose",
    "Milk Power 72x5",
    "Milk Power Choco 300pcs",
    "Milk Power Choco 72pcx5",
    "Nice 300pcs Loose",
]

conn = sqlite3.connect(r"data/salespro360.db"); cur = conn.cursor()
rows = [r[0] for r in cur.execute(
    "SELECT name FROM products WHERE supplier_id=1124 ORDER BY name"
).fetchall()]

print("DB has", len(rows), "products for supplier 1124:")
for i, name in enumerate(rows, 1):
    print(f"{i:02d}. {name}")

missing = [n for n in EXPECTED if n not in rows]
print("\nMissing:", len(missing))
for n in missing:
    print(" -", n)

# If any are missing, write a tiny CSV to import
if missing:
    out = Path("data/kili_missing.csv")
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["supplier_name","product_name","unit_pack_info"])
        for name in missing:
            w.writerow(["Kilimanjaro", name, ""])
    print("\nWrote:", out.resolve())
conn.close()
