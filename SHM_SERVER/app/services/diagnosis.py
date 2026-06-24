"""
diagnosis.py — ranked cause inference.

Takes the trend features from trend_analysis and produces a RANKED list of
likely defects with the evidence behind each — never a single verdict. This is
a transparent rule/evidence engine (no black-box ML): each detector inspects the
trends and emits a score in 0..1 plus human-readable evidence, so a maintenance
engineer can see *why* a cause is ranked where it is.

Scores are heuristic indicators of concern, not calibrated probabilities. The
defect taxonomy follows the project brief: crack, deflection, settlement, creep,
corrosion risk, and excessive vibration.
"""

from statistics import pstdev

from app.services.evaluation import classify
from config import Config

_SPECS = Config.THRESHOLD_SPECS
_SEVERITY = {'ok': 0.0, 'warning': 0.5, 'critical': 1.0}


def _clamp(x):
    return max(0.0, min(1.0, x))


def _likelihood(score):
    return 'High' if score >= 0.66 else 'Moderate' if score >= 0.33 else 'Low'


def _build_context(trends):
    """Flatten trends into a convenient structure with per-signal status."""
    elements = []
    for e in trends.get('elements', []):
        f = e['strain']
        elements.append({
            'name': e['name'], 'type': e['element_type'], 'feat': f,
            'status': classify(f['current'], _SPECS.get('strain', {})),
        })
    env = {}
    for param, f in trends.get('environment', {}).items():
        env[param] = {'feat': f, 'status': classify(f['current'], _SPECS.get(param, {}))}
    columns = [e for e in elements if e['type'] == 'column']
    slabs = [e for e in elements if e['type'] == 'slab']
    return {'elements': elements, 'env': env, 'columns': columns, 'slabs': slabs}


def _strain_rise_factor(feat):
    """How fast strain is rising relative to its critical range, in 0..1."""
    crit = _SPECS.get('strain', {}).get('crit_high', 500) or 500
    return _clamp(feat['slope_per_day'] / (0.5 * crit)) if feat['slope_per_day'] > 0 else 0.0


# ── Detectors: each returns a finding dict or None ───────────────────────────

def _detect_creep(ctx):
    """Slow, sustained strain rise not explained by temperature → creep / progressive load."""
    best = None
    for e in ctx['elements']:
        f = e['feat']
        if f['direction'] != 'rising' or f['slope_per_day'] <= 0:
            continue
        rise = _strain_rise_factor(f)
        sev = _SEVERITY[e['status']]
        temp = ctx['env'].get('temperature', {}).get('feat', {})
        thermal = 0.25 if temp.get('direction') == 'rising' else 0.0   # could be thermal expansion
        score = _clamp(0.55 * rise + 0.35 * sev + 0.1 - thermal)
        if f.get('hours_to_crit') is not None and f['hours_to_crit'] < 48:
            score = _clamp(score + 0.15)
        if best is None or score > best['score']:
            ev = [
                f"Strain on {e['name']} rising steadily (+{f['slope_per_day']:.0f} µm/m per day, "
                f"{f['pct_change']:+.0f}% vs baseline).",
            ]
            if thermal == 0.0:
                ev.append("Temperature is not rising, so thermal expansion is unlikely to explain it.")
            if f.get('hours_to_crit') is not None:
                ev.append(f"At the current rate it reaches the critical limit in ~{f['hours_to_crit']:.0f} h.")
            best = {'cause': 'Creep / progressive overload', 'score': score,
                    'evidence': ev, 'affected': [e['name']],
                    'recommendation': 'Schedule a load assessment and increase strain sampling on this element.'}
    return best


def _detect_crack(ctx):
    """Elevated/abrupt strain together with acoustic emission → crack initiation."""
    sound = ctx['env'].get('sound')
    sound_sev = _SEVERITY[sound['status']] if sound else 0.0
    sound_rising = sound and sound['feat']['direction'] == 'rising'
    best = None
    for e in ctx['elements']:
        f = e['feat']
        sev = _SEVERITY[e['status']]
        jump = _clamp(abs(f['zscore']) / 3.0) if f['direction'] == 'rising' else 0.0
        acoustic = _clamp(sound_sev + (0.3 if sound_rising else 0.0))
        score = _clamp(0.45 * sev + 0.2 * jump + 0.45 * acoustic)
        if score <= 0:
            continue
        if best is None or score > best['score']:
            ev = [f"{e['name']} strain is {e['status']} and rising sharply (z={f['zscore']:.1f})."]
            if acoustic > 0:
                ev.append("Acoustic (sound) level is elevated — consistent with crack activity.")
            else:
                ev.append("No acoustic emission detected, which lowers the likelihood of an active crack.")
            best = {'cause': 'Crack initiation', 'score': score, 'evidence': ev,
                    'affected': [e['name']],
                    'recommendation': 'Visual/dye-penetrant inspection of the element; check the acoustic sensor.'}
    return best


def _detect_deflection(ctx):
    """High/rising strain on a slab → excessive deflection (bending)."""
    best = None
    for e in ctx['slabs']:
        f = e['feat']
        sev = _SEVERITY[e['status']]
        rise = _strain_rise_factor(f)
        score = _clamp(0.6 * sev + 0.4 * rise)
        if score <= 0:
            continue
        if best is None or score > best['score']:
            best = {'cause': 'Excessive deflection', 'score': score,
                    'evidence': [f"Slab {e['name']} strain is {e['status']} "
                                 f"({f['current']:.0f} µm/m, {f['direction']})."],
                    'affected': [e['name']],
                    'recommendation': 'Measure mid-span deflection and compare against design limits.'}
    return best


def _detect_settlement(ctx):
    """Diverging strain between columns → differential foundation settlement."""
    cols = ctx['columns']
    if len(cols) < 2:
        return None
    currents = [c['feat']['current'] for c in cols]
    spread = max(currents) - min(currents)
    divergence = pstdev(currents) if len(currents) > 1 else 0.0
    crit = _SPECS.get('strain', {}).get('crit_high', 500) or 500
    rising = [c for c in cols if c['feat']['direction'] == 'rising']
    if spread <= 0.15 * crit or not rising:
        return None
    score = _clamp(divergence / (0.4 * crit) + 0.2 * len(rising) / len(cols))
    hi = max(cols, key=lambda c: c['feat']['current'])
    return {
        'cause': 'Differential settlement', 'score': score,
        'evidence': [
            f"Column strains are diverging (spread {spread:.0f} µm/m across {len(cols)} columns).",
            f"{hi['name']} is loading up relative to the others — a sign of uneven foundation movement.",
        ],
        'affected': [c['name'] for c in rising],
        'recommendation': 'Level-survey the column bases and review foundation/soil conditions.',
    }


def _detect_corrosion(ctx):
    """Sustained high humidity (with temperature cycling) → elevated corrosion risk."""
    hum = ctx['env'].get('humidity')
    if not hum:
        return None
    f = hum['feat']
    sev = _SEVERITY[hum['status']]
    warn = _SPECS.get('humidity', {}).get('warn_high', 75)
    elevated = _clamp((f['mean'] - 0.8 * warn) / (0.4 * warn)) if warn else 0.0
    temp = ctx['env'].get('temperature', {}).get('feat', {})
    cycling = 0.2 if temp and abs(temp.get('slope_per_day', 0)) > 1 else 0.0
    humidity_factor = max(sev, elevated)
    score = _clamp(0.6 * humidity_factor + cycling)
    # Corrosion risk requires humidity to actually be elevated — not temperature
    # cycling alone (which is normal daily variation).
    if humidity_factor <= 0 or score < 0.25:
        return None
    return {
        'cause': 'Elevated corrosion risk', 'score': score,
        'evidence': [
            f"Humidity is averaging {f['mean']:.0f}% (status {hum['status']}).",
            "Combined with temperature cycling, these conditions accelerate reinforcement corrosion.",
        ],
        'affected': ['structure (environmental)'],
        'recommendation': 'Inspect for moisture ingress/spalling; consider protective coatings or dehumidification.',
    }


def _detect_vibration(ctx):
    """Elevated or rising vibration → dynamic loading / resonance."""
    vib = ctx['env'].get('vibration')
    if not vib:
        return None
    f = vib['feat']
    sev = _SEVERITY[vib['status']]
    rise = _clamp(f['slope_per_day'] / 5.0) if f['direction'] == 'rising' else 0.0
    score = _clamp(0.7 * sev + 0.3 * rise)
    if score < 0.2:
        return None
    return {
        'cause': 'Excessive vibration / dynamic loading', 'score': score,
        'evidence': [f"Vibration is {vib['status']} ({f['current']:.1f} mm/s, {f['direction']})."],
        'affected': ['structure (dynamic)'],
        'recommendation': 'Identify the excitation source; check for resonance and fixity of connections.',
    }


_DETECTORS = [
    _detect_creep, _detect_crack, _detect_deflection,
    _detect_settlement, _detect_corrosion, _detect_vibration,
]


def rank_causes(trends, min_score=0.1):
    """Run all detectors and return findings ranked by score (desc)."""
    ctx = _build_context(trends)
    findings = []
    for detect in _DETECTORS:
        finding = detect(ctx)
        if finding and finding['score'] >= min_score:
            finding['score'] = round(finding['score'], 2)
            finding['likelihood'] = _likelihood(finding['score'])
            findings.append(finding)
    findings.sort(key=lambda f: f['score'], reverse=True)
    return findings
