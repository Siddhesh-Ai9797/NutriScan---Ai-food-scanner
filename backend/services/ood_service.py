import base64
import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GPT_MODEL  = "gpt-4o"


async def detect_all_foods(image_bytes: bytes, primary_food: str = None) -> dict:
    """
    Detects ALL food items in the image using GPT-4o Vision.
    Always called — whether EfficientNet identified the food or not.
    
    Args:
        image_bytes : raw image bytes
        primary_food: food EfficientNet already identified (if any)
    
    Returns:
        {
            "items": [
                {"food": "Waffles", "weight_grams": 150, "calories": 350, "protein": 7, "carbs": 55, "fat": 12},
                {"food": "Chocolate Cake", "weight_grams": 100, "calories": 280, "protein": 4, "carbs": 38, "fat": 14},
                {"food": "Hot Chocolate", "weight_grams": 200, "calories": 180, "protein": 5, "carbs": 30, "fat": 6}
            ],
            "total_calories": 810,
            "total_protein" : 16,
            "total_carbs"   : 123,
            "total_fat"     : 32,
            "primary_food"  : "Waffles"
        }
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")
    image_b64      = base64.b64encode(image_bytes).decode("utf-8")

    primary_hint = f"Our system already identified '{primary_food}' as the main food. " if primary_food else ""

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
                        "type"     : "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"{primary_hint}"
                            "You are a nutrition expert. Look at this food image carefully and identify "
                            "ALL food items visible — including main dish, sides, drinks, desserts, sauces, toppings. "
                            "Estimate the weight and nutrition for each item separately based on the portion size visible. "
                            "Respond ONLY with a JSON object in this exact format, no extra text:\n"
                            "{\n"
                            '  "items": [\n'
                            '    {\n'
                            '      "food": "exact food name",\n'
                            '      "weight_grams": estimated weight as number,\n'
                            '      "calories": total calories for this portion as number,\n'
                            '      "protein": total protein in grams as number,\n'
                            '      "carbs": total carbs in grams as number,\n'
                            '      "fat": total fat in grams as number\n'
                            '    }\n'
                            '  ],\n'
                            '  "total_calories": sum of all calories as number,\n'
                            '  "total_protein": sum of all protein as number,\n'
                            '  "total_carbs": sum of all carbs as number,\n'
                            '  "total_fat": sum of all fat as number\n'
                            "}\n"
                            "If you cannot identify the food at all, return items as empty array."
                        )
                    }
                ]
            }
        ],
        "max_tokens" : 500,
        "temperature": 0.3,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(OPENAI_URL, headers=headers, json=payload)

    if response.status_code != 200:
        return _fallback_response(primary_food)

    try:
        content = response.json()["choices"][0]["message"]["content"].strip()
        clean   = content.replace("```json", "").replace("```", "").strip()
        data    = json.loads(clean)

        items = data.get("items", [])
        if not items:
            return _fallback_response(primary_food)

        # Use GPT-4o totals or calculate from items
        total_calories = round(data.get("total_calories") or sum(i.get("calories", 0) for i in items))
        total_protein  = round(data.get("total_protein")  or sum(i.get("protein",  0) for i in items), 1)
        total_carbs    = round(data.get("total_carbs")    or sum(i.get("carbs",    0) for i in items), 1)
        total_fat      = round(data.get("total_fat")      or sum(i.get("fat",      0) for i in items), 1)

        # Primary food is first item or EfficientNet result
        primary = primary_food or (items[0]["food"] if items else "Unknown")

        return {
            "items"         : items,
            "total_calories": total_calories,
            "total_protein" : total_protein,
            "total_carbs"   : total_carbs,
            "total_fat"     : total_fat,
            "primary_food"  : primary,
            "source"        : "gpt4o",
        }

    except (json.JSONDecodeError, KeyError):
        return _fallback_response(primary_food)


async def estimate_portion(image_bytes: bytes, food_label: str) -> int:
    """
    Legacy function kept for compatibility.
    Now we use detect_all_foods instead.
    Returns estimated weight of primary food in grams.
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
                        "type"     : "image_url",
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
        "max_tokens" : 50,
        "temperature": 0.1,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(OPENAI_URL, headers=headers, json=payload)

    if response.status_code != 200:
        return 100

    try:
        content = response.json()["choices"][0]["message"]["content"].strip()
        clean   = content.replace("```json", "").replace("```", "").strip()
        data    = json.loads(clean)
        weight  = int(data.get("weight_grams", 100))
        return max(10, min(weight, 2000))
    except Exception:
        return 100


async def gpt4o_identify(image_bytes: bytes) -> dict:
    """
    Legacy wrapper — now calls detect_all_foods.
    Used when EfficientNet confidence is below threshold.
    """
    result = await detect_all_foods(image_bytes, primary_food=None)

    if not result.get("items"):
        return _fallback_response(None)

    # Return in old format for compatibility with predict.py
    return {
        "food"        : result["primary_food"],
        "weight_grams": result["items"][0].get("weight_grams", 100) if result["items"] else 100,
        "calories"    : result["total_calories"],
        "protein"     : result["total_protein"],
        "carbs"       : result["total_carbs"],
        "fat"         : result["total_fat"],
        "serving"     : f"full meal ({len(result['items'])} items)",
        "source"      : "gpt4o",
        "confidence"  : None,
        "items"       : result["items"],
    }


def _fallback_response(primary_food: str = None) -> dict:
    return {
        "items"         : [],
        "total_calories": 0,
        "total_protein" : 0,
        "total_carbs"   : 0,
        "total_fat"     : 0,
        "primary_food"  : primary_food or "Unknown",
        "source"        : "unknown",
        "error"         : "Could not identify all food items. Please describe manually.",
    }