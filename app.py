"""MilkLog REST API — single-file Flask + SQLite backend.

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
import re
import sqlite3
import time
from datetime import date as Date
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory

BASE = Path(__file__).parent
DB_PATH = BASE / "milklog.db"
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
PREF_KEYS = {"defaultPrice", "milkType"}

app = Flask(__name__, static_folder=None)


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


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS entries (
                date  TEXT PRIMARY KEY,           -- YYYY-MM-DD
                qty   REAL NOT NULL CHECK (qty > 0),
                price REAL NOT NULL CHECK (price >= 0),
                saved INTEGER NOT NULL            -- epoch ms
            );
            CREATE TABLE IF NOT EXISTS prefs (key TEXT PRIMARY KEY, value TEXT);
            """
        )


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
def cors(resp):  # lets the page work when opened from file:// or another origin
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, PUT, POST, DELETE, OPTIONS"
    return resp


def valid_date(s):
    try:
        return Date.fromisoformat(s).isoformat() == s
    except (TypeError, ValueError):
        raise ApiError(f"Invalid date '{s}', expected YYYY-MM-DD")


def parse_entry(d, data):
    """Validate one entry payload and return a (date, qty, price) tuple."""
    valid_date(d)
    try:
        qty, price = float(data["qty"]), float(data["price"])
    except (KeyError, TypeError, ValueError):
        raise ApiError("'qty' and 'price' must be numbers")
    if not 0 < qty <= 100:
        raise ApiError("'qty' must be between 0 and 100 litres")
    if not 0 <= price <= 10000:
        raise ApiError("'price' must be between 0 and 10000")
    return d, qty, price


def upsert(d, qty, price):
    db().execute(
        "INSERT INTO entries (date, qty, price, saved) VALUES (?,?,?,?) "
        "ON CONFLICT(date) DO UPDATE SET qty=excluded.qty, price=excluded.price, saved=excluded.saved",
        (d, qty, price, int(time.time() * 1000)),
    )


def get_entry(d):
    return dict(db().execute("SELECT * FROM entries WHERE date=?", (d,)).fetchone())


# ---------- entries ----------
@app.get("/api/health")
def health():
    return jsonify(status="ok")


@app.get("/api/entries")
def list_entries():
    month = request.args.get("month")
    if month:
        if not MONTH_RE.match(month):
            raise ApiError("'month' must be YYYY-MM")
        rows = db().execute("SELECT * FROM entries WHERE date LIKE ? ORDER BY date", (month + "-%",))
    else:
        rows = db().execute("SELECT * FROM entries ORDER BY date")
    return jsonify([dict(r) for r in rows])


@app.put("/api/entries/<d>")
def put_entry(d):
    _, qty, price = parse_entry(d, request.get_json(silent=True) or {})
    upsert(d, qty, price)
    db().commit()
    return jsonify(get_entry(d))


@app.delete("/api/entries/<d>")
def delete_entry(d):
    valid_date(d)
    cur = db().execute("DELETE FROM entries WHERE date=?", (d,))
    db().commit()
    if not cur.rowcount:
        raise ApiError("No entry for that date", 404)
    return "", 204


@app.post("/api/entries/bulk")
def bulk_entries():
    items = (request.get_json(silent=True) or {}).get("entries")
    if not isinstance(items, list):
        raise ApiError("'entries' must be a list")
    rows = [parse_entry(i.get("date") if isinstance(i, dict) else None, i if isinstance(i, dict) else {}) for i in items]
    for row in rows:  # all-or-nothing: validation above runs before any write
        upsert(*row)
    db().commit()
    return jsonify(imported=len(rows)), 201


@app.delete("/api/entries")
def clear_entries():
    db().execute("DELETE FROM entries")
    db().commit()
    return "", 204


# ---------- prefs ----------
@app.get("/api/prefs")
def get_prefs():
    return jsonify({r["key"]: r["value"] for r in db().execute("SELECT * FROM prefs")})


@app.put("/api/prefs")
def put_prefs():
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
