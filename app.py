"""MilkLog REST API — Flask backend with SQLite or PostgreSQL storage.

Run:   pip install -r requirements.txt && python app.py
Open:  http://localhost:5000   (Flask also serves index.html)

Endpoints
  GET    /api/health
  GET    /api/entries[?month=YYYY-MM]
  PUT    /api/entries/<YYYY-MM-DD>     {"qty": 1.5, "price": 60}   (create/update)
  DELETE /api/entries/<YYYY-MM-DD>
  POST   /api/entries/bulk             {"entries": [{date, qty, price}, ...]}
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

BASE = Path(__file__).parent
DB_PATH = Path(os.environ.get("MILKLOG_DB_PATH", BASE / "milklog.db"))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip() or None
CORS_ORIGINS = {
    origin.strip()
    for origin in os.environ.get("MILKLOG_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
}
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
PREF_KEYS = {"defaultPrice", "milkType"}

app = Flask(__name__, static_folder=None)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "milklog-dev-secret")


# ---------- database ----------
def _postgres_dsn():
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        return "postgresql://" + DATABASE_URL[len("postgres://"):]
    return DATABASE_URL


def _connect_postgres():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(_postgres_dsn(), row_factory=dict_row)


def _sql(query):
    return query.replace("?", "%s") if DATABASE_URL else query


def db():
    if "db" not in g:
        if DATABASE_URL:
            g.db = _connect_postgres()
        else:
            g.db = sqlite3.connect(DB_PATH)
            g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    if DATABASE_URL:
        with _connect_postgres() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    date       TEXT NOT NULL,
                    userId     TEXT NOT NULL DEFAULT '',
                    qty        DOUBLE PRECISION NOT NULL CHECK (qty > 0),
                    morningQty DOUBLE PRECISION DEFAULT 0,
                    eveningQty DOUBLE PRECISION DEFAULT 0,
                    price      DOUBLE PRECISION NOT NULL CHECK (price >= 0),
                    saved      BIGINT NOT NULL,
                    PRIMARY KEY (date, userId)
                )
                """
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS user_profiles (userId TEXT PRIMARY KEY, ownerUsername TEXT NOT NULL, createdAt BIGINT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS prefs (key TEXT PRIMARY KEY, value TEXT)"
            )
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS entries (
                date        TEXT NOT NULL,
                userId      TEXT NOT NULL DEFAULT '',
                qty         REAL NOT NULL CHECK (qty > 0),
                morningQty  REAL DEFAULT 0,
                eveningQty  REAL DEFAULT 0,
                price       REAL NOT NULL CHECK (price >= 0),
                saved       INTEGER NOT NULL,
                PRIMARY KEY (date, userId)
            );
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_profiles (
                userId TEXT PRIMARY KEY,
                ownerUsername TEXT NOT NULL,
                createdAt INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS prefs (key TEXT PRIMARY KEY, value TEXT);
            """
        )


init_db()


# ---------- helpers ----------
class ApiError(Exception):
    def __init__(self, msg, status=400):
        self.msg, self.status = msg, status


@app.errorhandler(ApiError)
def handle_api_error(e):
    return jsonify(error=e.msg), e.status


@app.errorhandler(404)
def not_found(_):
    return jsonify(error="Not found"), 404


@app.errorhandler(405)
def bad_method(_):
    return jsonify(error="Method not allowed"), 405


@app.after_request
def cors(resp):
    origin = request.headers.get("Origin")
    if not CORS_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = "*"
    elif origin in CORS_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers.add("Vary", "Origin")
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, PUT, POST, DELETE, OPTIONS"
    return resp


def valid_date(s):
    try:
        return Date.fromisoformat(s).isoformat() == s
    except (TypeError, ValueError):
        raise ApiError(f"Invalid date '{s}', expected YYYY-MM-DD")


def parse_entry(d, data):
    """Validate one entry payload and return a (date, userId, qty, morningQty, eveningQty, price) tuple."""
    valid_date(d)
    data = data or {}
    qty_val = data.get("qty")
    price_val = data.get("price")
    morning = data.get("morningQty")
    evening = data.get("eveningQty")

    if morning is None and evening is None and qty_val is None:
        raise ApiError("'qty' and 'price' must be numbers")

    try:
        if morning is not None or evening is not None:
            morning_qty = float(morning if morning is not None else 0)
            evening_qty = float(evening if evening is not None else 0)
            qty = morning_qty + evening_qty
        else:
            qty = float(qty_val)
            morning_qty = qty
            evening_qty = 0.0
        price = float(price_val)
    except (TypeError, ValueError):
        raise ApiError("'qty' and 'price' must be numbers")

    if not 0 < qty <= 100:
        raise ApiError("'qty' must be between 0 and 100 litres")
    if not 0 <= price <= 10000:
        raise ApiError("'price' must be between 0 and 10000")
    if morning_qty < 0 or evening_qty < 0:
        raise ApiError("'morningQty' and 'eveningQty' must be non-negative")
    return d, qty, morning_qty, evening_qty, price


def chosen_user_id():
    query_user = request.args.get("user")
    payload = request.get_json(silent=True) or {}
    user_id = (payload.get("userId") or query_user or session.get("username") or "").strip()
    return user_id or "default"


def upsert(d, qty, morning_qty, evening_qty, price, user_id):
    db().execute(
        _sql(
            "INSERT INTO entries (date, userId, qty, morningQty, eveningQty, price, saved) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(date, userId) DO UPDATE SET qty=excluded.qty, morningQty=excluded.morningQty, eveningQty=excluded.eveningQty, price=excluded.price, saved=excluded.saved"
        ),
        (d, user_id, qty, morning_qty, evening_qty, price, int(time.time() * 1000)),
    )


def get_entry(d, user_id=None):
    if user_id is None:
        user_id = chosen_user_id()
    row = db().execute(_sql("SELECT * FROM entries WHERE date=? AND userId=?"), (d, user_id)).fetchone()
    return dict(row) if row is not None else None


# ---------- entries ----------
@app.get("/api/health")
def health():
    return jsonify(status="ok")


@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        raise ApiError("Username and password are required")
    if db().execute(_sql("SELECT 1 FROM users WHERE username=?"), (username,)).fetchone():
        raise ApiError("Username already exists", 409)
    db().execute(_sql("INSERT INTO users (username, password) VALUES (?, ?)"), (username, password))
    db().commit()
    session["username"] = username
    return jsonify({"username": username, "loggedIn": True}), 201


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    row = db().execute(_sql("SELECT * FROM users WHERE username=?"), (username,)).fetchone()
    if row is None or row["password"] != password:
        raise ApiError("Invalid username or password", 401)
    session["username"] = username
    return jsonify({"username": username, "loggedIn": True})


@app.post("/api/logout")
def logout():
    session.pop("username", None)
    return jsonify({"loggedOut": True})


@app.get("/api/me")
def me():
    username = session.get("username")
    if not username:
        return jsonify(error="Authentication required"), 401
    return jsonify({"username": username})


@app.get("/api/users")
def list_users():
    username = session.get("username")
    if not username:
        return jsonify(error="Authentication required"), 401
    rows = db().execute(
        _sql("SELECT userId, ownerUsername FROM user_profiles WHERE ownerUsername=? ORDER BY userId"),
        (username,),
    ).fetchall()
    return jsonify([{"id": row["userId"], "name": row["userId"], "owner": row["ownerUsername"]} for row in rows])


@app.post("/api/users")
def create_user():
    username = session.get("username")
    if not username:
        return jsonify(error="Authentication required"), 401
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or data.get("userId") or "").strip()
    if not name:
        raise ApiError("'name' is required")
    if not db().execute(_sql("SELECT 1 FROM user_profiles WHERE userId=?"), (name,)).fetchone():
        db().execute(
            _sql("INSERT INTO user_profiles (userId, ownerUsername, createdAt) VALUES (?, ?, ?)"),
            (name, username, int(time.time() * 1000)),
        )
    db().commit()
    return jsonify({"id": name, "name": name, "owner": username}), 201


@app.get("/api/entries")
def list_entries():
    user = request.args.get("user")
    month = request.args.get("month")

    if "username" not in session and not user:
        has_rows = db().execute("SELECT 1 FROM entries LIMIT 1").fetchone() is not None
        if not has_rows:
            return jsonify(error="Authentication required"), 401

    conditions = []
    params = []
    if user:
        conditions.append("userId=?")
        params.append(user)
    elif "username" in session:
        owner = session["username"]
        conditions.append(
            "(userId IN (SELECT userId FROM user_profiles WHERE ownerUsername=?) OR userId=?)"
        )
        params.extend((owner, owner))

    if month:
        if not MONTH_RE.match(month):
            raise ApiError("'month' must be YYYY-MM")
        conditions.append("date LIKE ?")
        params.append(month + "-%")

    query = "SELECT * FROM entries"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query = _sql(query + " ORDER BY date")
    rows = db().execute(query, tuple(params)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.put("/api/entries/<d>")
def put_entry(d):
    data = request.get_json(silent=True) or {}
    user_id = chosen_user_id()
    _, qty, morning_qty, evening_qty, price = parse_entry(d, data)
    upsert(d, qty, morning_qty, evening_qty, price, user_id)
    db().commit()
    entry = get_entry(d, user_id)
    entry["userId"] = user_id
    entry["qty"] = float(entry["qty"])
    entry["morningQty"] = float(entry["morningQty"] or 0)
    entry["eveningQty"] = float(entry["eveningQty"] or 0)
    return jsonify(entry)


@app.delete("/api/entries/<d>")
def delete_entry(d):
    valid_date(d)
    user_id = chosen_user_id()
    cur = db().execute(_sql("DELETE FROM entries WHERE date=? AND userId=?"), (d, user_id))
    db().commit()
    if not cur.rowcount:
        raise ApiError("No entry for that date", 404)
    return "", 204


@app.post("/api/entries/bulk")
def bulk_entries():
    items = (request.get_json(silent=True) or {}).get("entries")
    if not isinstance(items, list):
        raise ApiError("'entries' must be a list")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ApiError("Each entry must be an object")
        user_id = str(item.get("userId") or chosen_user_id())
        d = item.get("date")
        if d is None:
            raise ApiError("Each entry requires a date")
        _, qty, morning_qty, evening_qty, price = parse_entry(d, item)
        rows.append((d, user_id, qty, morning_qty, evening_qty, price))
    for d, user_id, qty, morning_qty, evening_qty, price in rows:
        upsert(d, qty, morning_qty, evening_qty, price, user_id)
    db().commit()
    return jsonify(imported=len(rows)), 201


@app.delete("/api/entries")
def clear_entries():
    user_id = chosen_user_id()
    if user_id:
        db().execute(_sql("DELETE FROM entries WHERE userId=?"), (user_id,))
    else:
        db().execute("DELETE FROM entries")
    db().commit()
    return "", 204


# ---------- prefs ----------
@app.get("/api/prefs")
def get_prefs():
    if "username" not in session:
        has_prefs = db().execute("SELECT 1 FROM prefs LIMIT 1").fetchone() is not None
        if not has_prefs:
            return jsonify(error="Authentication required"), 401
    return jsonify({r["key"]: r["value"] for r in db().execute("SELECT * FROM prefs")})


@app.put("/api/prefs")
def put_prefs():
    data = request.get_json(silent=True) or {}
    unknown = set(data) - PREF_KEYS
    if unknown:
        raise ApiError(f"Unknown preference(s): {', '.join(sorted(unknown))}")
    for k, v in data.items():
        db().execute(
            _sql(
                "INSERT INTO prefs (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
            ),
            (k, str(v)),
        )
    db().commit()
    return jsonify({r["key"]: r["value"] for r in db().execute("SELECT * FROM prefs")})


# ---------- frontend ----------
@app.get("/")
def index():
    return send_from_directory(BASE, "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
