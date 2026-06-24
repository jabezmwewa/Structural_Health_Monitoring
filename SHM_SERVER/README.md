# SHM Server

Flask backend for the Structural Health Monitoring (SHM) system. It ingests
time-series readings from the ESP32 node, stores them, computes a health score,
raises threshold alerts, and serves the monitoring dashboard.

## Requirements

- Python 3.12+
- Dependencies in [`requirements.txt`](requirements.txt)

## Setup

```bash
# from this directory (SHM_SERVER/)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# configure environment (optional — sensible defaults are built in)
cp .env.example .env               # then edit values as needed
```

## Run

```bash
python run.py
```

The server starts on <http://localhost:2000>. The SQLite database
(`instance/shm.db`) is created automatically on first start.

## API

| Method | Path                            | Purpose                                        |
|--------|---------------------------------|------------------------------------------------|
| POST   | `/api/data`                     | Ingest a reading from the device               |
| GET    | `/api/latest`                   | Most recent reading                            |
| GET    | `/api/readings?limit=N`         | Last N readings (chronological, for charts)    |
| GET    | `/api/alerts?limit=N&resolved=` | Recent alerts                                  |
| PATCH  | `/api/alerts/<id>/resolve`      | Mark an alert resolved                         |
| GET    | `/`                             | Dashboard UI                                   |

### Example: post a reading

```bash
curl -X POST http://localhost:2000/api/data \
  -H "Content-Type: application/json" \
  -d '{"strain": 120, "temperature": 24.5, "humidity": 55, "pressure": 101, "vibration": 3.2}'
```

## Project layout

```
SHM_SERVER/
├── config.py            # Config: thresholds, DB URI, env loading
├── run.py               # entrypoint (port 2000)
├── app/
│   ├── __init__.py      # app factory, blueprint registration
│   ├── models.py        # SensorReading, HealthScore, Alert
│   ├── routes/          # sensor, dashboard, alerts blueprints
│   └── services/        # health_score, alert_engine, ai_analyst
├── templates/dashboard.html
└── static/main.js       # live polling + charts (single source of truth)
```

## Notes

- `instance/` (the local SQLite DB) and `.env` are git-ignored; do not commit them.
- The AI analyst (`app/services/ai_analyst.py`) is disabled unless `GEMINI_API_KEY`
  is set, and is not yet wired into any route.
