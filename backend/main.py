import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from routers import predict, label, chat, menu, profile
from services.nutrition_service import get_nutrition as _get_nutrition, NotAFoodError
from services.ood_service import estimate_named_food
from services.s3_service import download_food_photo, signed_photo_url
from services.auth_service import require_user, require_admin, rate_limit

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

# Every router needs a signed-in user; paid endpoints add per-user limits on top.
_signed_in = [Depends(require_user)]
app.include_router(predict.router, tags=["Prediction"],   dependencies=_signed_in)
app.include_router(label.router,   tags=["Labeling"],     dependencies=_signed_in)
app.include_router(chat.router,    tags=["AI Coach"],     dependencies=_signed_in)
app.include_router(menu.router,    tags=["Menu Scanner"], dependencies=_signed_in)
app.include_router(profile.router, tags=["Profile"],      dependencies=_signed_in)


@app.get("/")
def root():
    return {"status": "running", "message": "NutriScan AI API is live."}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/admin/me", dependencies=[Depends(require_admin)])
def admin_me():
    """Lets the /admin page check access without exposing the admin email."""
    return {"admin": True}


class PhotoLinksRequest(BaseModel):
    urls: list[str] = Field(default_factory=list, max_length=50)


@app.post("/admin/photo-links", dependencies=[Depends(require_admin)])
def admin_photo_links(request: PhotoLinksRequest):
    """15-minute read links for user photos shown on the admin page. The bucket itself is private."""
    links = {url: signed_photo_url(url) for url in request.urls}
    return {"links": {url: link for url, link in links.items() if link}}


NOT_A_FOOD = "We don't recognise \"{food}\" as a food. Please check the spelling or try another name."


@app.get("/nutrition", dependencies=[Depends(rate_limit("nutrition", 60))])
async def get_nutrition_by_name(
    food : str = Query(..., min_length=1, max_length=120),
    grams: Optional[float] = Query(None, gt=0, le=3000),
):
    """
    Nutrition for any food name typed by the user, per 100g as normally eaten.
    Handles informal names like 'cheese hamburger', 'pomplet fry', 'dal makhani'.
    When `grams` is passed (the portion weight estimated at scan time), values
    are scaled to that portion so an edited meal is logged at its real size.
    """
    food = food.strip()
    if not food:
        raise HTTPException(status_code=400, detail="Food name cannot be empty.")
    try:
        result = await _get_nutrition(food)
    except NotAFoodError:
        raise HTTPException(status_code=400, detail=NOT_A_FOOD.format(food=food))
    if result is None:
        raise HTTPException(status_code=503, detail="Nutrition lookup is unavailable right now. Please try again.")

    if grams:
        factor = grams / 100.0
        result = {
            **result,
            "calories": round(result["calories"] * factor),
            "protein" : round(result["protein"] * factor, 1),
            "carbs"   : round(result["carbs"]   * factor, 1),
            "fat"     : round(result["fat"]     * factor, 1),
            "serving" : f"{round(grams)}g",
        }
    return result


class EstimateRequest(BaseModel):
    food     : str = Field(..., min_length=1, max_length=120)
    image_url: Optional[str] = None
    grams    : Optional[float] = Field(None, gt=0, le=3000)


@app.post("/nutrition/estimate", dependencies=[Depends(rate_limit("nutrition", 60))])
async def estimate_corrected_food(request: EstimateRequest):
    """
    Called when the user corrects a scanned food's name.
    Sends the original photo plus the corrected name to GPT-4o so the whole
    plate is estimated, keeping the portion from the scan. Falls back to the
    per-100g lookup scaled by `grams` if the photo is missing or GPT-4o fails.
    """
    food = request.food.strip()
    if not food:
        raise HTTPException(status_code=400, detail="Food name cannot be empty.")

    image_bytes = download_food_photo(request.image_url) if request.image_url else None
    if image_bytes:
        try:
            estimate = await estimate_named_food(image_bytes, food, grams=request.grams)
        except NotAFoodError:
            raise HTTPException(status_code=400, detail=NOT_A_FOOD.format(food=food))
        if estimate:
            return {
                **estimate,
                "serving": f"{estimate['weight_grams']}g" if estimate.get("weight_grams") else "full plate",
                "source" : "gpt4o_photo",
            }

    return await get_nutrition_by_name(food=food, grams=request.grams)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)