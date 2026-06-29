#!/usr/bin/env python3
"""
SHM Machine Learning Pipeline
──────────────────────────────
Detects anomalies and trends in sensor data, then outputs a ranked list
of candidate structural defects with scores and supporting evidence.

Usage:
    python3 SHM_ML/pipeline.py                 # load DB + synthetic baseline
    python3 SHM_ML/pipeline.py --no-db         # fully synthetic (no DB needed)
    python3 SHM_ML/pipeline.py --hours 72      # change analysis window
    python3 SHM_ML/pipeline.py --export csv    # also write results to CSV

Run from the project root (Structural_Health_Monitoring/).
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import textwrap
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION  ← tweak these to match your physical structure
# ─────────────────────────────────────────────────────────────────────────────

DB_PATH      = Path(__file__).parent.parent / "SHM_SERVER" / "instance" / "shm.db"
SYNTH_DAYS   = 30          # days of synthetic "healthy" data to prepend as baseline

# Threshold bands (mirror Config.THRESHOLD_SPECS in config.py)
STRAIN_WARN   = 400.0   # μm/m
STRAIN_CRIT   = 500.0
VIBR_WARN     = 15.0    # mm/s
VIBR_CRIT     = 25.0
TEMP_WARN_HI  = 40.0    # °C
HUMID_WARN_HI = 75.0    # %
SOUND_WARN    = 70.0    # dB

# Isolation Forest settings
IF_CONTAMINATION = 0.05   # expected fraction of outliers in training data
IF_N_ESTIMATORS  = 200


# ─────────────────────────────────────────────────────────────────────────────
#  DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────

def load_db(db_path: Path) -> tuple[pd.DataFrame, list[str]]:
    """
    Load samples + per-element strain from SQLite.
    Returns (wide_df, element_names).
    """
    con = sqlite3.connect(db_path)
    samples = pd.read_sql(
        "SELECT id AS sample_id, timestamp, temperature, humidity, vibration, sound "
        "FROM samples ORDER BY timestamp",
        con, parse_dates=["timestamp"],
    )
    strains = pd.read_sql(
        "SELECT sm.sample_id, e.name AS element, sm.microstrain "
        "FROM strain_measurements sm "
        "JOIN structural_elements e ON sm.element_id = e.id",
        con,
    )
    con.close()

    element_names = sorted(strains["element"].unique().tolist())
    wide = strains.pivot(index="sample_id", columns="element", values="microstrain")
    wide.columns = [f"strain_{c.replace(' ', '_')}" for c in wide.columns]

    df = samples.set_index("sample_id").join(wide).set_index("timestamp").sort_index()
    return df, element_names


# ─────────────────────────────────────────────────────────────────────────────
#  SYNTHETIC DATA GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def generate_synthetic(
    start: pd.Timestamp,
    n_days: int,
    element_names: list[str],
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate a realistic synthetic SHM baseline with:
      • Daily temperature cycle and humidity fluctuations
      • Normal strain for all elements (mean 90-110 μm/m)
      • Two brief vibration burst anomalies (simulating nearby machinery)
      • A slow drift on the first element in the final 20% of the period
        (early warning signal before the real data's rapid rise)
      • Two isolated strain spikes on the first element (micro-crack events)
    The synthetic data represents "known-healthy" operation and trains
    the Isolation Forest's baseline.
    """
    rng = np.random.default_rng(seed)
    interval_min = 10
    n = n_days * 24 * 60 // interval_min

    t = pd.date_range(start=start, periods=n, freq=f"{interval_min}min")
    hours   = np.arange(n) * interval_min / 60.0
    day_frac = (hours % 24) / 24.0

    # ── Environmental signals ──────────────────────────────────────────────
    temp = (
        22
        + 8 * np.sin(2 * np.pi * day_frac - np.pi / 2)
        + rng.normal(0, 0.6, n)
    )
    humidity = np.clip(
        63 - 0.25 * temp + 5 * np.sin(2 * np.pi * day_frac + np.pi) + rng.normal(0, 2, n),
        30, 92,
    )

    vibration = np.abs(rng.normal(2.5, 0.7, n))
    for burst_frac in [0.33, 0.71]:           # two vibration bursts
        i0 = int(n * burst_frac)
        vibration[max(0, i0 - 2) : i0 + 4] += rng.uniform(18, 26, 6)

    sound = np.clip(40 + vibration * 0.9 + rng.normal(0, 2, n), 28, 95)

    df = pd.DataFrame(
        {"temperature": temp, "humidity": humidity, "vibration": vibration, "sound": sound},
        index=t,
    )

    # ── Strain per element ─────────────────────────────────────────────────
    for i, name in enumerate(element_names):
        col  = f"strain_{name.replace(' ', '_')}"
        base = 90 + i * 10
        noise = rng.normal(0, 10, n)

        if i == 0:
            # First element gets a slow drift in the last 20% (early warning),
            # plus two isolated spike events
            onset = int(n * 0.80)
            drift = np.zeros(n)
            drift[onset:] = np.linspace(0, 80, n - onset)

            for spike_frac in [0.52, 0.87]:
                pt = int(n * spike_frac)
                noise[pt] += rng.uniform(60, 100)
        else:
            drift = np.zeros(n)

        df[col] = np.clip(base + drift + noise, 0, None)

    return df


# ─────────────────────────────────────────────────────────────────────────────
#  ANOMALY DETECTION  (Isolation Forest per sensor)
# ─────────────────────────────────────────────────────────────────────────────

def detect_anomalies(
    df: pd.DataFrame,
    n_train: int,
) -> pd.DataFrame:
    """
    For each sensor column, fit an Isolation Forest on the first `n_train`
    rows (the synthetic baseline) and score every row.

    Returns a DataFrame with columns:
        {sensor}__label  — sklearn convention: -1 = anomaly, +1 = normal
        {sensor}__score  — raw decision function (lower → more anomalous)
    """
    sensor_cols = [
        c for c in df.columns
        if c in ("temperature", "humidity", "vibration", "sound")
        or c.startswith("strain_")
    ]

    results: dict[str, pd.Series] = {}

    for col in sensor_cols:
        s = df[col].dropna()
        if len(s) < 30:
            continue

        X = s.values.reshape(-1, 1).astype(float)
        # Align train cutoff to available (non-NaN) rows
        train_cut = min(n_train, int(len(X) * 0.95))

        scaler  = RobustScaler()
        X_train = scaler.fit_transform(X[:train_cut])
        X_all   = scaler.transform(X)

        clf = IsolationForest(
            n_estimators=IF_N_ESTIMATORS,
            contamination=IF_CONTAMINATION,
            random_state=42,
            n_jobs=-1,
        )
        clf.fit(X_train)

        labels = clf.predict(X_all)
        scores = clf.decision_function(X_all)

        results[f"{col}__label"] = pd.Series(labels, index=s.index)
        results[f"{col}__score"] = pd.Series(scores, index=s.index)

    return pd.DataFrame(results, index=df.index)


# ─────────────────────────────────────────────────────────────────────────────
#  TREND ANALYSIS  (per element, OLS linear regression)
# ─────────────────────────────────────────────────────────────────────────────

def fit_trend(series: pd.Series, warn: float, crit: float) -> dict | None:
    """
    Fit OLS trend to a time series.  Returns:
        slope_per_hr  — units/hour (positive = rising)
        r2            — goodness-of-fit (0–1)
        p_value       — significance of slope
        hours_to_warn / hours_to_crit — extrapolated time to threshold
                        (0 means already past; None means trending away)
    """
    s = series.dropna()
    if len(s) < 10:
        return None

    t0    = s.index[0]
    hours = np.array([(ts - t0).total_seconds() / 3600 for ts in s.index])
    vals  = s.values.astype(float)

    slope, intercept, r, p, _ = stats.linregress(hours, vals)
    r2 = r ** 2

    def _hrs_to(level: float) -> float | None:
        if slope <= 1e-6:
            return None
        h = (level - intercept) / slope
        remaining = h - hours[-1]
        return max(round(remaining, 1), 0)

    return {
        "current":       round(float(vals[-1]), 1),
        "mean":          round(float(vals.mean()), 1),
        "max":           round(float(vals.max()), 1),
        "slope_per_hr":  round(float(slope), 3),
        "r2":            round(float(r2), 3),
        "p_value":       round(float(p), 5),
        "hours_to_warn": _hrs_to(warn),
        "hours_to_crit": _hrs_to(crit),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  FEATURE ASSEMBLY
# ─────────────────────────────────────────────────────────────────────────────

def build_features(
    df: pd.DataFrame,
    anom_df: pd.DataFrame,
    real_start: pd.Timestamp | None,
    window_h: int,
) -> dict:
    """
    Slice the analysis window, then aggregate raw stats, anomaly rates,
    and trend info into a flat dict that the defect rules consume.
    """
    if real_start is not None:
        mask = df.index >= real_start
    else:
        mask = df.index >= (df.index[-1] - pd.Timedelta(hours=window_h))

    dw = df[mask]
    aw = anom_df[mask]

    def _anom_rate(col: str) -> float:
        lbl = f"{col}__label"
        if lbl not in aw.columns:
            return 0.0
        n = aw[lbl].dropna()
        return round(float((n == -1).sum() / max(len(n), 1)), 4)

    # ── Element features ───────────────────────────────────────────────────
    strain_cols = [c for c in df.columns if c.startswith("strain_")]
    elements = []
    for col in strain_cols:
        name  = col.removeprefix("strain_").replace("_", " ")
        trend = fit_trend(dw[col], STRAIN_WARN, STRAIN_CRIT)
        if trend is None:
            continue
        elements.append({
            "name":           name,
            "col":            col,
            "current_strain": trend["current"],
            "mean_strain":    trend["mean"],
            "max_strain":     trend["max"],
            "slope_per_hr":   trend["slope_per_hr"],
            "r2":             trend["r2"],
            "p_value":        trend["p_value"],
            "hours_to_warn":  trend["hours_to_warn"],
            "hours_to_crit":  trend["hours_to_crit"],
            "anomaly_rate":   _anom_rate(col),
            "pct_above_warn": round(float((dw[col].dropna() > STRAIN_WARN).mean()), 4),
            "pct_above_crit": round(float((dw[col].dropna() > STRAIN_CRIT).mean()), 4),
        })

    # ── Environmental features ─────────────────────────────────────────────
    env = {}
    for sig, warn_hi in [
        ("temperature", TEMP_WARN_HI),
        ("humidity",    HUMID_WARN_HI),
        ("vibration",   VIBR_WARN),
        ("sound",       SOUND_WARN),
    ]:
        if sig not in dw.columns:
            continue
        s = dw[sig].dropna()
        if len(s) == 0:
            continue
        env[sig] = {
            "current":        round(float(s.iloc[-1]), 2),
            "mean":           round(float(s.mean()), 2),
            "max":            round(float(s.max()), 2),
            "anomaly_rate":   _anom_rate(sig),
            "pct_above_warn": round(float((s > warn_hi).mean()), 4),
        }

    strains_now = [e["current_strain"] for e in elements]
    return {
        "elements":            elements,
        "env":                 env,
        "differential_strain": round(max(strains_now) - min(strains_now), 1) if strains_now else 0,
        "window_hours":        window_h,
        "analysis_end":        str(dw.index[-1]) if len(dw) else "—",
        "n_readings":          len(dw),
    }


# ═════════════════════════════════════════════════════════════════════════════
#  DEFECT RULES  ←  EDIT THIS SECTION TO CUSTOMISE DETECTION LOGIC
#
#  Each rule is a plain Python function:
#      rule_*(features: dict) → (score: float, evidence: list[str])
#
#  • score: 0.0 (no indication) → 1.0 (strong). Contributions are additive;
#    clip to 1.0 at the end of each rule.  Rules with score < 0.05 are
#    suppressed from the ranked output.
#  • evidence: human-readable strings (shown under each ranked defect).
#
#  Add, remove, or edit rules freely.  Register them in DEFECT_RULES below.
# ═════════════════════════════════════════════════════════════════════════════

def rule_deflection(f: dict) -> tuple[float, list]:
    """
    Structural deflection: load-bearing element under increasing load or
    loss of stiffness.  Key signals: strong, statistically significant
    upward strain trend + sustained exceedance of warning/critical bands.
    """
    score, ev = 0.0, []
    for el in f["elements"]:
        if el["slope_per_hr"] > 1.0 and el["r2"] > 0.55 and el["p_value"] < 0.05:
            score += 0.40
            ev.append(
                f"{el['name']}: sustained upward trend "
                f"{el['slope_per_hr']:+.1f} μm/m/h (R²={el['r2']:.2f}, p={el['p_value']:.4f})"
            )
        if el["hours_to_crit"] == 0:
            score += 0.40
            if el["current_strain"] >= STRAIN_CRIT:
                ev.append(
                    f"{el['name']}: currently exceeds critical threshold "
                    f"({el['current_strain']:.0f} ≥ {STRAIN_CRIT} μm/m)"
                )
            else:
                ev.append(
                    f"{el['name']}: trend has already crossed critical ({STRAIN_CRIT} μm/m) — "
                    f"peak {el['max_strain']:.0f} μm/m, current {el['current_strain']:.0f} μm/m"
                )
        elif el["hours_to_crit"] is not None and el["hours_to_crit"] < 24:
            score += 0.30
            ev.append(
                f"{el['name']}: projected to reach critical in ≈{el['hours_to_crit']:.1f} h "
                f"at current trend rate"
            )
        if el["pct_above_warn"] > 0.15:
            score += 0.20
            ev.append(
                f"{el['name']}: {el['pct_above_warn']*100:.1f}% of readings "
                f"above warning threshold ({STRAIN_WARN} μm/m)"
            )
    return min(score, 1.0), ev


def rule_cracking(f: dict) -> tuple[float, list]:
    """
    Micro-cracking or crack propagation: anomalous strain spikes combined
    with sustained threshold exceedances.
    """
    score, ev = 0.0, []
    for el in f["elements"]:
        if el["anomaly_rate"] > 0.08:
            score += 0.30
            ev.append(
                f"{el['name']}: {el['anomaly_rate']*100:.1f}% of readings "
                f"flagged as anomalous by Isolation Forest"
            )
        if el["max_strain"] > STRAIN_CRIT:
            score += 0.35
            ev.append(
                f"{el['name']}: peak {el['max_strain']:.0f} μm/m exceeds "
                f"CRITICAL threshold ({STRAIN_CRIT} μm/m)"
            )
        elif el["max_strain"] > STRAIN_WARN:
            score += 0.20
            ev.append(
                f"{el['name']}: peak {el['max_strain']:.0f} μm/m exceeds "
                f"warning threshold ({STRAIN_WARN} μm/m)"
            )
        if el["pct_above_crit"] > 0.02:
            score += 0.20
            ev.append(
                f"{el['name']}: {el['pct_above_crit']*100:.1f}% of readings "
                f"above critical — indicates sustained crack-level stress"
            )
    return min(score, 1.0), ev


def rule_settlement(f: dict) -> tuple[float, list]:
    """
    Differential settlement: one part of the structure sinking faster
    than adjacent parts, causing asymmetric loading.
    """
    score, ev = 0.0, []
    diff = f["differential_strain"]

    if diff > 250:
        score += 0.50
        ev.append(
            f"Differential strain across elements: {diff:.0f} μm/m "
            f"(>250 is structurally significant)"
        )
    elif diff > 100:
        score += 0.25
        ev.append(f"Differential strain across elements: {diff:.0f} μm/m")

    els = f["elements"]
    if len(els) >= 2:
        by_slope = sorted(els, key=lambda e: e["slope_per_hr"], reverse=True)
        hi, lo   = by_slope[0], by_slope[-1]
        delta    = hi["slope_per_hr"] - lo["slope_per_hr"]
        if delta > 3.0:
            score += 0.35
            ev.append(
                f"Asymmetric loading rate: {hi['name']} trending "
                f"{hi['slope_per_hr']:+.1f} μm/m/h vs "
                f"{lo['name']} {lo['slope_per_hr']:+.1f} μm/m/h "
                f"(Δ = {delta:.1f})"
            )

    return min(score, 1.0), ev


def rule_creep(f: dict) -> tuple[float, list]:
    """
    Creep: slow, monotonic strain growth under sustained load, with no
    clear external trigger.  Distinguished from deflection by a lower
    slope and very high R² (smooth, not spiky).
    """
    score, ev = 0.0, []
    for el in f["elements"]:
        # Classic creep: steady, highly predictable (R² > 0.85), slow
        if 0.05 < el["slope_per_hr"] < 4.0 and el["r2"] > 0.85 and el["p_value"] < 0.01:
            score += 0.45
            ev.append(
                f"{el['name']}: smooth monotonic strain increase "
                f"{el['slope_per_hr']:+.2f} μm/m/h, R²={el['r2']:.2f} — "
                f"classic creep signature"
            )
        elif el["slope_per_hr"] > 0.05 and el["r2"] > 0.65:
            score += 0.18
            ev.append(
                f"{el['name']}: gradual upward drift {el['slope_per_hr']:+.2f} μm/m/h "
                f"(R²={el['r2']:.2f})"
            )

    # Creep more likely when anomaly rate is low (loading is steady, not spiky)
    total_anom = sum(e["anomaly_rate"] for e in f["elements"])
    if score > 0 and total_anom < 0.05:
        score += 0.10
        ev.append("Low anomaly rate consistent with steady loading (not sudden impact)")

    return min(score, 1.0), ev


def rule_corrosion_risk(f: dict) -> tuple[float, list]:
    """
    Corrosion: sustained high humidity + elevated temperatures accelerate
    corrosion of reinforcement bars, which shows up as gradual anomalous
    strain in column elements.
    """
    score, ev = 0.0, []
    hum  = f["env"].get("humidity", {})
    temp = f["env"].get("temperature", {})

    if hum.get("mean", 0) > 70:
        score += 0.25
        ev.append(f"Mean humidity {hum['mean']:.1f}% — above 70% accelerates corrosion")
    if hum.get("pct_above_warn", 0) > 0.10:
        score += 0.20
        ev.append(
            f"Humidity above warning ({HUMID_WARN_HI}%) for "
            f"{hum['pct_above_warn']*100:.0f}% of the analysis window"
        )
    if temp.get("max", 0) > 35 and hum.get("mean", 0) > 60:
        score += 0.15
        ev.append(
            f"High-temperature / high-humidity combination "
            f"({temp['max']:.1f}°C peak, {hum['mean']:.1f}% mean humidity)"
        )

    for el in f["elements"]:
        if "column" in el["name"].lower() and el["anomaly_rate"] > 0.05:
            score += 0.20
            ev.append(
                f"{el['name']}: {el['anomaly_rate']*100:.1f}% anomalous readings "
                f"in sustained-humidity environment"
            )

    return min(score, 1.0), ev


def rule_vibration_fatigue(f: dict) -> tuple[float, list]:
    """
    Vibration-induced fatigue: repeated high-amplitude vibration events
    can cause fatigue cracking, especially at welds and joints.
    """
    score, ev = 0.0, []
    vib = f["env"].get("vibration", {})

    if vib.get("max", 0) > VIBR_CRIT:
        score += 0.45
        ev.append(
            f"Vibration peak {vib['max']:.1f} mm/s exceeds CRITICAL "
            f"level ({VIBR_CRIT} mm/s)"
        )
    elif vib.get("max", 0) > VIBR_WARN:
        score += 0.30
        ev.append(
            f"Vibration peak {vib['max']:.1f} mm/s exceeds warning "
            f"level ({VIBR_WARN} mm/s)"
        )
    if vib.get("anomaly_rate", 0) > 0.04:
        score += 0.25
        ev.append(
            f"Vibration anomaly rate {vib['anomaly_rate']*100:.1f}% "
            f"(Isolation Forest) — repeated burst events detected"
        )
    if vib.get("pct_above_warn", 0) > 0.01:
        score += 0.15
        ev.append(
            f"Vibration above {VIBR_WARN} mm/s for "
            f"{vib['pct_above_warn']*100:.1f}% of the period"
        )

    return min(score, 1.0), ev


# ── Defect registry — add, remove, or reorder entries here ───────────────────
DEFECT_RULES: list[tuple[str, callable, str]] = [
    (
        "Structural Deflection",
        rule_deflection,
        "Sustained high strain with strong upward trend in load-bearing elements",
    ),
    (
        "Micro-cracking / Crack Propagation",
        rule_cracking,
        "Sudden strain spikes and elevated anomaly rate suggesting crack development",
    ),
    (
        "Differential Settlement",
        rule_settlement,
        "Uneven strain distribution across elements indicating foundation movement",
    ),
    (
        "Creep",
        rule_creep,
        "Slow, steady, monotonic strain growth under constant load",
    ),
    (
        "Corrosion Risk",
        rule_corrosion_risk,
        "High humidity and temperature combination accelerating rebar corrosion",
    ),
    (
        "Vibration Fatigue",
        rule_vibration_fatigue,
        "Repeated high-amplitude vibration events causing fatigue cracking",
    ),
]

# ═════════════════════════════════════════════════════════════════════════════
#  END OF DEFECT RULES
# ═════════════════════════════════════════════════════════════════════════════


# ─────────────────────────────────────────────────────────────────────────────
#  SCORING AND RANKING
# ─────────────────────────────────────────────────────────────────────────────

def rank_defects(features: dict) -> list[dict]:
    results = []
    for name, fn, description in DEFECT_RULES:
        try:
            score, evidence = fn(features)
        except Exception as exc:
            score, evidence = 0.0, [f"[rule error: {exc}]"]
        if score >= 0.05:
            results.append(
                {
                    "defect":      name,
                    "score":       round(score, 3),
                    "pct":         round(score * 100),
                    "confidence":  "HIGH" if score >= 0.65 else ("MODERATE" if score >= 0.35 else "LOW"),
                    "description": description,
                    "evidence":    evidence,
                }
            )
    return sorted(results, key=lambda x: x["score"], reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
#  OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

W = 72   # report width

def _hr(ch="─"): return ch * W

def print_report(
    features: dict,
    ranked:   list[dict],
    df:       pd.DataFrame,
    anom_df:  pd.DataFrame,
    real_start: pd.Timestamp | None,
) -> None:

    print()
    print("╔" + "═" * W + "╗")
    print("║" + "  SHM  ·  DEFECT RANKING REPORT".center(W) + "║")
    print("║" + f"  Generated {datetime.now():%Y-%m-%d %H:%M:%S}".ljust(W) + "║")
    print("║" + f"  Analysis window ends: {features['analysis_end']}".ljust(W) + "║")
    print("║" + f"  Readings in window:   {features['n_readings']}".ljust(W) + "║")
    print("╚" + "═" * W + "╝")

    # ── Sensor snapshot ────────────────────────────────────────────────────
    print(f"\n{_hr()}")
    print("  SENSOR SNAPSHOT")
    print(_hr())
    fmt = "  {:<20}  {:>9}  {:>9}  {:>9}  {:>9}  {:>8}"
    print(fmt.format("Sensor", "Current", "Mean", "Max", "Trend/h", "Anom%"))
    print(fmt.format("──────", "───────", "────", "───", "───────", "─────"))

    for el in features["elements"]:
        slope_str = f"{el['slope_per_hr']:+.1f}μ" if abs(el["slope_per_hr"]) > 0.01 else "stable"
        tag = ""
        if el["current_strain"] >= STRAIN_CRIT or el["max_strain"] >= STRAIN_CRIT:
            tag = " ◀ CRITICAL"
        elif el["current_strain"] >= STRAIN_WARN or el["max_strain"] >= STRAIN_WARN:
            tag = " ◀ WARNING"
        print(
            fmt.format(
                el["name"],
                f"{el['current_strain']:.0f}μ",
                f"{el['mean_strain']:.0f}μ",
                f"{el['max_strain']:.0f}μ",
                slope_str,
                f"{el['anomaly_rate']*100:.1f}%",
            ) + tag
        )

    print()
    env = features["env"]
    for sig, unit, warn in [
        ("temperature", "°C",   TEMP_WARN_HI),
        ("humidity",    "%",    HUMID_WARN_HI),
        ("vibration",   "mm/s", VIBR_WARN),
        ("sound",       "dB",   SOUND_WARN),
    ]:
        if sig not in env:
            continue
        s   = env[sig]
        tag = f"  ◀ WARNING (>{warn})" if s["max"] > warn else ""
        print(
            fmt.format(
                sig.capitalize(),
                f"{s['current']:.1f}{unit}",
                f"{s['mean']:.1f}{unit}",
                f"{s['max']:.1f}{unit}",
                "—",
                f"{s['anomaly_rate']*100:.1f}%",
            ) + tag
        )

    print(f"\n  Differential strain across elements: {features['differential_strain']:.0f} μm/m")

    # ── Ranked defect list ─────────────────────────────────────────────────
    print(f"\n{_hr('═')}")
    print("  RANKED DEFECT CANDIDATES")
    print(_hr("═"))

    if not ranked:
        print("\n  No defects detected above minimum threshold. Structure appears healthy.\n")
    else:
        for i, d in enumerate(ranked, 1):
            bar  = "█" * int(d["pct"] * 0.30) + "░" * (30 - int(d["pct"] * 0.30))
            conf_colour = {"HIGH": "!!!", "MODERATE": " ! ", "LOW": "   "}[d["confidence"]]
            print(f"\n  #{i}  [{conf_colour}]  {d['defect']}")
            print(f"       {bar}  {d['score']:.2f} / 1.00  ({d['confidence']})")
            print(f"       {d['description']}")
            for ev_line in d["evidence"]:
                wrapped = textwrap.fill(
                    f"• {ev_line}", width=W - 8,
                    initial_indent="       ",
                    subsequent_indent="         ",
                )
                print(wrapped)

    # ── Anomaly timeline ──────────────────────────────────────────────────
    print(f"\n{_hr()}")
    print("  ANOMALY TIMELINE  (most recent 15 flagged readings in analysis window)")
    print(_hr())

    label_cols = [c for c in anom_df.columns if c.endswith("__label")]
    if label_cols:
        if real_start is not None:
            anom_win = anom_df[anom_df.index >= real_start]
        else:
            cutoff   = anom_df.index[-1] - pd.Timedelta(hours=features["window_hours"])
            anom_win = anom_df[anom_df.index >= cutoff]

        flagged = anom_win[(anom_win[label_cols] == -1).any(axis=1)].tail(15)

        if flagged.empty:
            print("  No anomalies detected in this window.")
        else:
            for ts, row in flagged.iterrows():
                sensors = [
                    c.replace("__label", "").replace("strain_", "strain:")
                    for c in label_cols if row[c] == -1
                ]
                print(f"  {ts}  →  {', '.join(sensors)}")
    else:
        print("  (no anomaly data)")

    print(f"\n{'═' * W}\n")


def export_csv(
    features: dict, ranked: list[dict], path: Path
) -> None:
    rows = []
    for d in ranked:
        for ev in (d["evidence"] or ["—"]):
            rows.append({
                "defect":     d["defect"],
                "score":      d["score"],
                "confidence": d["confidence"],
                "evidence":   ev,
            })
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  Results exported to {path}")


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="SHM ML Pipeline — anomaly detection, trend analysis, defect ranking"
    )
    parser.add_argument(
        "--no-db", action="store_true",
        help="Skip DB loading and run on fully synthetic data",
    )
    parser.add_argument(
        "--hours", type=int, default=48,
        help="Analysis window in hours (default: 48)",
    )
    parser.add_argument(
        "--export", choices=["csv"], default=None,
        help="Export ranked results to a file",
    )
    args = parser.parse_args()

    print(f"\n[SHM Pipeline]  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(_hr())

    # ── Step 1: Load real data ──────────────────────────────────────────────
    real_df     = None
    real_start  = None
    element_names = ["Column A", "Column B", "Slab 1"]   # fallback

    if not args.no_db and DB_PATH.exists():
        print(f"[1/5] Loading sensor data from {DB_PATH}")
        real_df, element_names = load_db(DB_PATH)
        real_start = real_df.index[0]
        print(
            f"      {len(real_df)} samples · "
            f"{real_df.index[0]:%Y-%m-%d %H:%M} → {real_df.index[-1]:%Y-%m-%d %H:%M} · "
            f"elements: {', '.join(element_names)}"
        )
    else:
        reason = "no DB found" if not DB_PATH.exists() else "--no-db flag"
        print(f"[1/5] Skipping DB ({reason}) — will use synthetic data only")

    # ── Step 2: Generate synthetic baseline ────────────────────────────────
    synth_end   = (real_start - pd.Timedelta(minutes=10)) if real_start else pd.Timestamp.now()
    synth_start = synth_end - pd.Timedelta(days=SYNTH_DAYS)
    print(
        f"[2/5] Generating {SYNTH_DAYS}-day synthetic baseline "
        f"({synth_start:%Y-%m-%d} → {synth_end:%Y-%m-%d})"
    )
    synth_df = generate_synthetic(synth_start, SYNTH_DAYS, element_names)

    # ── Step 3: Merge ──────────────────────────────────────────────────────
    if real_df is not None:
        # Ensure column alignment before concatenating
        for col in synth_df.columns:
            if col not in real_df.columns:
                real_df[col] = np.nan
        for col in real_df.columns:
            if col not in synth_df.columns:
                synth_df[col] = np.nan
        df = pd.concat([synth_df, real_df]).sort_index()
    else:
        df = synth_df.copy()

    print(
        f"[3/5] Combined dataset: {len(df)} samples · "
        f"{df.index[0]:%Y-%m-%d} → {df.index[-1]:%Y-%m-%d}"
    )

    # ── Step 4: Anomaly detection ───────────────────────────────────────────
    print(f"[4/5] Fitting Isolation Forest (contamination={IF_CONTAMINATION})…")
    n_synth  = len(synth_df)
    anom_df  = detect_anomalies(df, n_train=n_synth)
    lbl_cols = [c for c in anom_df.columns if c.endswith("__label")]
    n_anom   = (anom_df[lbl_cols] == -1).any(axis=1).sum()
    print(
        f"      {n_anom} / {len(df)} timestamps have ≥1 anomalous signal "
        f"({n_anom/len(df)*100:.1f}%)"
    )

    # ── Step 5: Build features + rank defects ───────────────────────────────
    print(f"[5/5] Evaluating {len(DEFECT_RULES)} defect rules over last {args.hours} h…")
    features = build_features(df, anom_df, real_start, window_h=args.hours)
    ranked   = rank_defects(features)
    print(f"      {len(ranked)} candidate defects identified above threshold.\n")

    # ── Report ──────────────────────────────────────────────────────────────
    print_report(features, ranked, df, anom_df, real_start)

    if args.export == "csv":
        out = Path(__file__).parent / f"results_{datetime.now():%Y%m%d_%H%M%S}.csv"
        export_csv(features, ranked, out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
