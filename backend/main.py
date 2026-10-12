import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from routers import predict, label, chat, menu, profile
from services.nutrition_service import get_nutrition as _get_nutrition
from services.ood_service import estimate_named_food
from services.s3_service import download_food_photo

app = FastAPI(
    title       = "NutriScan AI",
    description = "AI-powered food nutrition scanner with personalized coaching.",
    version     = "2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = [
        "http://localhost:3000",
        "https://nutri-scan-ai-food-scanner.vercel.app",
    ],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.include_router(predict.router, tags=["Prediction"])
app.include_router(label.router,   tags=["Labeling"])
app.include_router(chat.router,    tags=["AI Coach"])
app.include_router(menu.router,    tags=["Menu Scanner"])
app.include_router(profile.router, tags=["Profile"])


@app.get("/")
def root():
    return {"status": "running", "message": "NutriScan AI API is live."}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/nutrition")
async def get_nutrition_by_name(
    food : str = Query(...),
    grams: Optional[float] = Query(None, gt=0, le=3000),
):
    """
    Fetch nutrition for any food name typed by the user.
    First tries USDA — if nothing found falls back to GPT-4o.
    Handles informal names like 'cheese hamburger', 'pomplet fry', 'dal makhani'.

    Both sources give values per 100g. When `grams` is passed (the portion
    weight estimated at scan time), values are scaled to that portion so an
    edited meal is logged at its real size, not as 100g.
    """
    result = await _nutrition_per_100g(food)

    if grams and result.get("calories") is not None:
        factor = grams / 100.0
        result = {
            **result,
            "calories": round(result["calories"] * factor),
            "protein" : round((result.get("protein") or 0) * factor, 1),
            "carbs"   : round((result.get("carbs")   or 0) * factor, 1),
            "fat"     : round((result.get("fat")     or 0) * factor, 1),
            "serving" : f"{round(grams)}g",
        }

    return result


class EstimateRequest(BaseModel):
    food     : str = Field(..., min_length=1, max_length=120)
    image_url: Optional[str] = None
    grams    : Optional[float] = Field(None, gt=0, le=3000)


@app.post("/nutrition/estimate")
async def estimate_corrected_food(request: EstimateRequest):
    """
    Called when the user corrects a scanned food's name.
    Sends the original photo plus the corrected name to GPT-4o so the whole
    plate is estimated. Falls back to the per-100g lookup scaled by `grams`
    if the photo is missing or GPT-4o fails.
    """
    food = request.food.strip()
    if not food:
        raise HTTPException(status_code=400, detail="Food name cannot be empty.")

    image_bytes = download_food_photo(request.image_url) if request.image_url else None
    if image_bytes:
        estimate = await estimate_named_food(image_bytes, food)
        if estimate:
            return {
                **estimate,
                "serving": f"{estimate['weight_grams']}g" if estimate.get("weight_grams") else "full plate",
                "source" : "gpt4o_photo",
            }

    return await get_nutrition_by_name(food=food, grams=request.grams)


async def _nutrition_per_100g(food: str) -> dict:
    import httpx
    import json

    # Step 1 — Try USDA first
    result = await _get_nutrition(food)

    # Step 2 — If USDA returned nothing → use GPT-4o
    if not result.get("calories"):
        openai_api_key = os.getenv("OPENAI_API_KEY")

        payload = {
            "model": "gpt-4o",
            "messages": [{
                "role": "user",
                "content": (
                    f"You are a nutrition expert. The user described their food as: '{food}'. "
                    f"Understand what food this is regardless of how it's described — "
                    f"it could be a casual description, a regional name, or a detailed description like 'hamburger with 3 layers of cheese'. "
                    f"Identify the food and give accurate nutrition per 100g. "
                    f"Respond ONLY with JSON, no extra text:\n"
                    '{{"calories": number, "protein": number, "carbs": number, "fat": number, "food_name": "clean food name"}}'
                )
            }],
            "max_tokens" : 100,
            "temperature": 0.1,
        }

        headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type" : "application/json",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            )

        if response.status_code == 200:
            try:
                content = response.json()["choices"][0]["message"]["content"].strip()
                clean   = content.replace("```json", "").replace("```", "").strip()
                data    = json.loads(clean)
                return {
                    "food"    : food,
                    "calories": round(data.get("calories", 0)),
                    "protein" : round(data.get("protein",  0), 1),
                    "carbs"   : round(data.get("carbs",    0), 1),
                    "fat"     : round(data.get("fat",      0), 1),
                    "serving" : "per 100g",
                    "source"  : "gpt4o",
                }
            except Exception:
                pass

    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)