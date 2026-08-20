"""
Reads the customer's free-text answers with Claude instead of naive keyword
matching, so "I dislike repetitive data entry" doesn't get read as "dislikes
analytical work" the way a keyword scan would.

Requires ANTHROPIC_API_KEY in the environment. If it's missing, or the
request fails for any reason (offline, rate limit, bad key), this module
returns None and engine.py falls back to the keyword-based scorer in
careers.py — the pipeline still runs end to end either way.
"""
import os
import json
import requests

from careers import DIMENSIONS

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = f"""You are scoring a career-assessment respondent on 10 fixed dimensions, \
based only on what they actually wrote. Dimensions: {", ".join(DIMENSIONS)}.

For each dimension, output an integer 1-10:
- 5 = no signal either way in their text
- 7-10 = their text clearly indicates strength/interest in this dimension
- 1-4 = their text clearly indicates dislike/weakness in this dimension

Ground every non-5 score in something they actually said. Do not infer a low \
score for a dimension just because a nearby word appears — e.g. someone who \
dislikes "repetitive data entry" is not necessarily low on Analytical; read \
intent, not keywords.

Respond with ONLY a JSON object mapping each dimension name to its integer \
score. No prose, no markdown fences."""


def _build_user_prompt(answers: dict) -> str:
    return (
        f"What they're naturally good at: {answers.get('goodAt', '') or '(not answered)'}\n"
        f"What people compliment them on: {answers.get('compliments', '') or '(not answered)'}\n"
        f"What tasks they dislike: {answers.get('dislike', '') or '(not answered)'}\n"
        f"Their ideal career description: {answers.get('idealCareer', '') or '(not answered)'}"
    )


def get_text_scores(answers: dict, timeout: float = 15.0):
    """Returns {dimension: 1-10} from Claude, or None if unavailable."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        resp = requests.post(
            API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 300,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": _build_user_prompt(answers)}],
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"].strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        scores = json.loads(text)

        cleaned = {}
        for d in DIMENSIONS:
            val = scores.get(d, 5)
            try:
                cleaned[d] = max(1, min(10, int(round(float(val)))))
            except (TypeError, ValueError):
                cleaned[d] = 5
        return cleaned

    except Exception:
        # Offline, bad key, rate limited, malformed response, etc. —
        # the pipeline should degrade, not crash.
        return None
