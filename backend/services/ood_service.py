import base64
import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))
# ── Config ───────────────────────────────────────────────────────────────
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GPT_MODEL  = "gpt-4o"


async def estimate_portion(image_bytes: bytes, food_label: str) -> int:
    """
    Asks GPT-4o to estimate the portion weight in grams for a known food.
    Used to scale per-100g USDA nutrition data to actual serving size.

    Args:
        image_bytes: raw image bytes
        food_label : food name e.g. "hamburger"

    Returns:
        estimated weight in grams (defaults to 100 if estimation fails)
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")
    image_b64      = base64.b64encode(image_bytes).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "Content-Type" : "application/json",
    }

    payload = {
        "model": GPT_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
                    },
                    {
                        "type": "text",
                        "text": (
                            f"This is a photo of {food_label}. "
                            "Estimate the total weight of the food in grams as it appears in this image. "
                            "Respond ONLY with a JSON object, no extra text:\n"
                            '{"weight_grams": <number>}\n'
                            "If you cannot estimate, use 100."
                        )
                    }
                ]
            }
        ],
        "max_tokens": 50,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(OPENAI_URL, headers=headers, json=payload)

    if response.status_code != 200:
        return 100   # fallback to 100g

    try:
        content = response.json()["choices"][0]["message"]["content"].strip()
        clean   = content.replace("```json", "").replace("```", "").strip()
        data    = json.loads(clean)
        weight  = int(data.get("weight_grams", 100))
        return max(10, min(weight, 2000))   # clamp between 10g and 2000g
    except Exception:
        return 100


async def gpt4o_identify(image_bytes: bytes) -> dict:
    """
    Sends unknown food image to GPT-4o Vision.
    Returns food name + estimated macros + portion weight.
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")
    image_b64      = base64.b64encode(image_bytes).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "Content-Type" : "application/json",
    }

    payload = {
        "model": GPT_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
                    },
                    {
                        "type": "text",
                        "text": (
                            "You are a nutrition expert. Look at this food image and respond "
                            "ONLY with a JSON object in this exact format, no extra text:\n"
                            "{\n"
                            '  "food": "name of the dish",\n'
                            '  "weight_grams": estimated total weight of food in grams,\n'
                            '  "calories": total calories for this portion,\n'
                            '  "protein": total protein in grams for this portion,\n'
                            '  "carbs": total carbs in grams for this portion,\n'
                            '  "fat": total fat in grams for this portion\n'
                            "}\n"
                            "If you cannot identify the food, set food to 'unknown' and all numbers to 0."
                        )
                    }
                ]
            }
        ],
        "max_tokens": 200,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(OPENAI_URL, headers=headers, json=payload)

    if response.status_code != 200:
        return _fallback_response()

    try:
        content = response.json()["choices"][0]["message"]["content"].strip()
        clean   = content.replace("```json", "").replace("```", "").strip()
        data    = json.loads(clean)

        if data.get("food", "").lower() == "unknown":
            return _fallback_response()

        weight = int(data.get("weight_grams", 100))

        return {
            "food"        : data["food"],
            "weight_grams": weight,
            "calories"    : round(data.get("calories", 0)),
            "protein"     : round(data.get("protein", 0), 1),
            "carbs"       : round(data.get("carbs", 0), 1),
            "fat"         : round(data.get("fat", 0), 1),
            "serving"     : f"estimated portion ({weight}g)",
            "source"      : "gpt4o",
            "confidence"  : None,
        }

    except Exception:
        return _fallback_response()


def _fallback_response() -> dict:
    return {
        "food"        : None,
        "weight_grams": None,
        "calories"    : None,
        "protein"     : None,
        "carbs"       : None,
        "fat"         : None,
        "serving"     : None,
        "source"      : "unknown",
        "confidence"  : None,
        "error"       : "Could not identify this food. Please describe it manually.",
    }