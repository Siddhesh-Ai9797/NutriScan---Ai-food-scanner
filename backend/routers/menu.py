from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from services.auth_service import rate_limit
from services.image_service import normalize_image, ImageError, NOT_AN_IMAGE
from pydantic import BaseModel
from typing import List, Optional
import httpx
import os
import json
import base64
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

router = APIRouter()

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GPT_MODEL  = "gpt-4o"


class MenuDish(BaseModel):
    name            : str
    estimated_calories: int
    protein         : float
    carbs           : float
    fat             : float
    reason          : str   # why this is recommended


class MenuScanResponse(BaseModel):
    recommendations : List[MenuDish]
    avoid           : List[str]
    summary         : str
    remaining_calories: int


@router.post("/scan-menu", response_model=MenuScanResponse, dependencies=[Depends(rate_limit("menu", 30))])
async def scan_menu(
    file              : UploadFile = File(...),
    calories_consumed : int        = Form(0),
    daily_goal        : int        = Form(2000),
    protein_consumed  : float      = Form(0),
    protein_goal      : int        = Form(150),
):
    """
    Upload a restaurant menu photo → get personalized dish recommendations
    based on the user's remaining calories and protein goal for the day.
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured.")

    # Validate and normalise the photo (JPEG, PNG, WEBP, iPhone HEIC...)
    if file.content_type and not (
        file.content_type.startswith("image/") or file.content_type == "application/octet-stream"
    ):
        raise HTTPException(status_code=400, detail=NOT_AN_IMAGE)
    try:
        image_bytes = normalize_image(await file.read())
    except ImageError as e:
        raise HTTPException(status_code=400, detail=str(e))

    image_b64          = base64.b64encode(image_bytes).decode("utf-8")
    remaining_calories = max(daily_goal - calories_consumed, 0)
    remaining_protein  = max(protein_goal - protein_consumed, 0)
    over_by            = max(calories_consumed - daily_goal, 0)
    if over_by > 0:
        budget_note = f"The user is already OVER their calorie goal by {over_by} kcal today."
    elif remaining_calories < 400:
        budget_note = f"The user only has {remaining_calories} kcal left today, which is less than a typical restaurant dish."
    else:
        budget_note = "The user has a normal amount of calories left for a meal."

    prompt = f"""You are a nutrition expert helping a user choose the best dishes from a restaurant menu.

USER'S CURRENT STATUS:
- Calories remaining today: {remaining_calories} kcal
- Protein remaining today : {remaining_protein}g
- Daily calorie goal      : {daily_goal} kcal
- Daily protein goal      : {protein_goal}g
- Budget situation        : {budget_note}

Look at this restaurant menu and recommend the TOP 3 best dishes based on the user's remaining nutrition goals.
Also identify 2-3 dishes to avoid and why.

Every "reason", "avoid" and "summary" text is shown directly to the user, so speak to them as "you" and "your"
(e.g. "fits your remaining calories"). Never say "the user".

Respond ONLY with a JSON object in this exact format, no extra text:
{{
  "recommendations": [
    {{
      "name": "dish name",
      "estimated_calories": number,
      "protein": number in grams,
      "carbs": number in grams,
      "fat": number in grams,
      "reason": "why this fits their goals"
    }}
  ],
  "avoid": ["dish name - reason", "dish name - reason"],
  "summary": "2 sentence summary of best strategy for this meal"
}}

IMPORTANT RULES:
- Restaurant menus almost never print nutrition facts. Estimate calories and macros yourself from each dish
  name using typical restaurant portions. Never refuse or return an empty list because nutrition facts are missing.
- Read menus in any language. Write each dish name as printed, followed by an English translation in
  brackets if it is not in English.
- If the user is low on calories or already over their goal, still recommend the 1 to 3 lightest, most
  protein-dense options, and use the summary to suggest a smaller portion, sharing, or a side dish.
  Do not tell them to skip meals.
- Only return recommendations as an empty array if you genuinely cannot read ANY dish names, for example
  a blank, very blurry, or non-menu image. Then explain that in the summary."""

    payload = {
        "model"  : GPT_MODEL,
        "messages": [
            {
                "role"   : "user",
                "content": [
                    {
                        "type"     : "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "max_tokens" : 600,
        "temperature": 0.2,
    }

    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "Content-Type" : "application/json",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(OPENAI_URL, headers=headers, json=payload)

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Menu scanner unavailable. Try again.")

    content = response.json()["choices"][0]["message"]["content"].strip()

    try:
        clean = content.replace("```json", "").replace("```", "").strip()
        data  = json.loads(clean)

        return MenuScanResponse(
            recommendations   = data.get("recommendations", []),
            avoid             = data.get("avoid", []),
            summary           = data.get("summary", ""),
            remaining_calories= remaining_calories,
        )
    except (json.JSONDecodeError, KeyError):
        raise HTTPException(status_code=500, detail="Could not parse menu. Try a clearer photo.")