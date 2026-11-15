"""
One place for every OpenAI call, so each one is timed, counted and priced.
"""
import json
import os
import time

import httpx

from services import metrics_service

OPENAI_URL = "https://api.openai.com/v1/chat/completions"


async def chat_completion(payload: dict, feature: str, timeout: float = 20.0) -> dict | None:
    """
    Sends a chat completion request. Returns the response JSON, or None on any
    failure. Never raises for network or API errors.
    """
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
        "Content-Type" : "application/json",
    }
    model = payload.get("model", "unknown")
    started = time.perf_counter()
    status = None
    body = None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(OPENAI_URL, headers=headers, json=payload)
        status = response.status_code
        if status == 200:
            body = response.json()
    except (httpx.HTTPError, ValueError):
        status = None

    usage = (body or {}).get("usage") or {}
    metrics_service.record_llm_call(
        feature           = feature,
        model             = model,
        latency_ms        = (time.perf_counter() - started) * 1000,
        prompt_tokens     = int(usage.get("prompt_tokens") or 0),
        completion_tokens = int(usage.get("completion_tokens") or 0),
        ok                = body is not None,
        status            = status,
    )
    return body


def message_text(body: dict | None) -> str | None:
    try:
        return body["choices"][0]["message"]["content"].strip()
    except (TypeError, KeyError, IndexError, AttributeError):
        return None


def parse_json_reply(body: dict | None) -> dict | None:
    """Pulls a JSON object out of a model reply, tolerating ```json fences."""
    text = message_text(body)
    if not text:
        return None
    clean = text.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(clean)
    except ValueError:
        start, end = clean.find("{"), clean.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(clean[start:end + 1])
        except ValueError:
            return None
    return data if isinstance(data, dict) else None
