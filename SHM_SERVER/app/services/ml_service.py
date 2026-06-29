"""
ml_service.py — thin wrapper around SHM_ML/pipeline.py for the Flask app.

Imports the pipeline module by path, runs compute_report(), and caches
the result for CACHE_TTL seconds so the Isolation Forest fit (1-3 s) does
not block every dashboard refresh.
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path
from threading import Lock

# ── Locate SHM_ML/pipeline.py relative to this file ─────────────────────────
_SHM_ML_DIR = Path(__file__).resolve().parent.parent.parent.parent / "SHM_ML"
if str(_SHM_ML_DIR) not in sys.path:
    sys.path.insert(0, str(_SHM_ML_DIR))

try:
    import pipeline as _pipeline
    _ML_AVAILABLE = True
except ImportError as _e:
    _ML_AVAILABLE = False
    _IMPORT_ERROR = str(_e)

# ── Cache ────────────────────────────────────────────────────────────────────
CACHE_TTL   = 300   # seconds (5 min) — tune here
_cache: dict | None = None
_cache_time: float  = 0.0
_cache_lock         = Lock()


def get_ml_report(window_h: int = 48) -> dict:
    """
    Return the cached ML report, recomputing if the cache is stale.
    Thread-safe: concurrent requests wait on the lock rather than
    all triggering a pipeline run simultaneously.
    """
    global _cache, _cache_time

    if not _ML_AVAILABLE:
        return {"error": f"ML pipeline unavailable: {_IMPORT_ERROR}"}

    with _cache_lock:
        age = time.time() - _cache_time
        if _cache is not None and age < CACHE_TTL:
            return _cache

        try:
            result = _pipeline.compute_report(window_h=window_h)
            result["cache_age_s"] = 0
            _cache      = result
            _cache_time = time.time()
        except Exception:
            err = traceback.format_exc()
            # Return stale cache rather than an error if we have one
            if _cache is not None:
                stale = dict(_cache)
                stale["cache_age_s"] = int(age)
                stale["stale_warning"] = "Recompute failed; showing cached result."
                return stale
            return {"error": err}

    return _cache
