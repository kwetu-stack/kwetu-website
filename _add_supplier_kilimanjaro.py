import sqlite3
DB = r"data/salespro360.db"
conn = sqlite3.connect(DB); cur = conn.cursor()
cur.execute("PRAGMA foreign_keys = ON")
cur.execute("INSERT OR IGNORE INTO suppliers (id, name) VALUES (?, ?)", (1124, "Kilimanjaro"))
conn.commit()
print(cur.execute("SELECT id,name FROM suppliers WHERE id=1124").fetchone())
conn.close()
