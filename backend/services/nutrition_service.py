import httpx
import os
from dotenv import load_dotenv

load_dotenv("../.env")

USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"


async def get_nutrition(food_label: str) -> dict:
    """
    Calls USDA FoodData Central API with a food label.
    Returns calories, protein, carbs, fat per 100g serving.
    """
    # Read key inside function — guarantees .env is already loaded
    usda_api_key = os.getenv("USDA_API_KEY")

    query = food_label.replace("_", " ")

    params = {
        "query"   : query,
        "api_key" : usda_api_key,
        "pageSize": 1,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(USDA_SEARCH_URL, params=params)

    if response.status_code != 200:
        return _fallback_nutrition(food_label)

    data  = response.json()
    foods = data.get("foods", [])

    if not foods:
        return _fallback_nutrition(food_label)

    food      = foods[0]
    nutrients = {n["nutrientName"]: n.get("value", 0) for n in food.get("foodNutrients", [])}

    calories = round(nutrients.get("Energy", 0))
    protein  = round(nutrients.get("Protein", 0), 1)
    carbs    = round(nutrients.get("Carbohydrate, by difference", 0), 1)
    fat      = round(nutrients.get("Total lipid (fat)", 0), 1)

    return {
        "food"    : food_label.replace("_", " ").title(),
        "calories": calories,
        "protein" : protein,
        "carbs"   : carbs,
        "fat"     : fat,
        "serving" : "per 100g",
        "source"  : "USDA FoodData Central",
    }


def _fallback_nutrition(food_label: str) -> dict:
    return {
        "food"    : food_label.replace("_", " ").title(),
        "calories": None,
        "protein" : None,
        "carbs"   : None,
        "fat"     : None,
        "serving" : None,
        "error"   : "Nutrition data unavailable. Please enter manually.",
    }