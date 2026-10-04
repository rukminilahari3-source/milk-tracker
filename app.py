"""MilkLog REST API — single-file Flask + SQLite backend.

Run:   pip install -r requirements.txt && python app.py
Open:  http://localhost:5000   (Flask also serves index.html)

Endpoints
  GET    /api/health
  GET    /api/users
  POST   /api/users                  {"name": "Asha"}
  GET    /api/entries[?month=YYYY-MM&user=Alice]
  PUT    /api/entries/<YYYY-MM-DD>?user=Alice    {"morningQty": 1.5, "eveningQty": 2.0, "price": 60}
  DELETE /api/entries/<YYYY-MM-DD>?user=Alice
  POST   /api/entries/bulk             {"entries": [{date, user, morningQty, eveningQty, price}, ...]}
  DELETE /api/entries                  (clear all)
  GET    /api/prefs
  PUT    /api/prefs                    {"defaultPrice": 60, "milkType": "Cow"}
"""
import os
import re
import sqlite3
import time
from contextlib import closing
from datetime import date as Date
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE = Path(__file__).parent
DB_PATH = BASE / "milklog.db"
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
PREF_KEYS = {"defaultPrice", "milkType"}
DEFAULT_USER = "Default"

app = Flask(__name__, static_folder=None)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or os.urandom(32)


# ---------- database ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def migrate_entries_schema(conn):
    table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entries'").fetchone()
    if not table:
        return

    columns = [row[1] for row in conn.execute("PRAGMA table_info(entries)").fetchall()]
    if "user_id" in columns and "morning_qty" in columns and "evening_qty" in columns:
        return

    conn.execute("ALTER TABLE entries RENAME TO entries_legacy")
    conn.executescript(
        """
        CREATE TABLE entries (
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            qty REAL NOT NULL CHECK (qty >= 0),
            morning_qty REAL NOT NULL DEFAULT 0 CHECK (morning_qty >= 0),
            evening_qty REAL NOT NULL DEFAULT 0 CHECK (evening_qty >= 0),
            price REAL NOT NULL CHECK (price >= 0),
            saved INTEGER NOT NULL,
            PRIMARY KEY (user_id, date)
        );
        """
    )
    legacy_rows = conn.execute(
        "SELECT date, qty, price, saved FROM entries_legacy ORDER BY date"
    ).fetchall()
    for row in legacy_rows:
        conn.execute(
            "INSERT INTO entries (user_id, date, qty, morning_qty, evening_qty, price, saved) VALUES (?,?,?,?,?,?,?)",
            (DEFAULT_USER, row[0], float(row[1]), float(row[1]), 0.0, float(row[2]), row[3]),
        )
    conn.execute("DROP TABLE entries_legacy")


def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS entries (
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                qty REAL NOT NULL CHECK (qty >= 0),
                morning_qty REAL NOT NULL DEFAULT 0 CHECK (morning_qty >= 0),
                evening_qty REAL NOT NULL DEFAULT 0 CHECK (evening_qty >= 0),
                price REAL NOT NULL CHECK (price >= 0),
                saved INTEGER NOT NULL,
                PRIMARY KEY (user_id, date)
            );
            CREATE TABLE IF NOT EXISTS prefs (key TEXT PRIMARY KEY, value TEXT);
            """
        )
        migrate_entries_schema(conn)
        conn.execute(
            "INSERT OR IGNORE INTO users (name, created) VALUES (?, ?)",
            (DEFAULT_USER, int(time.time() * 1000)),
        )
        conn.execute(
            "INSERT OR IGNORE INTO auth_users (username, password_hash, created) VALUES (?, ?, ?)",
            (
                os.environ.get("MILKLOG_ADMIN_USERNAME", "admin"),
                generate_password_hash(os.environ.get("MILKLOG_ADMIN_PASSWORD", "admin123")),
                int(time.time() * 1000),
            ),
        )
        conn.commit()


# ---------- helpers ----------
class ApiError(Exception):
    def __init__(self, msg, status=400):
        self.msg, self.status = msg, status


@app.errorhandler(ApiError)
def handle_api_error(e):
    return jsonify(error=e.msg), e.status


@app.errorhandler(401)
def unauthorized(_):
    return jsonify(error="Login required"), 401


@app.errorhandler(404)
def not_found(_):
    return jsonify(error="Not found"), 404


@app.errorhandler(405)
def bad_method(_):
    return jsonify(error="Method not allowed"), 405


@app.after_request
def cors(resp):  # lets the page work when opened from file:// or another origin
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, PUT, POST, DELETE, OPTIONS"
    return resp


def require_login():
    username = session.get("username")
    if not username:
        raise ApiError("Login required", 401)
    return username


def valid_date(s):
    try:
        return Date.fromisoformat(s).isoformat() == s
    except (TypeError, ValueError):
        raise ApiError(f"Invalid date '{s}', expected YYYY-MM-DD")


def normalize_user(user_name=None, source=None):
    if source is not None and isinstance(source, dict):
        user_name = source.get("user") or source.get("userId") or source.get("user_name") or user_name
    name = (user_name or DEFAULT_USER).strip()
    if not name:
        name = DEFAULT_USER
    return ensure_user(name)


def ensure_user(name):
    clean_name = (name or DEFAULT_USER).strip()
    if not clean_name:
        clean_name = DEFAULT_USER
    row = db().execute("SELECT name FROM users WHERE lower(name)=lower(?)", (clean_name,)).fetchone()
    if row:
        return row["name"]
    db().execute("INSERT INTO users (name, created) VALUES (?, ?)", (clean_name, int(time.time() * 1000)))
    return clean_name


def parse_entry(d, data, user_name=None):
    """Validate one payload and return (user_id, date, qty, morning_qty, evening_qty, price)."""
    valid_date(d)
    user_id = normalize_user(user_name, data)
    try:
        if "morningQty" in data or "eveningQty" in data:
            morning_qty = float(data.get("morningQty", 0) or 0)
            evening_qty = float(data.get("eveningQty", 0) or 0)
        elif "qty" in data:
            qty = float(data["qty"])
            morning_qty = qty
            evening_qty = 0.0
        else:
            raise KeyError
        price = float(data.get("price", 0) or 0)
    except (KeyError, TypeError, ValueError):
        raise ApiError("'morningQty', 'eveningQty' or 'qty', and 'price' must be numbers")

    total_qty = morning_qty + evening_qty
    if not 0 <= morning_qty <= 100:
        raise ApiError("'morningQty' must be between 0 and 100 litres")
    if not 0 <= evening_qty <= 100:
        raise ApiError("'eveningQty' must be between 0 and 100 litres")
    if not 0 < total_qty <= 100:
        raise ApiError("Total milk quantity must be between 0 and 100 litres")
    if not 0 <= price <= 10000:
        raise ApiError("'price' must be between 0 and 10000")
    return user_id, d, total_qty, morning_qty, evening_qty, price


def upsert(d, user_id, qty, morning_qty, evening_qty, price):
    db().execute(
        "INSERT INTO entries (user_id, date, qty, morning_qty, evening_qty, price, saved) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(user_id, date) DO UPDATE SET qty=excluded.qty, morning_qty=excluded.morning_qty, evening_qty=excluded.evening_qty, price=excluded.price, saved=excluded.saved",
        (user_id, d, qty, morning_qty, evening_qty, price, int(time.time() * 1000)),
    )


def entry_to_dict(row):
    return {
        "userId": row["user_id"],
        "date": row["date"],
        "qty": float(row["qty"]),
        "morningQty": float(row["morning_qty"]),
        "eveningQty": float(row["evening_qty"]),
        "price": float(row["price"]),
        "saved": row["saved"],
    }


def get_entry(d, user_id):
    row = db().execute("SELECT * FROM entries WHERE user_id=? AND date=?", (user_id, d)).fetchone()
    if row is None:
        raise ApiError("No entry for that date", 404)
    return entry_to_dict(row)


# ---------- entries ----------
@app.get("/api/health")
def health():
    return jsonify(status="ok")


@app.get("/api/me")
def who_am_i():
    username = session.get("username")
    if not username:
        raise ApiError("Login required", 401)
    return jsonify({"loggedIn": True, "username": username})


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        raise ApiError("Username and password are required")
    row = db().execute("SELECT * FROM auth_users WHERE lower(username)=lower(?)", (username,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        raise ApiError("Invalid username or password", 401)
    session["username"] = row["username"]
    return jsonify({"loggedIn": True, "username": row["username"]})


@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        raise ApiError("Username and password are required")
    if len(password) < 4:
        raise ApiError("Password must be at least 4 characters")
    existing = db().execute("SELECT 1 FROM auth_users WHERE lower(username)=lower(?)", (username,)).fetchone()
    if existing:
        raise ApiError("Username already exists")
    db().execute(
        "INSERT INTO auth_users (username, password_hash, created) VALUES (?, ?, ?)",
        (username, generate_password_hash(password), int(time.time() * 1000)),
    )
    db().commit()
    ensure_user(username)
    session["username"] = username
    return jsonify({"loggedIn": True, "username": username}), 201


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"loggedOut": True})


@app.get("/api/users")
def list_users():
    require_login()
    rows = db().execute("SELECT name FROM users ORDER BY name").fetchall()
    return jsonify([row["name"] for row in rows])


@app.post("/api/users")
def add_user():
    require_login()
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or data.get("user") or "").strip()
    if not name:
        raise ApiError("User name is required")
    user = ensure_user(name)
    return jsonify({"name": user}), 201


@app.get("/api/entries")
def list_entries():
    require_login()
    user_name = request.args.get("user") or request.args.get("userId") or request.args.get("userName")
    month = request.args.get("month")
    if month:
        if not MONTH_RE.match(month):
            raise ApiError("'month' must be YYYY-MM")
        if user_name:
            rows = db().execute(
                "SELECT * FROM entries WHERE user_id=? AND date LIKE ? ORDER BY date",
                (normalize_user(user_name), month + "-%"),
            )
        else:
            rows = db().execute("SELECT * FROM entries WHERE date LIKE ? ORDER BY date", (month + "-%",))
    else:
        if user_name:
            rows = db().execute("SELECT * FROM entries WHERE user_id=? ORDER BY date", (normalize_user(user_name),))
        else:
            rows = db().execute("SELECT * FROM entries ORDER BY date, user_id")
    return jsonify([entry_to_dict(r) for r in rows])


@app.put("/api/entries/<d>")
def put_entry(d):
    require_login()
    payload = request.get_json(silent=True) or {}
    user_name = request.args.get("user") or request.args.get("userId") or payload.get("user") or payload.get("userId") or session.get("username") or DEFAULT_USER
    user_id, _, qty, morning_qty, evening_qty, price = parse_entry(d, payload, user_name)
    upsert(d, user_id, qty, morning_qty, evening_qty, price)
    db().commit()
    return jsonify(get_entry(d, user_id))


@app.delete("/api/entries/<d>")
def delete_entry(d):
    require_login()
    valid_date(d)
    user_name = request.args.get("user") or request.args.get("userId") or session.get("username") or DEFAULT_USER
    user_id = normalize_user(user_name)
    cur = db().execute("DELETE FROM entries WHERE user_id=? AND date=?", (user_id, d))
    db().commit()
    if not cur.rowcount:
        raise ApiError("No entry for that date", 404)
    return "", 204


@app.post("/api/entries/bulk")
def bulk_entries():
    require_login()
    payload = request.get_json(silent=True) or {}
    items = payload.get("entries")
    if not isinstance(items, list):
        raise ApiError("'entries' must be a list")

    for item in items:
        if not isinstance(item, dict):
            raise ApiError("Each entry must be a JSON object")
        if "date" not in item:
            raise ApiError("Each entry must include a 'date'")
        user_name = item.get("user") or item.get("userId") or request.args.get("user") or DEFAULT_USER
        user_id, _, qty, morning_qty, evening_qty, price = parse_entry(item["date"], item, user_name)
        upsert(item["date"], user_id, qty, morning_qty, evening_qty, price)
    db().commit()
    return jsonify(imported=len(items)), 201


@app.delete("/api/entries")
def clear_entries():
    require_login()
    user_name = request.args.get("user") or request.args.get("userId")
    if user_name:
        db().execute("DELETE FROM entries WHERE user_id=?", (normalize_user(user_name),))
    else:
        db().execute("DELETE FROM entries")
    db().commit()
    return "", 204


# ---------- prefs ----------
@app.get("/api/prefs")
def get_prefs():
    require_login()
    return jsonify({r["key"]: r["value"] for r in db().execute("SELECT * FROM prefs")})


@app.put("/api/prefs")
def put_prefs():
    require_login()
    data = request.get_json(silent=True) or {}
    unknown = set(data) - PREF_KEYS
    if unknown:
        raise ApiError(f"Unknown preference(s): {', '.join(sorted(unknown))}")
    for k, v in data.items():
        db().execute("INSERT OR REPLACE INTO prefs (key, value) VALUES (?,?)", (k, str(v)))
    db().commit()
    return get_prefs()


# ---------- frontend ----------
@app.get("/")
def index():
    return send_from_directory(BASE, "index.html")


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
