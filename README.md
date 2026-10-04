# 🥛 MilkLog — Daily Milk Tracker

**Version:** 2.0
**Type:** Mobile-first web app with a Flask REST API backend
**Files:** `app.py` (backend), `index.html` (frontend), `requirements.txt`

---

## Overview

MilkLog tracks daily milk consumption and calculates costs. The frontend is a single HTML file; data is stored in a SQLite database through a Flask REST API, so it is shared across every device that connects to the server.

```
Browser (index.html)  ──fetch/JSON──▶  Flask API (app.py)  ──▶  milklog.db (SQLite)
```

---

## Quick Start

```bash
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000**. Flask serves `index.html` itself, and `milklog.db` is created automatically on first run.

Sign in with the first-run administrator account: username `admin`, password `admin123`. You can create additional accounts from the login screen. Set `MILKLOG_ADMIN_USERNAME` and `MILKLOG_ADMIN_PASSWORD` before the first run to choose different initial credentials. Set `SECRET_KEY` to a long random value to keep sessions valid across server restarts. Change the default password before allowing other devices to connect.

To use it on a phone, connect to the same Wi-Fi and open `http://<your-computer-IP>:5000`.

---

## Features

| Tab | What it does |
|---|---|
| 📅 Today | Log entries (date, litres, price/L), dashboard stats, last 7 entries with delete |
| 🗓 Calendar | Monthly calendar with entry indicators, tap a day for details |
| 📊 Monthly | Totals, daily average, weekly bar chart, entry table, year summary |
| ⚙️ Settings | Default price, milk type, CSV export/import, clear all data |

---

## REST API

Base URL: `/api` · Format: JSON · Dates: `YYYY-MM-DD`

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Server status check |
| POST | `/api/login` | Sign in with username and password |
| POST | `/api/register` | Create an account |
| POST | `/api/logout` | End the current session |
| GET | `/api/me` | Get the current signed-in account |
| GET | `/api/entries` | List all entries (optional `?month=YYYY-MM`) |
| PUT | `/api/entries/<date>` | Create or update an entry |
| DELETE | `/api/entries/<date>` | Delete an entry (404 if none exists) |
| POST | `/api/entries/bulk` | Import many entries; all-or-nothing |
| DELETE | `/api/entries` | Delete all entries |
| GET | `/api/prefs` | Read settings |
| PUT | `/api/prefs` | Update `defaultPrice` and/or `milkType` |

### Examples

```bash
# Create or update an entry
curl -X PUT localhost:5000/api/entries/2026-10-04 \
  -H "Content-Type: application/json" -d '{"qty": 1.5, "price": 60}'

# List October entries
curl "localhost:5000/api/entries?month=2026-10"

# Bulk import
curl -X POST localhost:5000/api/entries/bulk -H "Content-Type: application/json" \
  -d '{"entries":[{"date":"2026-10-01","qty":1,"price":60}]}'
```

### Entry object

```json
{ "date": "2026-10-04", "qty": 1.5, "price": 60.0, "saved": 1791102525127 }
```

`saved` is the last-modified time in epoch milliseconds.

### Validation and errors

| Rule | Limit |
|---|---|
| `qty` | greater than 0 and at most 100 litres |
| `price` | 0 to 10000 |
| `date` | must be a real calendar date |
| `prefs` keys | only `defaultPrice`, `milkType` |

Data and preference endpoints require a signed-in session. Errors return JSON: `{"error": "message"}` with status 400 (invalid input), 401 (not signed in), 404 or 405.

---

## Database

SQLite file `milklog.db`, next to `app.py`.

| Table | Columns |
|---|---|
| `entries` | `date` (PK), `qty`, `price`, `saved` |
| `prefs` | `key` (PK), `value` |

To back up your data, copy `milklog.db`.

---

## Migrating from the localStorage version

On first load, if the server has no entries and the browser holds data from v1.0 (`milktracker_entries`), the app uploads it automatically, once. No action needed.

## Offline behaviour

If the server is unreachable, the app shows the last saved copy and displays a warning. Saving, deleting, and importing are disabled until the server is back.

---

## CSV Format

Used for export and import (Settings tab):

```
Date,Quantity (L),Price per L,Total Cost
2026-10-01,1.5,60,90.00
```

---

## Tech Stack

- **Frontend:** HTML, CSS, vanilla JS (single file); Playfair Display and DM Sans via Google Fonts
- **Backend:** Python 3, Flask
- **Database:** SQLite (standard library `sqlite3`)

---

## Notes and Limitations

- **Shared household data.** Authentication gates the app and its APIs; accounts on this installation can access the same household records.
- **Development server.** `app.py` runs with `debug=True`. For production, set `debug=False` and use a WSGI server such as `gunicorn app:app`.
- **Development server.** `app.py` runs with `debug=True`. For production, set `debug=False` and use a WSGI server such as `gunicorn app:app`.
- **Static hosting no longer works.** GitHub Pages and Netlify can't run Flask; the server must be running somewhere the app can reach.
- **Opening `index.html` directly** (`file://`) works, but only while `app.py` is running on `localhost:5000`.
