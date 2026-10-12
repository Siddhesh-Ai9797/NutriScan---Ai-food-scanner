import base64
import os
import httpx
import json
from dotenv import load_dotenv
from services.nutrition_service import NotAFoodError

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

    # The EfficientNet guess is only a hint. The model only knows 101 Food-101 classes,
    # so for dishes outside that list (biryani, dal, dosa...) it confidently picks the
    # closest class. GPT-4o must check the guess against the photo, not repeat it.
    readable_hint = primary_food.replace("_", " ") if primary_food else None
    primary_hint = (
        f"A fast image classifier guessed the main dish is '{readable_hint}'. "
        "That classifier only knows 101 common Western dishes, so it is often wrong for "
        "regional cuisine such as Indian, Asian, or Latin dishes. Do not trust the guess. "
        "Look at the image yourself and name the main dish as it really is. "
    ) if readable_hint else ""

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
                            "Name dishes specifically: say 'masala dosa' rather than 'dosa' if there is a filling, "
                            "'chicken biryani' rather than 'rice'. If the photo is a platter of many dishes served "
                            "together, such as an Indian thali, a bento box, or a mezze platter, use the platter's "
                            "name (e.g. 'vegetarian thali') as primary_food and list each dish as an item. "
                            "Estimate the weight and nutrition for each item separately based on the portion size visible. "
                            "Respond ONLY with a JSON object in this exact format, no extra text:\n"
                            "{\n"
                            '  "primary_food": "specific name of the main dish, e.g. chicken biryani",\n'
                            '  "hint_correct": true if the classifier guess names the same dish as primary_food, otherwise false,\n'
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
        "max_tokens" : 700,
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

        # GPT-4o's own name for the main dish; fall back to the first item.
        gpt_primary  = (data.get("primary_food") or (items[0].get("food") if items else "") or "").strip()
        # If GPT-4o did not answer, assume the hint stands (old behaviour).
        hint_correct = data.get("hint_correct")
        if not isinstance(hint_correct, bool):
            hint_correct = True

        return {
            "items"         : items,
            "total_calories": total_calories,
            "total_protein" : total_protein,
            "total_carbs"   : total_carbs,
            "total_fat"     : total_fat,
            "primary_food"  : gpt_primary or primary_food or "Unknown",
            "hint_correct"  : hint_correct,
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


async def estimate_named_food(image_bytes: bytes, food_name: str, grams: float | None = None) -> dict | None:
    """
    The user corrected the food name. Estimate nutrition for the WHOLE portion
    in the photo, trusting the user's name. Used instead of per-100g lookups,
    which are poor for regional dishes (USDA returns packaged products).

    Returns {"food", "weight_grams", "calories", "protein", "carbs", "fat"} or None.
    Raises NotAFoodError if the corrected name is not a real food or drink.
    """
    portion_hint = (
        f"An earlier look at this same photo estimated the portion at about {round(grams)}g. "
        "Keep the weight close to that unless the corrected dish clearly weighs differently. "
    ) if grams else ""
    openai_api_key = os.getenv("OPENAI_API_KEY")
    image_b64      = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "model": GPT_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": (
                    f"The user says this photo shows: {json.dumps(food_name)}. First decide whether that "
                    "name is a real food or drink; random letters or non-foods are not. If it is a food, "
                    "trust that name even if the photo looks like something else to you. "
                    f"{portion_hint}"
                    "You are a nutrition expert. Estimate the weight "
                    "of the full portion visible and the nutrition for that whole portion, as typically "
                    "prepared for this dish (include oil, ghee, and meat where the dish normally has them). "
                    "Respond ONLY with JSON, no extra text:\n"
                    '{"is_food": true or false, "weight_grams": number, "calories": number, "protein": number, "carbs": number, "fat": number}'
                )},
            ],
        }],
        "max_tokens" : 150,
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(OPENAI_URL, headers=headers, json=payload)
        if response.status_code != 200:
            return None
        content = response.json()["choices"][0]["message"]["content"].strip()
        data    = json.loads(content.replace("```json", "").replace("```", "").strip())
        if data.get("is_food") is False:
            raise NotAFoodError(food_name)
        calories = float(data["calories"])
        if calories <= 0:
            return None
        return {
            "food"        : food_name,
            "weight_grams": round(float(data.get("weight_grams") or 0)) or None,
            "calories"    : round(calories),
            "protein"     : round(float(data.get("protein") or 0), 1),
            "carbs"       : round(float(data.get("carbs")   or 0), 1),
            "fat"         : round(float(data.get("fat")     or 0), 1),
        }
    except NotAFoodError:
        raise
    except Exception:
        return None


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