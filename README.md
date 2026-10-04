# 🥛 MilkLog — Daily Milk Tracker

**Version:** 1.0  
**Type:** Single-file Progressive Web App (PWA)  
**File:** `index.html`

---

## Overview

MilkLog is a mobile-first web app for tracking daily milk consumption and calculating costs. It runs entirely in the browser with no backend — all data is stored locally on the user's device via `localStorage`.

---

## Features

### 📅 Today Tab
- Log milk entries by date, quantity (litres), and price per litre
- View today's consumption at a glance
- Dashboard stats: today's quantity, month total, month cost, days logged
- Recent entries list (last 7) with delete option

### 🗓 Calendar Tab
- Monthly calendar view with entry indicators
- Tap any day to see entry details
- Navigate between months

### 📊 Monthly Tab
- Monthly summary: total litres, total cost, average per day, days logged
- Weekly trend bar chart (weeks 1–5)
- Full entry table for the selected month
- Year-at-a-glance summary table

### ⚙️ Settings Tab
- Set a default price per litre (used when no price is entered)
- Choose milk type label (Cow, Buffalo, Toned, Full Cream, Skimmed, Other)
- Export all data as a `.csv` file
- Import data from a `.csv` file
- Clear all data

---

## Data Storage

All data is stored in `localStorage` under two keys:

| Key | Contents |
|---|---|
| `milktracker_entries` | JSON object keyed by date (`YYYY-MM-DD`), each with `qty`, `price`, `saved` |
| `milktracker_prefs` | JSON object with `defaultPrice` and `milkType` |

No data is sent to any server.

---

## CSV Format

Exports and imports use the following structure:

```
Date,Quantity (L),Price per L,Total Cost
2025-06-01,1.5,60,90.00
```

---

## Installing as a PWA

| Platform | Steps |
|---|---|
| Android Chrome | Tap ⋮ menu → "Add to Home screen" |
| iPhone Safari | Tap Share → "Add to Home Screen" |
| Desktop Chrome | Click the install icon in the address bar |

---

## Tech Stack

- **HTML/CSS/JS** — single self-contained file, no build step required
- **Fonts:** Playfair Display (headings), DM Sans (body) via Google Fonts
- **Storage:** Browser `localStorage`
- **No dependencies** — no frameworks, no npm, no server

---

## Usage

Simply open `index.html` in any modern browser. No installation or setup needed.
