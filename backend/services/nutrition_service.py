"""
Nutrition for a food typed by name (no photo).

USDA FoodData Central used to be the first source, but its top search hit is
often a branded or raw product (banana 312 kcal/100g, white rice as dry grain,
any made-up word matched to some product). GPT-4o now estimates typical
per-100g values for the food as normally eaten, and first confirms the name is
actually a food.
"""
import json
import os

import httpx

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GPT_MODEL  = "gpt-4o"


class NotAFoodError(ValueError):
    """The name does not describe a real food or drink."""


async def get_nutrition(food_name: str) -> dict | None:
    """
    Returns per-100g values:
        {"food", "calories", "protein", "carbs", "fat", "serving": "per 100g", "source"}
    Raises NotAFoodError for names that are not food. Returns None if GPT-4o fails.
    """
    payload = {
        "model": GPT_MODEL,
        "messages": [{
            "role": "user",
            "content": (
                "You are a nutrition expert. A user typed this food name: "
                f"{json.dumps(food_name)}.\n"
                "It may be informal, a regional name in any cuisine, or a description like "
                "'hamburger with 3 layers of cheese'. First decide if it is a real food or drink. "
                "Random letters, objects, or non-foods are not.\n"
                "If it is a food, give typical nutrition per 100g AS NORMALLY EATEN "
                "(cooked rice, not dry grain; fresh fruit, not dried or chips; plain yogurt unless "
                "a flavour is named), using reference values such as USDA where they exist.\n"
                "Respond ONLY with JSON, no extra text:\n"
                '{"is_food": true or false, "food_name": "clean food name", '
                '"calories": number, "protein": number, "carbs": number, "fat": number}'
            ),
        }],
        "max_tokens" : 120,
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
        "Content-Type" : "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(OPENAI_URL, headers=headers, json=payload)
        if response.status_code != 200:
            return None
        content = response.json()["choices"][0]["message"]["content"].strip()
        data    = json.loads(content.replace("```json", "").replace("```", "").strip())
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None

    if data.get("is_food") is False:
        raise NotAFoodError(food_name)

    try:
        calories = float(data["calories"])
    except (KeyError, TypeError, ValueError):
        return None
    if calories < 0 or calories > 950:   # nothing exceeds pure fat (~900 kcal/100g)
        return None

    return {
        "food"    : (data.get("food_name") or food_name).strip(),
        "calories": round(calories),
        "protein" : round(float(data.get("protein") or 0), 1),
        "carbs"   : round(float(data.get("carbs")   or 0), 1),
        "fat"     : round(float(data.get("fat")     or 0), 1),
        "serving" : "per 100g",
        "source"  : "gpt4o",
    }
