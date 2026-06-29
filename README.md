# Structural Health Monitoring (SHM) System

## Overview

An embedded system for continuously monitoring the structural integrity of buildings, bridges, and industrial structures. The platform combines an ESP32 sensor node with a Flask web server and a real-time browser dashboard to give maintenance engineers an always-on view of structural health.

The system collects strain, vibration, temperature, humidity, and acoustic data from physical sensors, computes a structural health score, raises threshold alerts, runs AI-powered trend analysis, and overlays live weather context to help correlate environmental loads with structural behaviour.

## Problem Statement

Infrastructure in rapidly developing regions faces significant challenges:

- Increasing urbanisation and infrastructure expansion
- Environmental stress — heavy rainfall, temperature fluctuations, humidity cycles
- Dynamic loads from traffic and human activity
- Gradual structural degradation that often goes unnoticed until severe damage occurs

Traditional monitoring is reactive rather than proactive, leading to costly emergency repairs and potential safety hazards.

## Solution

The SHM platform provides:

- **Real-time data acquisition** — continuous per-element strain, vibration, temperature, humidity and acoustic monitoring via an ESP32 node
- **Structural health scoring** — a 0–100 health index computed from all active signals, with Healthy / Warning / Critical classification
- **Threshold alerting** — per-parameter warning and critical bands; alerts are raised, updated in place, and auto-resolved when values return to safe range
- **AI trend analysis** — a ranked-cause inference engine that identifies developing issues from signal trends before thresholds are breached
- **Live weather context** — Open-Meteo integration overlays external temperature, wind, precipitation and sky conditions so engineers can correlate environmental loads with sensor readings
- **Bento-box dashboard** — a modern, responsive browser UI with dark mode, an ECharts health gauge, a strain distribution bar chart, time-series trend charts, and a live alert feed

## Technology Stack

| Layer | Technology |
|---|---|
| Sensor node | ESP32 microcontroller, HX711 (strain), DHT22 (temp/humidity), SW-420 (vibration), KY-038 (sound) |
| Firmware | Arduino C++ (ESP32) with Wi-Fi HTTP ingest |
| Backend | Python 3 · Flask 3 · SQLAlchemy · Flask-Migrate (SQLite / PostgreSQL) |
| AI / Analysis | Rule-based trend analysis and ranked-cause diagnosis engine |
| Frontend | Tailwind CSS · Apache ECharts 5 · Chart.js · Vanilla JS |
| External APIs | Open-Meteo (weather, no key required) |

## Key Features

- ✅ Per-element strain monitoring (independent sensors per structural member)
- ✅ Real-time 0–100 structural health score with ECharts gauge
- ✅ Warning and critical threshold bands per sensor parameter
- ✅ Ranked AI cause inference from trend patterns
- ✅ Open-Meteo live weather context card
- ✅ Bento-box dashboard layout with dark mode
- ✅ Strain distribution bar chart per structural element
- ✅ Configurable time-range trend charts (1 h / 6 h / 24 h / 7 d)
- ✅ Alert lifecycle (raised → updated in place → auto-resolved)
- ✅ Collapsible sidebar with active-alert badge
- ✅ ESP32 firmware with Wi-Fi ingest

## Project Structure

```
Structural_Health_Monitoring/
├── README.md                   # This file
├── SHM_ESP32 FIRMWARE.ino      # ESP32 Arduino firmware
└── SHM_SERVER/                 # Flask web server + dashboard
    ├── README.md               # Server-specific setup and API docs
    ├── run.py                  # Server entry point (port 2000)
    ├── config.py               # Thresholds, DB URI, GPS coords for weather
    ├── requirements.txt
    ├── .env.example
    ├── migrations/             # Alembic database migrations
    └── app/
        ├── models.py           # Device, StructuralElement, Sample, Alert, HealthScore
        ├── routes/             # dashboard, sensor, alerts, api_v2 blueprints
        ├── services/           # health_score, alert_engine, trend_analysis, diagnosis
        ├── static/main.js      # Dashboard JS (polling, ECharts, Chart.js, weather)
        └── templates/
            └── dashboard.html  # Bento-box dashboard template
```

## Quick Start

```bash
# 1. Create and activate a virtual environment
cd Structural_Health_Monitoring
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r SHM_SERVER/requirements.txt

# 3. Configure environment (optional — sensible defaults are built in)
cp SHM_SERVER/.env.example SHM_SERVER/.env

# 4. Apply database migrations
cd SHM_SERVER
FLASK_APP=run.py ../.venv/bin/flask db upgrade

# 5. Seed demo device and structural elements
FLASK_APP=run.py ../.venv/bin/flask seed-demo

# 6. Start the server
../.venv/bin/python3 run.py
```

Open **http://localhost:2000** in your browser.

To generate a continuous stream of simulated sensor readings (in a second terminal):

```bash
cd SHM_SERVER
FLASK_APP=run.py ../.venv/bin/flask simulate
```

See `SHM_SERVER/README.md` for full API documentation and configuration details.

## ESP32 Firmware

The `SHM_ESP32 FIRMWARE.ino` sketch connects the ESP32 to Wi-Fi and posts sensor readings to `/api/v2/ingest` on the server. Configure the SSID, password, and server IP in the sketch before flashing.

## Configuration

Key settings in `SHM_SERVER/config.py` (overridable via `.env`):

| Variable | Default | Purpose |
|---|---|---|
| `DEVICE_LAT` | `-1.2921` | Latitude for Open-Meteo weather fetch |
| `DEVICE_LON` | `36.8219` | Longitude for Open-Meteo weather fetch |
| `DATABASE_URL` | `sqlite:///shm.db` | Database connection string |
| `GEMINI_API_KEY` | *(empty)* | Optional — enables AI analyst service |

Strain, temperature, humidity, vibration, and sound thresholds are defined in `Config.THRESHOLD_SPECS` in `config.py`.

## Project Status

**Active development — Phase 2 complete.**

- Phase 1 ✅ — Flask backend, per-element data model, health scoring, alerting, v2 REST API
- Phase 2 ✅ — AI trend analysis, ranked cause inference, bento dashboard UI, ECharts visualisations, Open-Meteo weather integration, dark mode, ESP32 firmware
- Phase 3 🔄 — Production hardening, multi-device support, FFT vibration analysis, mobile app

## License

[Specify your project licence here]

## Contact

For questions or collaboration inquiries, please reach out to the project team.

---

**Last updated:** June 2026
