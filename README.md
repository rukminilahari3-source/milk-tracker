# 🥛 MilkLog — Daily Milk Tracker

**Version:** 2.1 · **Type:** Mobile-first web app with a Flask REST API backend
**Files:** `app.py` (backend), `index.html` (frontend), `requirements.txt`, `render.yaml`

---

## Overview

MilkLog tracks daily milk consumption and calculates costs. The frontend is a single HTML file. Data is stored per account through a Flask REST API in SQLite (local) or PostgreSQL (hosted, when `DATABASE_URL` is set).

```
Browser (index.html)  ──fetch/JSON──▶  Flask API (app.py)  ──▶  SQLite (local) or PostgreSQL (hosted)
```

Sign-in is required. Create an account on first load; entries are stored per account and passwords are hashed.

---

## Quick Start

```
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000**. Flask serves `index.html` itself, and `milklog.db` is created automatically on first run. Register an account on the login screen, then start logging.

To use it on a phone, connect to the same Wi-Fi and open `http://<your-computer-IP>:5000`.

> If you change the database schema after `milklog.db` already exists, delete the local file and restart. `CREATE TABLE IF NOT EXISTS` does not alter existing tables.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Signs login sessions. **Required in production**; use a long random value. |
| `DATABASE_URL` | PostgreSQL connection string (hosted). Omit for local SQLite. |
| `MILKLOG_ALLOWED_ORIGINS` | Comma-separated browser origins allowed to call the API cross-site. |
| `MILKLOG_DB_PATH` | Optional path for the local SQLite file. |

---

## Deploying on Render

The recommended setup serves the page and the API from the same Render URL, so no cross-site cookie or CORS configuration is needed.

1. Create a PostgreSQL database with a provider that offers a free plan and copy its connection string. Free plans have storage, inactivity and retention limits; check them before relying on the database as your only backup.
2. Push the repository to GitHub and create or update a Blueprint in Render using `render.yaml`. When prompted, set `DATABASE_URL` and `SECRET_KEY`. Never commit either value to GitHub.
3. Open your Render service URL, for example `https://milklog-rukminilahari3-api.onrender.com/`.
4. Verify `/api/health` returns `{"status":"ok"}`.
5. Register an account and save a test entry.

Notes:
- The free Render service sleeps when idle, so the first request can be slow.
- Its filesystem is ephemeral, so the hosted app needs `DATABASE_URL`; the local SQLite file is not used.
- Existing `milklog.db` data is not transferred automatically. Use **Export CSV** locally and **Import CSV** on the hosted app.
- `milklog.db` is listed in `.gitignore` and should not be committed.

**Optional: GitHub Pages frontend.** Pages serves static files only, so the API must stay on Render, and browsers may block the session cookie across the two sites (Safari especially). Using the Render URL directly avoids this.

---

## Features

| Tab | What it does |
| --- | --- |
| 📅 Today | Log entries (date, litres, price/L), dashboard stats, last 7 entries with delete |
| 🗓 Calendar | Monthly calendar with entry indicators, tap a day for details |
| 📊 Monthly | Totals, daily average, weekly bar chart, entry table, year summary |
| ⚙️ Settings | Default price, milk type, CSV export/import, clear all data, logout |

---

## REST API

Base URL: `/api` · Format: JSON · Dates: `YYYY-MM-DD`

All endpoints except `/api/health`, `/api/login` and `/api/register` require sign-in (session cookie). Unauthenticated requests return `401`.

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/health` | Server status check |
| POST | `/api/register` | Create an account and sign in |
| POST | `/api/login` | Sign in with username and password |
| POST | `/api/logout` | End the current session |
| GET | `/api/me` | Get the signed-in account |
| GET | `/api/users` | List profiles owned by the account |
| POST | `/api/users` | Create a profile |
| GET | `/api/entries` | List your entries (optional `?month=YYYY-MM`) |
| PUT | `/api/entries/<date>` | Create or update an entry |
| DELETE | `/api/entries/<date>` | Delete an entry (404 if none exists) |
| POST | `/api/entries/bulk` | Import many entries; all-or-nothing |
| DELETE | `/api/entries` | Delete all your entries |
| GET | `/api/prefs` | Read settings |
| PUT | `/api/prefs` | Update `defaultPrice` and/or `milkType` |

### Examples

```
# Register (stores the session cookie in cookies.txt)
curl -c cookies.txt -X POST localhost:5000/api/register \
  -H "Content-Type: application/json" -d '{"username":"lahari","password":"secret"}'

# Create or update an entry
curl -b cookies.txt -X PUT localhost:5000/api/entries/2026-10-04 \
  -H "Content-Type: application/json" -d '{"qty": 1.5, "price": 60}'

# List October entries
curl -b cookies.txt "localhost:5000/api/entries?month=2026-10"

# Bulk import
curl -b cookies.txt -X POST localhost:5000/api/entries/bulk \
  -H "Content-Type: application/json" \
  -d '{"entries":[{"date":"2026-10-01","qty":1,"price":60}]}'
```

### Entry object

```
{ "date": "2026-10-04", "userId": "lahari", "qty": 1.5, "morningQty": 1.5,
  "eveningQty": 0, "price": 60.0, "saved": 1791102525127 }
```

`saved` is the last-modified time in epoch milliseconds. You can send either `qty`, or `morningQty` and/or `eveningQty` (then `qty` is their sum).

### Validation and errors

| Rule | Limit |
| --- | --- |
| `qty` | greater than 0 and at most 100 litres |
| `morningQty`, `eveningQty` | not negative |
| `price` | 0 to 10000 |
| `date` | must be a real calendar date |
| `prefs` keys | only `defaultPrice`, `milkType` |

Errors return JSON `{"error": "message"}` with status 400 (invalid input), 401 (not signed in), 404, 405 or 409 (username taken).

---

## Database

Local development uses the SQLite file `milklog.db`, next to `app.py`. Set `DATABASE_URL` to a PostgreSQL connection string to use PostgreSQL instead; the app creates its tables on startup.

| Table | Columns |
| --- | --- |
| `entries` | `date` + `userId` (primary key), `qty`, `morningQty`, `eveningQty`, `price`, `saved` |
| `users` | `username` (PK), `password` (hash) |
| `user_profiles` | `userId` (PK), `ownerUsername`, `createdAt` |
| `prefs` | `key` (PK), `value` (shared by all accounts) |

Back up the database with the tools provided by your database provider. For local SQLite, copy `milklog.db`.

---

## Offline behaviour

If the API is unreachable, the app shows the last saved copy. New entries are saved on the current device and queued in browser storage; the app retries syncing them when the API becomes available or the browser comes back online. Entries need a reachable API to appear on other devices. Deleting and importing require the API to be available.

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
- **Database:** SQLite (local) or PostgreSQL (hosted)

---

## Notes and Limitations

- **Development server.** `app.py` runs with `debug=True`. For production, set `debug=False` and use a WSGI server such as `gunicorn app:app`.
- **Shared preferences.** `defaultPrice` and `milkType` are stored once for the whole database, not per account.
- **Static hosting needs a separate API host.** GitHub Pages cannot run Flask; if you use it for the frontend, point the `API` constant in `index.html` at your Flask server.
- **Opening `index.html` directly** (`file://`) works only while `app.py` is running on `localhost:5000`.
