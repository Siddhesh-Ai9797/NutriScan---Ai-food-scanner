"""
Nutrition for a food typed by name (no photo).

USDA FoodData Central used to be the first source, but its top search hit is
often a branded or raw product (banana 312 kcal/100g, white rice as dry grain,
any made-up word matched to some product). GPT-4o now estimates typical
per-100g values for the food as normally eaten, and first confirms the name is
actually a food.
"""
import json

from services import metrics_service
from services.cache_service import CACHE_ON, name_cache, name_key
from services.guardrail_service import check_per_100g
from services.openai_client import chat_completion, parse_json_reply

GPT_MODEL = "gpt-4o"


class NotAFoodError(ValueError):
    """The name does not describe a real food or drink."""


async def get_nutrition(food_name: str) -> dict | None:
    """
    Returns per-100g values:
        {"food", "calories", "protein", "carbs", "fat", "serving": "per 100g", "source"}
    Raises NotAFoodError for names that are not food. Returns None if GPT-4o fails.
    Answers are cached by name, including "not a food" answers.
    """
    key = name_key(food_name)
    if CACHE_ON and key:
        cached = name_cache.get(key)
        if cached is not None:
            metrics_service.record_event("name_cache_hit")
            if cached == "NOT_FOOD":
                raise NotAFoodError(food_name)
            return cached

    result = await _lookup(food_name)
    if CACHE_ON and key and result is not None:
        name_cache.set(key, result)
    if result == "NOT_FOOD":
        raise NotAFoodError(food_name)
    return result


async def _lookup(food_name: str) -> dict | str | None:
    """Returns per-100g values, the string NOT_FOOD, or None on failure."""
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
    data = parse_json_reply(await chat_completion(payload, feature="nutrition_lookup", timeout=15.0))
    if data is None:
        return None

    if data.get("is_food") is False:
        return "NOT_FOOD"

    try:
        calories = float(data["calories"])
    except (KeyError, TypeError, ValueError):
        return None
    flags = check_per_100g(calories, data.get("protein") or 0, data.get("carbs") or 0, data.get("fat") or 0)
    if flags:
        for rule in flags:
            metrics_service.record_event("guardrail", rule=rule, feature="nutrition_lookup")
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
