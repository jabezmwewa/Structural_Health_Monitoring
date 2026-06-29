# SHM Server

Flask backend for the Structural Health Monitoring (SHM) system. Ingests time-series readings from the ESP32 node, stores them in a relational database, computes a structural health score, manages threshold alerts, runs AI trend analysis, fetches live weather context, and serves the monitoring dashboard.

## Requirements

- Python 3.12+
- Dependencies listed in [`requirements.txt`](requirements.txt)

## Setup

```bash
# From the project root (Structural_Health_Monitoring/)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r SHM_SERVER/requirements.txt

# Configure environment (optional — sensible defaults are built in)
cp .env.example .env               # then edit values as needed
```

## Environment Variables

Copy `.env.example` to `.env` and adjust:

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `dev-secret-…` | Flask session secret |
| `FLASK_DEBUG` | `true` | Debug mode — set `false` in production |
| `DATABASE_URL` | `sqlite:///shm.db` | DB connection string; swap for PostgreSQL in production |
| `GEMINI_API_KEY` | *(empty)* | Optional — enables the Gemini AI analyst service |
| `DEVICE_LAT` | `-1.2921` | Latitude of the monitored structure (for Open-Meteo weather) |
| `DEVICE_LON` | `36.8219` | Longitude of the monitored structure |

## Database

Schema is managed by Flask-Migrate (Alembic). Create or update the local database:

```bash
cd SHM_SERVER
FLASK_APP=run.py ../.venv/bin/flask db upgrade
```

Run this once before the first start, and again after pulling changes that add new migrations. To generate a migration after editing models:

```bash
FLASK_APP=run.py ../.venv/bin/flask db migrate -m "describe the change"
FLASK_APP=run.py ../.venv/bin/flask db upgrade
```

## Running

```bash
cd SHM_SERVER
FLASK_APP=run.py ../.venv/bin/flask seed-demo   # create demo device + elements (idempotent)
../.venv/bin/python3 run.py                      # start server on port 2000
```

Open **http://localhost:2000** in your browser.

To stream simulated sensor data while the server is running (separate terminal):

```bash
cd SHM_SERVER
FLASK_APP=run.py ../.venv/bin/flask simulate
```

> **Note:** Use the explicit `../.venv/bin/python3` path rather than the system `python3` to ensure the correct virtual environment is always used.

## Dashboard

The dashboard at `/` is a single-page bento-box UI with:

- **Health gauge** — ECharts dial showing the 0–100 structural health score with colour-coded zones (red 0–30, amber 30–60, green 60–100)
- **Strain distribution** — ECharts horizontal bar chart showing current microstrain per structural element, with warning and critical reference lines
- **Element cards** — per-element status pills and animated strain progress bars
- **Environment sensors** — live temperature, humidity, vibration, and sound readings
- **Weather context** — external conditions fetched from Open-Meteo (no API key required) for the configured device coordinates
- **AI analysis** — ranked likely-cause cards derived from signal trends and patterns
- **Trend charts** — Chart.js time-series for strain (per element) and temperature/humidity, with 1 h / 6 h / 24 h / 7 d range selector
- **Alert feed** — active and historical alerts with one-click resolve
- **Dark mode** — system-preference-aware, persisted to localStorage
- **Responsive sidebar** — desktop fixed, mobile slide-in drawer with active alert badge

Auto-refresh: sensor snapshot and alerts every 5 s; AI analysis every 30 s; weather every 10 min.

## API Reference

### Legacy endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/data` | Ingest a reading from the legacy single-sensor path |
| `GET` | `/api/latest` | Most recent legacy reading |
| `GET` | `/api/readings?limit=N` | Last N readings |
| `GET` | `/api/alerts?limit=N&resolved=` | Recent alerts |
| `PATCH` | `/api/alerts/<id>/resolve` | Mark an alert resolved |

### v2 API (per-element, recommended)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v2/ingest` | Ingest a per-element sample (env signals + strain per element) |
| `GET` | `/api/v2/latest` | Current snapshot: per-element status, health score, alert count |
| `GET` | `/api/v2/history` | Downsampled time-series for trend charts |
| `GET` | `/api/v2/elements` | List all structural elements for a device |
| `GET` | `/api/v2/alerts` | Alerts with element names (active by default) |
| `GET` | `/api/v2/analysis` | AI trend analysis and ranked likely causes |
| `GET` | `/api/v2/weather` | Live weather proxy from Open-Meteo for the device location |

#### Query parameters — `/api/v2/history`

| Parameter | Default | Description |
|---|---|---|
| `hours` | `24` | Lookback window in hours |
| `element_id` | *(all)* | Filter to one structural element |
| `max_points` | `200` | Downsample to at most this many points |

#### Query parameters — `/api/v2/alerts`

| Parameter | Default | Description |
|---|---|---|
| `active` | `true` | `true` = unresolved only, `false` = all |
| `element_id` | *(all)* | Filter to one element |
| `limit` | `50` | Max rows returned |

### Example: ingest a sample via curl

```bash
curl -X POST http://localhost:2000/api/v2/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "temperature": 24.5,
    "humidity": 55,
    "vibration": 3.2,
    "sound": 41,
    "strains": [
      { "element": "Column A", "microstrain": 120 },
      { "element": "Column B", "microstrain": 95  },
      { "element": "Slab 1",   "microstrain": 85  }
    ]
  }'
```

### Example: check weather proxy

```bash
curl http://localhost:2000/api/v2/weather
```

Returns the raw Open-Meteo current-conditions block for the configured device location. No external API key is required.

## Sensor Thresholds

Thresholds are defined in `config.py` under `Config.THRESHOLD_SPECS`. Each parameter supports up to four bands:

```
crit_low → warn_low → [OK zone] → warn_high → crit_high
```

| Parameter | Warning | Critical |
|---|---|---|
| Strain (μm/m) | > 400 | > 500 |
| Temperature (°C) | < 10 or > 40 | < 5 or > 45 |
| Humidity (%) | < 30 or > 75 | < 20 or > 85 |
| Vibration (mm/s) | > 15 | > 25 |
| Sound (dB) | > 70 | > 85 |

## Project Layout

```
SHM_SERVER/
├── run.py                      # Entry point — starts Flask on port 2000
├── config.py                   # Config: thresholds, DB URI, GPS coords, API keys
├── requirements.txt
├── .env.example
├── migrations/                 # Alembic migration scripts
└── app/
    ├── __init__.py             # App factory and blueprint registration
    ├── models.py               # ORM models: Device, StructuralElement, Sample,
    │                           #   StrainMeasurement, Alert, HealthScore
    ├── commands.py             # CLI commands: seed-demo, simulate
    ├── routes/
    │   ├── dashboard.py        # GET / — renders dashboard.html
    │   ├── sensor.py           # Legacy ingest + read endpoints
    │   ├── alerts.py           # Alert resolve endpoint
    │   └── api_v2.py           # v2 REST API (latest, history, alerts, analysis, weather)
    ├── services/
    │   ├── health_score.py     # 0–100 health index calculation
    │   ├── alert_engine.py     # Threshold evaluation and alert lifecycle
    │   ├── evaluation.py       # Per-value status classification (ok/warning/critical)
    │   ├── trend_analysis.py   # Signal trend feature extraction (slope, variance, drift)
    │   ├── diagnosis.py        # Ranked likely-cause inference from trend features
    │   └── ai_analyst.py       # Gemini AI analyst (requires GEMINI_API_KEY)
    ├── static/
    │   └── main.js             # Dashboard: polling, ECharts gauge + strain dist,
    │                           #   Chart.js trends, dark mode, sidebar, weather
    └── templates/
        └── dashboard.html      # Bento-box dashboard (Tailwind + ECharts + Chart.js)
```

## Notes

- `instance/` (the local SQLite database file) and `.env` are git-ignored; do not commit them.
- The Gemini AI analyst (`services/ai_analyst.py`) is disabled unless `GEMINI_API_KEY` is set in `.env`.
- Open-Meteo is completely free and requires no API key. Coordinates default to Nairobi; set `DEVICE_LAT` and `DEVICE_LON` in `.env` to match the actual structure location.
- For production, set `FLASK_DEBUG=false`, use a strong `SECRET_KEY`, and switch `DATABASE_URL` to PostgreSQL or MySQL.
