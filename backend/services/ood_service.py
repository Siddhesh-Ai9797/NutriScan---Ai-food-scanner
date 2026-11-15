import base64
import json
import os

from dotenv import load_dotenv

from services import metrics_service
from services.guardrail_service import NotFoodPhoto, check_plate
from services.nutrition_service import NotAFoodError
from services.openai_client import chat_completion, parse_json_reply

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

GPT_MODEL = "gpt-4o"


FULL_MODEL = os.getenv("FULL_VISION_MODEL", "gpt-4o")
FAST_MODEL = os.getenv("FAST_VISION_MODEL", "gpt-4o-mini")


def _plate_prompt(primary_food: str | None) -> str:
    # The EfficientNet guess is only a hint. The model only knows 101 Food-101 classes,
    # so for dishes outside that list (biryani, dal, dosa...) it confidently picks the
    # closest class. The vision model must check the guess against the photo, not repeat it.
    readable_hint = primary_food.replace("_", " ") if primary_food else None
    primary_hint = (
        f"A fast image classifier guessed the main dish is '{readable_hint}'. "
        "That classifier only knows 101 common Western dishes, so it is often wrong for "
        "regional cuisine such as Indian, Asian, or Latin dishes. Do not trust the guess. "
        "Look at the image yourself and name the main dish as it really is. "
    ) if readable_hint else ""
    return (
        f"{primary_hint}"
        "You are a nutrition expert. First decide whether the photo shows any food or drink at all. "
        "If it does not (a person, a screen, a room, an object), set is_food to false and return no items. "
        "Otherwise look at the image carefully and identify "
        "ALL food items visible, including main dish, sides, drinks, desserts, sauces, toppings. "
        "Name dishes specifically: say 'masala dosa' rather than 'dosa' if there is a filling, "
        "'chicken biryani' rather than 'rice'. If the photo is a platter of many dishes served "
        "together, such as an Indian thali, a bento box, or a mezze platter, use the platter's "
        "name (e.g. 'vegetarian thali') as primary_food and list each dish as an item. "
        "Estimate the weight and nutrition for each item separately based on the portion size visible. "
        "Respond ONLY with a JSON object in this exact format, no extra text:\n"
        "{\n"
        '  "is_food": true or false,\n'
        '  "primary_food": "specific name of the main dish, e.g. chicken biryani",\n'
        '  "hint_correct": true if the classifier guess names the same dish as primary_food, otherwise false,\n'
        '  "items": [\n'
        "    {\n"
        '      "food": "exact food name",\n'
        '      "weight_grams": estimated weight as number,\n'
        '      "calories": total calories for this portion as number,\n'
        '      "protein": total protein in grams as number,\n'
        '      "carbs": total carbs in grams as number,\n'
        '      "fat": total fat in grams as number\n'
        "    }\n"
        "  ],\n"
        '  "total_calories": sum of all calories as number,\n'
        '  "total_protein": sum of all protein as number,\n'
        '  "total_carbs": sum of all carbs as number,\n'
        '  "total_fat": sum of all fat as number\n'
        "}\n"
        "If there is food but you cannot identify it at all, return items as an empty array."
    )


async def detect_all_foods(image_bytes: bytes, primary_food: str = None,
                           model: str = FULL_MODEL, detail: str = "auto") -> tuple[dict | None, list[str]]:
    """
    Detects ALL food items in the photo with a vision model, then runs the
    output guardrail on the reply.

    Args:
        image_bytes : cleaned JPEG bytes
        primary_food: EfficientNet's guess, passed as a hint to check
        model       : gpt-4o for hard photos, gpt-4o-mini for confident ones
        detail      : OpenAI image detail; "low" sends a small image and costs far less

    Returns (plate, flags). plate is None when the call failed or nothing
    usable came back; flags list the guardrail rules that fired.
    Raises NotFoodPhoto when the model says there is no food in the photo.
    """
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}", "detail": detail}},
                {"type": "text", "text": _plate_prompt(primary_food)},
            ],
        }],
        "max_tokens"     : 700,
        "temperature"    : 0.3,
        "response_format": {"type": "json_object"},
    }
    body = await chat_completion(payload, feature="scan", timeout=20.0)
    if body is None:
        return None, ["llm_failed"]
    return check_plate(parse_json_reply(body))


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
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

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
    try:
        data = parse_json_reply(await chat_completion(payload, feature="estimate_named", timeout=20.0))
        if data is None:
            return None
        if data.get("is_food") is False:
            raise NotAFoodError(food_name)
        data.pop("is_food", None)
        plate, flags = check_plate({"items": [{**data, "food": food_name}]})
        for rule in flags:
            metrics_service.record_event("guardrail", rule=rule, feature="estimate_named")
        if plate is None:
            return None
        item = plate["items"][0]
        return {
            "food"        : food_name,
            "weight_grams": item["weight_grams"],
            "calories"    : item["calories"],
            "protein"     : item["protein"],
            "carbs"       : item["carbs"],
            "fat"         : item["fat"],
        }
    except NotAFoodError:
        raise
    except NotFoodPhoto:
        raise NotAFoodError(food_name)
    except Exception:
        return None
