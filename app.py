import os
import csv
import io
import json
import sqlite3
from datetime import datetime, date
from pathlib import Path
from flask import (
    Flask, render_template, request, redirect, url_for, session,
    flash, send_file, g, abort, make_response
)
from werkzeug.security import generate_password_hash, check_password_hash

# ======================= App / DB config =======================
BASE_DIR = Path(__file__).parent

def _resolve_sqlite_path():
    """
    Resolve SQLite file path from env (DATABASE_URL) or fallback:
      - If DATABASE_URL=sqlite:///relative/or/file.db -> relative to BASE_DIR
      - If DATABASE_URL=sqlite:////absolute/path.db   -> absolute path
      - If DATABASE_URL ends with .db (plain path)    -> use as given
      - Else fallback to /data/salespro360demo.db if /data exists, otherwise ./data/salespro360demo.db
    """
    env_url = (os.getenv("DATABASE_URL") or "").strip()
    if env_url:
        # Absolute path: sqlite:////abs/path.db
        if env_url.startswith("sqlite:////"):
            return env_url.replace("sqlite:////", "/")
        # Relative path: sqlite:///relative.db
        if env_url.startswith("sqlite:///"):
            rel = env_url.replace("sqlite:///", "")
            if rel.startswith("/"):
                return rel  # treat as absolute if user supplied a leading slash
            return str((BASE_DIR / rel).resolve())
        # Plain filesystem path ending with .db
        if env_url.lower().endswith(".db"):
            return env_url

    # Fallbacks
    if os.path.exists("/data"):  # Render persistent disk
        return "/data/salespro360demo.db"
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(exist_ok=True)
    return str((data_dir / "salespro360demo.db").resolve())

DB_FILE = _resolve_sqlite_path()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-salespro360")
app.config["DATABASE"] = DB_FILE

# ======================= DB helpers =======================
def get_db():
    if "db" not in g:
        # ensure parent dir exists (local)
        try:
            Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        conn = sqlite3.connect(app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db

@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return bool(row)

def has_column(conn, table: str, column: str) -> bool:
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(c["name"].lower() == column.lower() for c in cols)

# ======================= Schema =======================
def ensure_schema():
    """
    Creates/migrates all tables without destroying data.
    """
    conn = get_db()

    # users
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','rep')),
            created_at TEXT,
            full_name TEXT
        )
    """)

    # suppliers
    conn.execute("""
        CREATE TABLE IF NOT EXISTS suppliers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)

    # products (canonical)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            product_name TEXT,
            unit_pack_info TEXT,
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE
        )
    """)
    # legacy safety: ensure 'name' exists
    if not has_column(conn, "products", "name"):
        conn.execute("ALTER TABLE products ADD COLUMN name TEXT")

    # Soft migrations for legacy shapes
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

    # orders
    if not table_exists(conn, "orders"):
        conn.execute("""
            CREATE TABLE orders(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                total REAL
            )
        """)
    if not has_column(conn, "orders", "created_at"):
        conn.execute("ALTER TABLE orders ADD COLUMN created_at TEXT")
    if not has_column(conn, "orders", "total"):
        conn.execute("ALTER TABLE orders ADD COLUMN total REAL")
    for col, typ in [
        ("supplier_id", "INTEGER"),
        ("product_id",  "INTEGER"),
        ("quantity",    "INTEGER"),
        ("notes",       "TEXT"),
    ]:
        if not has_column(conn, "orders", col):
            conn.execute(f"ALTER TABLE orders ADD COLUMN {col} {typ}")

    if not has_column(conn, "orders", "order_no"):
        conn.execute("ALTER TABLE orders ADD COLUMN order_no TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_order_no ON orders(order_no)")
    if not has_column(conn, "orders", "unit_price"):
        conn.execute("ALTER TABLE orders ADD COLUMN unit_price REAL")
    if not has_column(conn, "orders", "payment_method"):
        conn.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT")
    if not has_column(conn, "orders", "status"):
        conn.execute("ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'Pending'")
    if not has_column(conn, "orders", "delivery_date"):
        conn.execute("ALTER TABLE orders ADD COLUMN delivery_date TEXT")
    if not has_column(conn, "orders", "currency"):
        conn.execute("ALTER TABLE orders ADD COLUMN currency TEXT DEFAULT 'KES'")
    if not has_column(conn, "orders", "customer_name"):
        conn.execute("ALTER TABLE orders ADD COLUMN customer_name TEXT")
    if not has_column(conn, "orders", "customer_location"):
        conn.execute("ALTER TABLE orders ADD COLUMN customer_location TEXT")
    if not has_column(conn, "orders", "line_items"):
        conn.execute("ALTER TABLE orders ADD COLUMN line_items TEXT")
    if not has_column(conn, "orders", "sales_rep_name"):
        conn.execute("ALTER TABLE orders ADD COLUMN sales_rep_name TEXT")

    # targets + actuals
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rep_targets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rep_id INTEGER NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            target_value REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS supplier_targets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            target_value REAL NOT NULL
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_supplier_targets_unique ON supplier_targets(supplier_id, month, year)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_rep_targets_unique ON rep_targets(rep_id, month, year)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS supplier_actuals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            mtd_value REAL NOT NULL DEFAULT 0,
            UNIQUE(supplier_id, month, year)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rep_actuals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rep_id INTEGER NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            mtd_value REAL NOT NULL DEFAULT 0,
            UNIQUE(rep_id, month, year)
        )
    """)

    conn.commit()

    # seed users
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not conn.execute("SELECT 1 FROM users WHERE username='admin'").fetchone():
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at, full_name) VALUES (?,?,?,?,?)",
            ("admin", generate_password_hash("admin123"), "admin", now_ts, "Administrator"),
        )
        conn.commit()
    if not conn.execute("SELECT 1 FROM users WHERE username='staff'").fetchone():
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at, full_name) VALUES (?,?,?,?,?)",
            ("staff", generate_password_hash("staff123"), "rep", now_ts, "Staff"),
        )
        conn.commit()

# Initialize schema in hosted envs
if os.getenv("RENDER", "").lower() == "true":
    with app.app_context():
        ensure_schema()

# ======================= Auth helpers =======================
def current_user_row():
    uid = session.get("user_id")
    if not uid:
        return None
    return get_db().execute(
        "SELECT id, username, role, COALESCE(full_name, username) AS display_name FROM users WHERE id=?",
        (uid,),
    ).fetchone()

def login_required(view):
    def wrapper(*a, **kw):
        if not current_user_row():
            flash("Please login to continue.", "info")
            return redirect(url_for("login"))
        return view(*a, **kw)
    wrapper.__name__ = view.__name__
    return wrapper

def admin_required(view):
    def wrapper(*a, **kw):
        u = current_user_row()
        if not u:
            flash("Please login to continue.", "info")
            return redirect(url_for("login"))
        if u["role"] != "admin":
            abort(403)
        return view(*a, **kw)
    wrapper.__name__ = view.__name__
    return wrapper

@app.context_processor
def inject_flags():
    u = current_user_row()
    return {
        "current_user": u["display_name"] if u else None,
        "is_admin": (u["role"] == "admin") if u else False,
        "date": date,
    }

# ======================= Core pages =======================
@app.route("/")
def root():
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    ensure_schema()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        row = get_db().execute(
            "SELECT * FROM users WHERE username=?",
            (username,),
        ).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            session["user_id"] = row["id"]
            flash("Welcome back.", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.", "error")
    return render_template("login.html")

@app.route("/logout", endpoint="logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))

def _orders_rep_col(conn):
    if has_column(conn, "orders", "rep_id"):
        return "rep_id"
    if has_column(conn, "orders", "sales_rep_id"):
        return "sales_rep_id"
    return None

# ======================= Dashboard =======================
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()

    orders_count = conn.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"]
    suppliers_count = conn.execute("SELECT COUNT(*) AS c FROM suppliers").fetchone()["c"]

    today = date.today()
    m, y = today.month, today.year

    s_mtd = conn.execute(
        "SELECT COALESCE(SUM(mtd_value),0) AS v FROM supplier_actuals WHERE month=? AND year=?",
        (m, y)
    ).fetchone()["v"] or 0.0
    r_mtd = conn.execute(
        "SELECT COALESCE(SUM(mtd_value),0) AS v FROM rep_actuals WHERE month=? AND year=?",
        (m, y)
    ).fetchone()["v"] or 0.0

    supplier_target_total = conn.execute(
        "SELECT COALESCE(SUM(target_value),0) AS t FROM supplier_targets WHERE month=? AND year=?",
        (m, y),
    ).fetchone()["t"] or 0.0
    rep_target_total = conn.execute(
        "SELECT COALESCE(SUM(target_value),0) AS t FROM rep_targets WHERE month=? AND year=?",
        (m, y),
    ).fetchone()["t"] or 0.0

    supplier_progress = (float(s_mtd) / float(supplier_target_total) * 100.0) if supplier_target_total > 0 else 0.0
    rep_progress = (float(r_mtd) / float(rep_target_total) * 100.0) if rep_target_total > 0 else 0.0

    supplier_remaining = max(supplier_target_total - s_mtd, 0.0)
    rep_remaining = max(rep_target_total - r_mtd, 0.0)

    return render_template(
        "dashboard.html",
        orders_count=int(orders_count),
        suppliers_count=int(suppliers_count),
        mtd_sales=float(s_mtd),
        month=m,
        year=y,
        supplier_target_total=float(supplier_target_total),
        rep_target_total=float(rep_target_total),
        supplier_progress=float(supplier_progress),
        rep_progress=float(rep_progress),
        supplier_mtd=float(s_mtd),
        rep_mtd=float(r_mtd),
        supplier_remaining=float(supplier_remaining),
        rep_remaining=float(rep_remaining),
    )

# =============== Shared helpers ===============
def generate_order_no(conn) -> str:
    today_iso = date.today().strftime("%Y-%m-%d")
    seq = conn.execute(
        "SELECT COUNT(*) AS c FROM orders WHERE date(created_at)=?",
        (today_iso,),
    ).fetchone()["c"] + 1
    return f"ORD-{date.today().strftime('%Y%m%d')}-{seq:04d}"

def _orders_where_and_params(args):
    wh, ps = [], []
    q = (args.get("q") or "").strip()
    if q:
        wh.append("(o.order_no LIKE ? OR EXISTS (SELECT 1 FROM suppliers s WHERE s.id=o.supplier_id AND s.name LIKE ?))")
        like = f"%{q}%"
        ps += [like, like]
    status = (args.get("status") or "").strip()
    if status:
        wh.append("o.status = ?")
        ps.append(status)
    supplier_id = args.get("supplier_id", type=int)
    if supplier_id:
        wh.append("o.supplier_id = ?")
        ps.append(supplier_id)
    dt_from = (args.get("from") or "").strip()
    if dt_from:
        wh.append("date(o.created_at) >= date(?)")
        ps.append(dt_from)
    dt_to = (args.get("to") or "").strip()
    if dt_to:
        wh.append("date(o.created_at) <= date(?)")
        ps.append(dt_to)
    return ("WHERE " + " AND ".join(wh)) if wh else "", ps

# ======================= API: products for order form =======================
@app.get("/api/products")
@login_required
def api_products():
    sid = request.args.get("supplier_id", type=int)
    conn = get_db()

    if sid:
        rows = conn.execute(
            """
            SELECT id, supplier_id,
                   COALESCE(product_name, name, '') AS pname,
                   COALESCE(unit_pack_info,'') AS up
            FROM products
            WHERE supplier_id = ?
            ORDER BY pname
            """,
            (sid,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, supplier_id,
                   COALESCE(product_name, name, '') AS pname,
                   COALESCE(unit_pack_info,'') AS up
            FROM products
            ORDER BY pname
            """
        ).fetchall()

    def label(r):
        nm = r["pname"] or ""
        up = r["up"] or ""
        return (nm + (f" ({up})" if up else "")).strip()

    products = [
        {
            "id": r["id"],
            "supplier_id": r["supplier_id"],
            "product_name": r["pname"],
            "label": label(r),
            "name": label(r),
            "text": label(r),
        }
        for r in rows
    ]
    return {"products": products}

# ======================= Products: list & uploads =======================
def _canon(text: str) -> str:
    """
    Canonicalize strings for duplicate detection.
    - lowercase
    - replace × with x
    - collapse spaces
    - remove spaces around 'x' (1 x 48 -> 1x48)
    - normalize units: pkt/pkts -> pk, g/gm/gms -> g, kgs -> kg, mls -> ml
    - remove spaces before trailing Z or V (e.g., '500gm Z' -> '500gmZ')
    """
    if not text:
        return ""
    s = text.strip().lower()
    s = s.replace("\u00d7", "x")  # ×
    while "  " in s:
        s = s.replace("  ", " ")
    s = s.replace(" x ", "x").replace(" x", "x").replace("x ", "x")
    s = s.replace("pkt", "pk").replace("pkts", "pk")
    s = s.replace(" gms", " g").replace(" gm", " g").replace("gms", "g").replace("gm", "g")
    s = s.replace(" kgs", " kg").replace("kgs", "kg")
    s = s.replace(" mls", " ml").replace("mls", "ml")
    s = s.replace("  ", " ")
    if s.endswith(" z"):
        s = s[:-2] + "z"
    if s.endswith(" v"):
        s = s[:-2] + "v"
    return s

def _canon_pair(prod_name: str, pack: str) -> str:
    merged = f"{prod_name or ''} {pack or ''}".strip()
    return _canon(merged)

def _upsert_supplier(conn, supplier_name: str) -> int:
    supplier_name = (supplier_name or "").strip()
    if not supplier_name:
        return 0
    row = conn.execute("SELECT id FROM suppliers WHERE lower(name)=lower(?)", (supplier_name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO suppliers(name) VALUES (?)", (supplier_name,))
    return cur.lastrowid

@app.get("/products", endpoint="products_list")
@login_required
def products_list():
    conn = get_db()
    q = (request.args.get("q") or "").strip()
    supplier_id = request.args.get("supplier_id", type=int)

    where, ps = [], []
    if q:
        where.append("(lower(p.product_name) LIKE lower(?) OR lower(COALESCE(p.unit_pack_info,'')) LIKE lower(?))")
        like = f"%{q}%"
        ps += [like, like]
    if supplier_id:
        where.append("p.supplier_id = ?")
        ps.append(supplier_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    products = conn.execute(f"""
        SELECT p.id,
               COALESCE(p.product_name, p.name, '') AS product_name,
               COALESCE(p.unit_pack_info, '') AS unit_pack_info,
               s.name AS supplier_name,
               p.supplier_id
        FROM products p
        JOIN suppliers s ON s.id = p.supplier_id
        {where_sql}
        ORDER BY s.name, p.product_name
        """, ps).fetchall()

    suppliers = conn.execute("SELECT id, name FROM suppliers ORDER BY name").fetchall()
    return render_template("products.html", products=products, suppliers=suppliers)

@app.post("/products/upload", endpoint="products_upload")
@admin_required
def products_upload():
    """
    CSV columns accepted:
      - supplier / supplier_name
      - product_name
      - unit_pack_info (or 'unit'/'pack') [optional]
    Duplicate detection is by canonicalized (product_name + unit_pack_info) within the same supplier.
    """
    file = request.files.get("file")
    if not file or not file.filename.lower().endswith(".csv"):
        flash("Upload CSV with columns: supplier, product_name, unit_pack_info (last one optional)", "error")
        return redirect(request.referrer or url_for("products_list"))

    text = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        flash("CSV appears empty or has no header row.", "error")
        return redirect(request.referrer or url_for("products_list"))

    headers = {h.lower().strip(): h for h in reader.fieldnames}
    supplier_key = headers.get("supplier") or headers.get("supplier_name")
    pname_key    = headers.get("product_name") or headers.get("product")
    unit_key     = headers.get("unit_pack_info") or headers.get("unit") or headers.get("pack")

    if not supplier_key or not pname_key:
        flash("CSV must include at least 'supplier' and 'product_name' columns.", "error")
        return redirect(request.referrer or url_for("products_list"))

    conn = get_db()

    existing_by_supplier = {}

    def _load_existing(sid: int):
        if sid in existing_by_supplier:
            return
        rows = conn.execute(
            "SELECT COALESCE(product_name, name, '') AS n, COALESCE(unit_pack_info,'') AS u FROM products WHERE supplier_id=?",
            (sid,)
        ).fetchall()
        existing_by_supplier[sid] = set(_canon_pair(r["n"], r["u"]) for r in rows)

    added, skipped = 0, 0
    for r in reader:
        supplier_name = (r.get(supplier_key) or "").strip()
        product_name  = (r.get(pname_key) or "").strip()
        unit_pack     = (r.get(unit_key) or "").strip() if unit_key else ""

        if not supplier_name or not product_name:
            skipped += 1
            continue

        sid = _upsert_supplier(conn, supplier_name)
        if sid <= 0:
            skipped += 1
            continue

        _load_existing(sid)
        cand = _canon_pair(product_name, unit_pack)
        if cand in existing_by_supplier[sid]:
            skipped += 1
            continue

        has_legacy_name = has_column(conn, "products", "name")
        cols = ["supplier_id", "product_name", "unit_pack_info"]
        vals = [sid, product_name, (unit_pack or None)]
        if has_legacy_name:
            cols.append("name")
            vals.append(product_name)
        placeholders = ",".join(["?"] * len(vals))
        sql = f"INSERT INTO products({','.join(cols)}) VALUES ({placeholders})"
        conn.execute(sql, vals)

        existing_by_supplier[sid].add(cand)
        added += 1

    conn.commit()
    flash(f"Products uploaded: {added} (skipped {skipped})", "success")
    return redirect(request.referrer or url_for("products_list"))

@app.get("/products/sample", endpoint="download_products_sample")
@admin_required
def download_products_sample():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["supplier", "product_name", "unit_pack_info"])
    w.writerow(["Shalina Healthcare Ke Ltd", "Kaluma King 1x18pk", ""])
    w.writerow(["Shalina Healthcare Ke Ltd", "Kaluma Balm 4g 1x24x24pkt", ""])
    w.writerow(["Shalina Healthcare Ke Ltd", "Sonamoja Tab 1X48", ""])
    w.writerow(["Krish Commodities (Z)", "Basmati Sunrice 5X5Kg Z", ""])
    w.writerow(["Sunveat Foods", "Funtoys Rings Tomato 30pcsx12gms", ""])
    mem = io.BytesIO(out.getvalue().encode("utf-8"))
    mem.seek(0)
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name="products_sample.csv")

# ======================= Orders =======================
@app.route("/orders/new", methods=["GET", "POST"], endpoint="orders_new")
@login_required
def orders_new():
    conn = get_db()

    if request.method == "POST":
        customer_name     = (request.form.get("customer_name") or "").strip()
        customer_location = (request.form.get("customer_location") or "").strip()
        notes             = (request.form.get("notes") or (request.form.get("comments") or "")).strip()
        payment_method    = (request.form.get("payment_method") or "").strip() or "COD"
        delivery_date     = (request.form.get("delivery_date") or "").strip() or None
        currency          = (request.form.get("currency") or "").strip() or "KES"
        sales_rep_text    = (request.form.get("sales_rep") or "").strip()

        supplier_ids_arr  = request.form.getlist("supplier_id[]")
        product_ids_arr   = request.form.getlist("product_id[]")
        qtys_arr          = request.form.getlist("qty[]")
        prices_arr        = request.form.getlist("unit_price[]")
        amts_arr          = request.form.getlist("line_amount[]")
        descs_arr         = request.form.getlist("desc[]")

        try:
            amount_in = request.form.get("amount")
            manual_total = float(amount_in) if amount_in not in (None, "",) else 0.0
        except ValueError:
            manual_total = 0.0

        pids_needed = [int(pid) for pid in product_ids_arr if (pid or "").strip().isdigit()]
        supplier_by_pid = {}
        if pids_needed:
            rows = conn.execute(
                f"SELECT id, supplier_id FROM products WHERE id IN ({','.join(['?']*len(set(pids_needed)))})",
                tuple(set(pids_needed))
            ).fetchall()
            supplier_by_pid = {r["id"]: r["supplier_id"] for r in rows}

        lines = []
        for i in range(len(product_ids_arr)):
            pid_raw = product_ids_arr[i] if i < len(product_ids_arr) else ""
            sid_raw = supplier_ids_arr[i] if i < len(supplier_ids_arr) else ""
            qty_raw = qtys_arr[i] if i < len(qtys_arr) else ""
            prc_raw = prices_arr[i] if i < len(prices_arr) else ""
            amt_raw = amts_arr[i] if i < len(amts_arr) else ""
            dsc_raw = descs_arr[i] if i < len(descs_arr) else ""

            try:
                pid_i = int(pid_raw) if pid_raw else 0
                sid_i = int(sid_raw) if (sid_raw or "").strip().isdigit() else 0
                if sid_i <= 0 and pid_i in supplier_by_pid:
                    sid_i = int(supplier_by_pid.get(pid_i, 0))
                q_i   = int(float(qty_raw or 0))
                pr_f  = float(prc_raw or 0)
                am_f  = float(amt_raw or 0)
            except ValueError:
                continue

            if pid_i <= 0 or q_i <= 0:
                continue
            if am_f <= 0 and pr_f > 0:
                am_f = round(pr_f * q_i, 2)

            lines.append({
                "supplier_id": sid_i,
                "product_id": pid_i,
                "qty": q_i,
                "unit_price": pr_f,
                "amount": am_f,
                "desc": dsc_raw or None
            })

        if not lines:
            flash("Add at least one item.", "error")
            return redirect(url_for("orders_new"))

        computed_total = round(sum(l["amount"] for l in lines), 2)
        total_to_save = manual_total if manual_total > 0 else computed_total

        first = lines[0]
        header_supplier_id = first.get("supplier_id") or None
        header_product_id  = first.get("product_id")
        header_quantity    = first.get("qty")
        header_unit_price  = first.get("unit_price")

        order_no = generate_order_no(conn)

        has_sales_rep_id = has_column(conn, "orders", "sales_rep_id")
        has_rep_id = has_column(conn, "orders", "rep_id")
        rep_target_col = "sales_rep_id" if has_sales_rep_id else ("rep_id" if has_rep_id else None)

        rep_val = None
        if rep_target_col:
            u = current_user_row()
            if u:
                rep_val = u["id"]
            if rep_val is None and sales_rep_text:
                r = conn.execute(
                    "SELECT id FROM users WHERE lower(username)=lower(?) OR lower(COALESCE(full_name,''))=lower(?)",
                    (sales_rep_text, sales_rep_text)
                ).fetchone()
                if r:
                    rep_val = r["id"]
            if rep_val is None:
                r = (conn.execute("SELECT id FROM users WHERE username='staff'").fetchone()
                     or conn.execute("SELECT id FROM users WHERE username='admin'").fetchone())
                if r:
                    rep_val = r["id"]
            if rep_val is None:
                flash("Please log in or choose a valid Sales Rep.", "error")
                return redirect(url_for("orders_new"))

        cols = [
            "order_no","created_at","total","supplier_id","product_id","quantity",
            "unit_price","payment_method","status","delivery_date","currency","notes",
            "customer_name","customer_location","line_items"
        ]
        params = [
            order_no,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total_to_save,
            header_supplier_id, header_product_id, header_quantity,
            header_unit_price, payment_method, "Pending", delivery_date, currency, notes,
            customer_name, customer_location, json.dumps(lines)
        ]

        if rep_target_col:
            cols.insert(3, rep_target_col)
            params.insert(3, int(rep_val))

        if has_column(conn, "orders", "sales_rep_name"):
            cols.append("sales_rep_name")
            params.append(sales_rep_text)

        placeholders = ",".join(["?"] * len(params))
        sql = f"INSERT INTO orders ({','.join(cols)}) VALUES ({placeholders})"
        conn.execute(sql, params)
        conn.commit()

        flash(f"Order {order_no} saved.", "success")
        return redirect(url_for("orders_history"))

    suppliers = conn.execute("SELECT id, name FROM suppliers ORDER BY name").fetchall()
    order_no_preview = generate_order_no(conn)
    return render_template("orders-new.html", suppliers=suppliers, order_no=order_no_preview)

# ---- Printable / Downloadable Order Sheet (HTML) ----
@app.get("/orders/<int:order_id>/sheet", endpoint="orders_sheet")
@login_required
def orders_sheet(order_id):
    conn = get_db()
    rep_col = _orders_rep_col(conn)
    rep_select = f", o.{rep_col} AS rep_id" if rep_col else ", NULL AS rep_id"

    r = conn.execute(f"""
        SELECT o.*, s.name AS supplier {rep_select}
        FROM orders o
        LEFT JOIN suppliers s ON s.id = o.supplier_id
        WHERE o.id = ?
    """, (order_id,)).fetchone()
    if not r:
        abort(404)

    rep_name = (r["sales_rep_name"] or "").strip() if "sales_rep_name" in r.keys() else ""
    if not rep_name:
        try:
            if r["rep_id"]:
                u = conn.execute(
                    "SELECT COALESCE(full_name, username) AS name FROM users WHERE id=?",
                    (r["rep_id"],),
                ).fetchone()
                rep_name = (u["name"] if u else "") or ""
        except Exception:
            rep_name = ""

    items = []
    try:
        items = json.loads(r["line_items"] or "[]")
    except Exception:
        items = []
    if not items:
        items = [{
            "product_id": r["product_id"],
            "qty": r["quantity"] or 0,
            "unit_price": r["unit_price"] or 0.0,
            "amount": r["total"] or 0.0
        }]

    enriched = []
    for it in items:
        if not it:
            continue
        pid = it.get("product_id")
        label = None
        if pid:
            pr = conn.execute(
                "SELECT COALESCE(product_name, name, '') AS pname, COALESCE(unit_pack_info,'') AS up FROM products WHERE id=?",
                (pid,),
            ).fetchone()
            if pr:
                up = pr["up"] or ""
                nm = pr["pname"] or ""
                label = (nm + (f" ({up})" if up else "")).strip()
        it["label"] = label or (f"Product #{pid}" if pid else "Product")
        it["qty"] = it.get("qty") or 0
        it["unit_price"] = float(it.get("unit_price") or 0.0)
        it["amount"] = float(it.get("amount") or (it["unit_price"] * it["qty"]))
        enriched.append(it)

    html = render_template("order-sheet.html", order=r, items=enriched, rep_name=rep_name)

    if request.args.get("dl") == "1":
        resp = make_response(html)
        fn = f"Order-{r['order_no'] or order_id}.html"
        resp.headers["Content-Disposition"] = f'attachment; filename="{fn}"'
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        return resp
    return html

# ---- Order History ----
@app.route("/orders/history", endpoint="orders_history")
@login_required
def orders_history():
    conn = get_db()
    where_sql, ps = _orders_where_and_params(request.args)
    rep_col = _orders_rep_col(conn)
    rep_select = f", o.{rep_col} AS rep_id" if rep_col else ", NULL AS rep_id"

    header_rows = conn.execute(
        f"""
        SELECT
            o.id, o.order_no, o.created_at, o.payment_method, o.status,
            o.delivery_date, o.currency, o.customer_name, o.customer_location,
            o.quantity, o.unit_price, o.total, o.line_items,
            o.sales_rep_name
            {rep_select}
        FROM orders o
        {where_sql}
        ORDER BY o.id DESC
        LIMIT 500
        """,
        ps
    ).fetchall()

    prows = conn.execute(
        "SELECT id, supplier_id, COALESCE(product_name, name, '') AS pname, COALESCE(unit_pack_info,'') AS up FROM products"
    ).fetchall()
    prod_map = {}
    for r in prows:
        up = r["up"] or ""
        nm = r["pname"] or ""
        label = (nm + (f" ({up})" if up else "")).strip()
        prod_map[r["id"]] = {"label": label, "supplier_id": r["supplier_id"]}

    rep_ids = [h["rep_id"] for h in header_rows if h["rep_id"]]
    rep_map = {}
    if rep_ids:
        placeholders = ",".join(["?"] * len(set(rep_ids)))
        rrows = conn.execute(
            f"SELECT id, COALESCE(full_name, username) AS name FROM users WHERE id IN ({placeholders})",
            tuple(set(rep_ids))
        ).fetchall()
        rep_map = {r["id"]: r["name"] for r in rrows}

    orders = []
    for h in header_rows:
        try:
            items_raw = json.loads(h["line_items"] or "[]")
        except Exception:
            items_raw = []

        if not items_raw:
            qty = int(float(h["quantity"] or 0))
            upx = float(h["unit_price"] or 0.0)
            amt = float(h["total"] or (qty * upx))
            items_raw = [{
                "product_id": None,
                "qty": qty,
                "unit_price": upx,
                "amount": amt,
                "desc": None
            }]

        items = []
        total = 0.0
        for it in items_raw:
            pid = it.get("product_id")
            label = prod_map.get(pid, {}).get("label") if pid else (it.get("desc") or "Product")
            qty = int(float(it.get("qty") or 0))
            upx = float(it.get("unit_price") or 0.0)
            amt = float(it.get("amount") or (qty * upx))
            total += amt
            items.append({"label": label, "qty": qty, "unit_price": upx, "amount": amt})

        sales_rep_display = (h["sales_rep_name"] or "").strip() if "sales_rep_name" in h.keys() else ""
        if not sales_rep_display:
            sales_rep_display = rep_map.get(h["rep_id"], "") if h["rep_id"] else ""

        orders.append({
            "id": h["id"],
            "order_no": h["order_no"],
            "created_at": h["created_at"],
            "customer_name": h["customer_name"] or "",
            "customer_location": h["customer_location"] or "",
            "sales_rep": sales_rep_display,
            "currency": h["currency"] or "KES",
            "items": items,
            "total": round(total, 2),
        })

    return render_template("orders-history.html", orders=orders)

# ---- Orders: status ----
@app.post("/orders/<int:order_id>/status", endpoint="orders_update_status")
@admin_required
def orders_update_status(order_id):
    new_status = (request.form.get("status") or "").strip().title()
    if new_status not in ("Pending", "Delivered", "Cancelled"):
        flash("Invalid status.", "error")
        return redirect(url_for("orders_history"))

    conn = get_db()
    if new_status == "Delivered":
        conn.execute(
            "UPDATE orders SET status=?, delivery_date=COALESCE(delivery_date, date('now')) WHERE id=?",
            (new_status, order_id),
        )
    else:
        conn.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
    conn.commit()
    flash("Order status updated.", "success")
    return redirect(request.referrer or url_for("orders_history"))

# ---- Orders CSV export ----
@app.get("/orders/history.csv", endpoint="orders_history_csv")
@login_required
def orders_history_csv():
    conn = get_db()
    where_sql, ps = _orders_where_and_params(request.args)
    rep_col = _orders_rep_col(conn)
    rep_select = f", o.{rep_col} AS rep_id" if rep_col else ", NULL AS rep_id"

    orders = conn.execute(
        f"""
        SELECT
            o.order_no, o.created_at, o.quantity, o.unit_price, o.total,
            o.payment_method, o.status, o.delivery_date, o.currency, o.notes,
            o.customer_name, o.customer_location, o.line_items,
            o.sales_rep_name
            {rep_select},
            s.name AS supplier,
            p.id AS legacy_product_id,
            p.product_name AS legacy_product_name,
            COALESCE(p.unit_pack_info,'') AS legacy_up
        FROM orders o
        LEFT JOIN suppliers s ON s.id = o.supplier_id
        LEFT JOIN products  p ON p.id = o.product_id
        {where_sql}
        ORDER BY o.rowid DESC
        """,
        ps
    ).fetchall()

    prows = conn.execute(
        "SELECT id, supplier_id, COALESCE(product_name, name, '') AS pname, COALESCE(unit_pack_info,'') AS up FROM products"
    ).fetchall()
    prod_map = {}
    for r in prows:
        up = r["up"] or ""
        nm = r["pname"] or ""
        label = (nm + (f" ({up})" if up else "")).strip()
        prod_map[r["id"]] = {"label": label, "supplier_id": r["supplier_id"]}

    srows = conn.execute("SELECT id, name FROM suppliers").fetchall()
    supplier_map = {r["id"]: r["name"] for r in srows}

    rep_ids = [o["rep_id"] for o in orders if o["rep_id"]]
    rep_map = {}
    if rep_ids:
        placeholders = ",".join(["?"] * len(set(rep_ids)))
        rrows = conn.execute(
            f"SELECT id, COALESCE(full_name, username) AS name FROM users WHERE id IN ({placeholders})",
            tuple(set(rep_ids))
        ).fetchall()
        rep_map = {r["id"]: r["name"] for r in rrows}

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([
        "Order No", "Date", "Supplier", "Product", "Qty", "Unit Price",
        "Line Total", "Payment Method", "Status", "Delivery Date", "Currency",
        "Customer", "Location", "Sales Rep", "Notes"
    ])

    for o in orders:
        try:
            items = json.loads(o["line_items"] or "[]")
        except Exception:
            items = []

        sales_rep_display = (o["sales_rep_name"] or "").strip() if "sales_rep_name" in o.keys() else ""
        if not sales_rep_display:
            sales_rep_display = rep_map.get(o["rep_id"], "") if o["rep_id"] else ""

        if items:
            for it in items:
                pid = it.get("product_id")
                qty = int(float(it.get("qty") or 0))
                upx = float(it.get("unit_price") or 0.0)
                amt = float(it.get("amount") or (qty * upx))

                label = prod_map.get(pid, {}).get("label") or (f"Product #{pid}" if pid else "Product")
                sid = it.get("supplier_id")
                if not sid and pid in prod_map:
                    sid = prod_map[pid].get("supplier_id")
                supp_name = supplier_map.get(sid) if sid else ""

                w.writerow([
                    o["order_no"], o["created_at"], supp_name, label, qty,
                    f"{upx:.2f}", f"{amt:.2f}",
                    o["payment_method"], o["status"], o["delivery_date"], o["currency"],
                    o["customer_name"] or "", o["customer_location"] or "",
                    sales_rep_display,
                    o["notes"] or ""
                ])
        else:
            leg_label = o["legacy_product_name"]
            if leg_label and o["legacy_up"]:
                leg_label = f"{leg_label} ({o['legacy_up']})"
            elif not leg_label:
                leg_label = prod_map.get(o["legacy_product_id"], {}).get("label", "")
            w.writerow([
                o["order_no"], o["created_at"], "", leg_label,
                o["quantity"] or 0, f"{(o['unit_price'] or 0):.2f}", f"{(o['total'] or 0):.2f}",
                o["payment_method"], o["status"], o["delivery_date"], o["currency"],
                o["customer_name"] or "", o["customer_location"] or "",
                sales_rep_display,
                o["notes"] or ""
            ])

    mem = io.BytesIO(out.getvalue().encode("utf-8"))
    mem.seek(0)
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name="orders_history.csv")

# ======================= Targets & uploads =======================
@app.route("/targets", methods=["GET"], endpoint="targets")
@login_required
def targets_page():
    conn = get_db()
    today = date.today()
    m, y = today.month, today.year

    rep_total = conn.execute(
        "SELECT COALESCE(SUM(target_value),0) AS t FROM rep_targets WHERE month=? AND year=?",
        (m, y),
    ).fetchone()["t"] or 0.0

    supplier_total = conn.execute(
        "SELECT COALESCE(SUM(target_value),0) AS t FROM supplier_targets WHERE month=? AND year=?",
        (m, y),
    ).fetchone()["t"] or 0.0

    supplier_targets = conn.execute(
        """
        SELECT st.supplier_id AS id, s.name AS name, COALESCE(SUM(st.target_value),0) AS target_value
        FROM supplier_targets st
        JOIN suppliers s ON s.id = st.supplier_id
        WHERE st.month=? AND st.year=?
        GROUP BY st.supplier_id, s.name
        ORDER BY s.name
        """, (m, y)
    ).fetchall()

    s_mtd_rows = conn.execute(
        "SELECT supplier_id AS id, COALESCE(mtd_value,0) AS mtd FROM supplier_actuals WHERE month=? AND year=?",
        (m, y)
    ).fetchall()
    s_mtd_map = {r["id"]: r["mtd"] for r in s_mtd_rows}

    supplier_rows = []
    for row in supplier_targets:
        supplier_rows.append(type("R", (), {
            "id": row["id"],
            "name": row["name"],
            "target_value": float(row["target_value"]),
            "mtd": float(s_mtd_map.get(row["id"], 0.0)),
        }))

    rep_targets = conn.execute(
        """
        SELECT rt.rep_id AS id, COALESCE(u.full_name, u.username) AS name,
               COALESCE(SUM(rt.target_value),0) AS target_value
        FROM rep_targets rt
        JOIN users u ON u.id = rt.rep_id
        WHERE rt.month=? AND rt.year=?
        GROUP BY rt.rep_id, name
        ORDER BY name
        """, (m, y)
    ).fetchall()

    r_mtd_rows = conn.execute(
        "SELECT rep_id AS id, COALESCE(mtd_value,0) AS mtd FROM rep_actuals WHERE month=? AND year=?",
        (m, y)
    ).fetchall()
    r_mtd_map = {r["id"]: r["mtd"] for r in r_mtd_rows}

    rep_rows = []
    for row in rep_targets:
        rep_rows.append(type("R", (), {
            "id": row["id"],
            "name": row["name"],
            "target_value": float(row["target_value"]),
            "mtd": float(r_mtd_map.get(row["id"], 0.0)),
        }))

    supp_recent = conn.execute(
        """
        SELECT st.supplier_id, s.name AS supplier_name, st.month, st.year, st.target_value
        FROM supplier_targets st
        JOIN suppliers s ON s.id = st.supplier_id
        ORDER BY st.id DESC
        LIMIT 10
        """
    ).fetchall()

    reps_recent = conn.execute(
        """
        SELECT rt.rep_id, COALESCE(u.full_name, u.username) AS rep_name, rt.month, rt.year, rt.target_value
        FROM rep_targets rt
        JOIN users u ON u.id = rt.rep_id
        ORDER BY rt.id DESC
        LIMIT 10
        """
    ).fetchall()

    return render_template(
        "targets.html",
        month=m, year=y,
        rep_total=float(rep_total),
        supplier_total=float(supplier_total),
        this_month=m, this_year=y,
        this_month_supplier_targets=float(supplier_total),
        this_month_rep_targets=float(rep_total),
        supplier_rows=supplier_rows,
        rep_rows=rep_rows,
        supp_recent=supp_recent,
        reps_recent=reps_recent,
    )

@app.route("/targets/rep/add", methods=["POST"], endpoint="targets_rep_add")
@admin_required
def targets_rep_add():
    try:
        rep_id = int(request.form.get("rep_id") or 0)
        month = int(request.form.get("month") or 0)
        year = int(request.form.get("year") or 0)
        target_value = float(request.form.get("target_value") or 0)
    except ValueError:
        flash("Invalid input for rep target.", "error")
        return redirect(url_for("targets"))

    if not (rep_id > 0 and 1 <= month <= 12 and year >= 2000):
        flash("Provide valid rep_id, month (1-12), and year.", "error")
        return redirect(url_for("targets"))

    conn = get_db()
    conn.execute(
        """
        INSERT INTO rep_targets(rep_id, month, year, target_value)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(rep_id, month, year)
        DO UPDATE SET target_value = excluded.target_value
        """,
        (rep_id, month, year, target_value),
    )
    conn.commit()
    flash("Rep target saved.", "success")
    return redirect(url_for("targets"))

@app.route("/targets/supplier/add", methods=["POST"], endpoint="targets_supplier_add")
@admin_required
def targets_supplier_add():
    try:
        supplier_id = int(request.form.get("supplier_id") or 0)
        month = int(request.form.get("month") or 0)
        year = int(request.form.get("year") or 0)
        target_value = float(request.form.get("target_value") or 0)
    except ValueError:
        flash("Invalid input for supplier target.", "error")
        return redirect(url_for("targets"))

    if not (supplier_id > 0 and 1 <= month <= 12 and year >= 2000):
        flash("Provide valid supplier_id, month (1-12), and year.", "error")
        return redirect(url_for("targets"))

    conn = get_db()
    conn.execute(
        """
        INSERT INTO supplier_targets(supplier_id, month, year, target_value)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(supplier_id, month, year)
        DO UPDATE SET target_value = excluded.target_value
        """,
        (supplier_id, month, year, target_value),
    )
    conn.commit()
    flash("Supplier target saved.", "success")
    return redirect(url_for("targets"))

@app.route("/targets/supplier/actual", methods=["POST"], endpoint="targets_supplier_actual")
@admin_required
def targets_supplier_actual():
    try:
        supplier_id = int(request.form.get("supplier_id") or 0)
        month = int(request.form.get("month") or 0)
        year = int(request.form.get("year") or 0)
        mtd_value = float(request.form.get("mtd_value") or 0)
    except ValueError:
        flash("Invalid input for supplier MTD.", "error")
        return redirect(url_for("targets"))

    if not (supplier_id > 0 and 1 <= month <= 12 and year >= 2000):
        flash("Provide valid supplier_id, month (1-12), and year.", "error")
        return redirect(url_for("targets"))

    conn = get_db()
    conn.execute(
        """
        INSERT INTO supplier_actuals(supplier_id, month, year, mtd_value)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(supplier_id, month, year)
        DO UPDATE SET mtd_value=excluded.mtd_value
        """,
        (supplier_id, month, year, mtd_value),
    )
    conn.commit()
    flash("Supplier MTD saved.", "success")
    return redirect(url_for("targets"))

@app.route("/targets/rep/actual", methods=["POST"], endpoint="targets_rep_actual")
@admin_required
def targets_rep_actual():
    try:
        rep_id = int(request.form.get("rep_id") or 0)
        month = int(request.form.get("month") or 0)
        year = int(request.form.get("year") or 0)
        mtd_value = float(request.form.get("mtd_value") or 0)
    except ValueError:
        flash("Invalid input for rep MTD.", "error")
        return redirect(url_for("targets"))

    if not (rep_id > 0 and 1 <= month <= 12 and year >= 2000):
        flash("Provide valid rep_id, month (1-12), and year.", "error")
        return redirect(url_for("targets"))

    conn = get_db()
    conn.execute(
        """
        INSERT INTO rep_actuals(rep_id, month, year, mtd_value)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(rep_id, month, year)
        DO UPDATE SET mtd_value=excluded.mtd_value
        """,
        (rep_id, month, year, mtd_value),
    )
    conn.commit()
    flash("Rep MTD saved.", "success")
    return redirect(url_for("targets"))

# ======================= Suppliers (upload) =======================
@app.route("/suppliers/upload", methods=["POST"], endpoint="suppliers_upload")
@admin_required
def suppliers_upload():
    file = request.files.get("file")
    if not file or not file.filename.lower().endswith(".csv"):
        flash("Please upload a CSV (.csv) with header 'name' (also accepts 'supplier' or 'supplier_name').", "error")
        return redirect(request.referrer or url_for("products_list"))

    text = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        flash("CSV appears empty or has no header row.", "error")
        return redirect(request.referrer or url_for("products_list"))

    headers = {h.lower().strip(): h for h in reader.fieldnames}
    name_key = headers.get("name") or headers.get("supplier") or headers.get("supplier_name")
    if not name_key:
        flash("CSV must include 'name' (or 'supplier' / 'supplier_name') column.", "error")
        return redirect(request.referrer or url_for("products_list"))

    conn = get_db()
    added, skipped = 0, 0
    for row in reader:
        name = (row.get(name_key) or "").strip()
        if not name:
            skipped += 1
            continue
        exists = conn.execute("SELECT 1 FROM suppliers WHERE lower(name)=lower(?)", (name,)).fetchone()
        if exists:
            skipped += 1
            continue
        conn.execute("INSERT INTO suppliers(name) VALUES (?)", (name,))
        added += 1

    conn.commit()
    flash(f"Suppliers uploaded: {added} (skipped {skipped})", "success")
    return redirect(request.referrer or url_for("products_list"))

@app.route("/suppliers/sample", endpoint="download_suppliers_sample")
@admin_required
def download_suppliers_sample():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["name"])
    w.writerow(["Acme Ltd"])
    mem = io.BytesIO(out.getvalue().encode("utf-8"))
    mem.seek(0)
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name="suppliers_sample.csv")

# ======================= Password page =======================
@app.route("/change-password", methods=["GET", "POST"], endpoint="change_password")
@admin_required
def change_password_view():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        new_pw = request.form.get("new_password") or ""
        if not username or not new_pw:
            flash("Provide both username and new password.", "error")
            return redirect(url_for("change_password"))
        conn = get_db()
        row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            flash("User not found.", "error")
            return redirect(url_for("change_password"))
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (generate_password_hash(new_pw), row["id"]),
        )
        conn.commit()
        flash("Password updated.", "success")
    return render_template("change-password.html")

# ======================= Main =======================
if __name__ == "__main__":
    with app.app_context():
        ensure_schema()
    app.run(debug=True)
