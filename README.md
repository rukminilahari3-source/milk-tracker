# 🥛 MilkLog — Daily Milk Tracker

**Version:** 2.0
**Type:** Mobile-first web app with a Flask REST API backend
**Files:** `app.py` (backend), `index.html` (frontend), `requirements.txt`

---

## Overview

MilkLog tracks daily milk consumption and calculates costs. The frontend is a single HTML file; data is stored through a Flask REST API in SQLite for local development or PostgreSQL when `DATABASE_URL` is configured.

```
Browser (index.html)  ──fetch/JSON──▶  Flask API (app.py)  ──▶  SQLite (local) or PostgreSQL (hosted)
```

---

## Quick Start

```bash
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000**. Flask serves `index.html` itself, and `milklog.db` is created automatically on first run.

The current Flask API does not implement login or access control. Do not deploy it with private data until authentication is added; restricting CORS does not stop direct API requests.

To use it on a phone, connect to the same Wi-Fi and open `http://<your-computer-IP>:5000`.

## Deploying with GitHub Pages and Render

GitHub Pages serves the frontend only; it cannot run the Flask API. This repository includes a Render Blueprint (`render.yaml`) for deploying the API on Render's free web-service plan. Free web services do not have persistent disks, so use an external PostgreSQL provider for records that must survive service restarts.

**Privacy warning:** the current API has no authentication, so anyone who knows its public URL can read, change, or delete entries. The CORS allowlist only controls which browser origins can read responses; it is not access control. Do not use this public deployment for private household data until authentication is implemented.

1. Create a PostgreSQL database with a provider that offers a free plan, and copy its connection string. Free database plans have provider-specific storage, inactivity, and retention limits; check those before relying on the database as your only backup.
2. Push the repository to GitHub and create or update a Blueprint in Render using this repository and its `render.yaml`. Pushing to GitHub Pages alone does not deploy the API. When prompted, set `DATABASE_URL` to the PostgreSQL connection string. Do not commit that string to GitHub.
3. The frontend uses `https://milklog-rukminilahari3-api.onrender.com/api` on the GitHub Pages origin. If Render assigns a different service URL, update the `API` constant near the top of the script in `index.html` and push the change.
4. In the GitHub repository, enable Pages for the branch and folder that contain `index.html` (for example, the root of the `main` branch). The Render Blueprint limits browser API access to `https://rukminilahari3-source.github.io`.
5. Verify `https://milklog-rukminilahari3-api.onrender.com/api/health` returns `{"status":"ok"}`, then open the Pages URL and save a test entry.

The Render free service may sleep while idle, so the first request can take longer. Its filesystem is ephemeral; the hosted app therefore requires `DATABASE_URL` and does not use its local SQLite file. Existing `milklog.db` data is not transferred automatically; export and import it separately if it needs to be retained.

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

The current API does not require sign-in. Errors return JSON: `{"error": "message"}` with status 400 (invalid input), 404 or 405.

---

## Database

Local development uses the SQLite file `milklog.db`, next to `app.py`. Set `DATABASE_URL` to a PostgreSQL connection string to use PostgreSQL instead; the app creates its tables on startup.

| Table | Columns |
|---|---|
| `entries` | `date` (PK), `qty`, `price`, `saved` |
| `prefs` | `key` (PK), `value` |

Back up the database using the tools provided by your database provider. For local SQLite, copy `milklog.db`.

---

## Migrating from the localStorage version

On first load, if the server has no entries and the browser holds data from v1.0 (`milktracker_entries`), the app uploads it automatically, once. No action needed.

## Offline behaviour

If the API is unreachable, the app shows the last saved copy. New entries are saved on the current device and queued in browser storage; the app retries syncing them when the API becomes available or the browser comes back online. Entries still require a reachable API to appear on other devices. Deleting and importing require the API to be available.

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

- **No API authentication.** Do not expose the API with private data; anyone who can reach its URL can access the records.
- **Development server.** `app.py` runs with `debug=True`. For production, set `debug=False` and use a WSGI server such as `gunicorn app:app`.
- **Development server.** `app.py` runs with `debug=True`. For production, set `debug=False` and use a WSGI server such as `gunicorn app:app`.
- **Static hosting requires a separate API host.** GitHub Pages cannot run Flask; configure the frontend to reach a Flask server such as the Render service described above.
- **Opening `index.html` directly** (`file://`) works, but only while `app.py` is running on `localhost:5000`.
