from app import app, get_db, ensure_schema
with app.app_context():
    ensure_schema()
    conn = get_db()
    # Suppliers
    suppliers = ["Shalina Healthcare Ke Ltd", "Sunveat Foods", "Krish Commodities (Z)"]
    for name in suppliers:
        conn.execute("INSERT OR IGNORE INTO suppliers(name) VALUES (?)", (name,))
    # Map supplier ids
    sids = {r["name"]: r["id"] for r in conn.execute("SELECT id,name FROM suppliers")}
    # Products
    rows = [
        (sids["Shalina Healthcare Ke Ltd"], "Kaluma King 1x18pk", ""),
        (sids["Shalina Healthcare Ke Ltd"], "Kaluma Balm 4g 1x24x24pkt", ""),
        (sids["Sunveat Foods"], "Funtoys Rings Tomato 30pcsx12gms", ""),
        (sids["Krish Commodities (Z)"], "Basmati Sunrice 5X5Kg Z", ""),
    ]
    for sid, pname, up in rows:
        conn.execute(
            "INSERT INTO products(supplier_id, product_name, unit_pack_info, name) VALUES (?,?,?,?)",
            (sid, pname, up, pname)
        )
    conn.commit()
print("Seeded suppliers & products OK")
