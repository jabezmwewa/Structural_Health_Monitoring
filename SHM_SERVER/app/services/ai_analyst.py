"""
ai_analyst.py  –  Option 2: Gemini-powered structural analysis

Drop-in service that sends recent readings to the Gemini API
and returns a natural-language assessment. Disabled by default;
set GEMINI_API_KEY in your environment to activate.
"""

import os
import json
import requests

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_URL = (
    'https://generativelanguage.googleapis.com/v1beta/models/'
    'gemini-pro:generateContent'
)


def analyse(readings: list, health_score: dict) -> str:
    """
    Sends the last N readings and current health score to Gemini
    and returns a plain-English structural assessment.

    Args:
        readings:     list of SensorReading dicts (most recent last)
        health_score: latest HealthScore dict

    Returns:
        str  – Gemini's assessment, or a fallback message if unavailable.
    """
    if not GEMINI_API_KEY:
        return 'AI analysis unavailable: GEMINI_API_KEY not configured.'

    prompt = _build_prompt(readings, health_score)

    try:
        response = requests.post(
            GEMINI_URL,
            params={'key': GEMINI_API_KEY},
            json={
                'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': {'maxOutputTokens': 300, 'temperature': 0.3},
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data['candidates'][0]['content']['parts'][0]['text']

    except Exception as exc:
        return f'AI analysis error: {exc}'


def _build_prompt(readings: list, health_score: dict) -> str:
    summary = json.dumps(readings[-5:], indent=2)   # last 5 readings
    score   = health_score.get('score', 'N/A')
    label   = health_score.get('label', 'N/A')

    return f"""
You are an expert structural health monitoring engineer.
Analyse the following sensor readings and provide a concise (3–4 sentence)
assessment of the structure's condition, any concerns, and a recommended action.

Health Score: {score}/100  ({label})

Recent Readings (latest last):
{summary}

Respond in plain English, no markdown, no bullet points.
""".strip()
