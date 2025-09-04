# seed.py
from app import app, db
from app.models import Supplier, Product  # adjust to your actual model names
import csv

def run_seed_safe():
    # --- Seed Suppliers ---
    suppliers = [
        {"id": 1116, "name": "Kilimanjaro Distributors Ltd"},
        {"id": 1117, "name": "Garisa Traders"},
        {"id": 1118, "name": "Mombasa Wholesalers"},
    ]
    for s in suppliers:
        exists = Supplier.query.get(s["id"])
        if not exists:
            db.session.add(Supplier(id=s["id"], name=s["name"]))

    # --- Seed Products from CSV ---
    # assumes you committed a clean CSV, e.g. "products_sample.csv"
    with open("products_sample.csv", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # adjust column names to match your CSV
            product_name = row["Item"]
            supplier_id = int(row["SupplierID"])
            buying_price = float(row["BuyingPrice"])
            selling_price = float(row["SellingPrice"])

            exists = Product.query.filter_by(name=product_name, supplier_id=supplier_id).first()
            if not exists:
                db.session.add(
                    Product(
                        name=product_name,
                        supplier_id=supplier_id,
                        buying_price=buying_price,
                        selling_price=selling_price,
                    )
                )

    db.session.commit()
    print("✅ Suppliers and Products seeded safely.")
