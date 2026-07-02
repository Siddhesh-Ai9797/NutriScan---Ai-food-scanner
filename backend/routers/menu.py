from fastapi import APIRouter, UploadFile, File, Form, HTTPException
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


@router.post("/scan-menu", response_model=MenuScanResponse)
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

    # Validate file
    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(status_code=400, detail="Invalid file type.")

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large. Max 10MB.")

    image_b64          = base64.b64encode(image_bytes).decode("utf-8")
    remaining_calories = max(daily_goal - calories_consumed, 0)
    remaining_protein  = max(protein_goal - protein_consumed, 0)

    prompt = f"""You are a nutrition expert helping a user choose the best dishes from a restaurant menu.

USER'S CURRENT STATUS:
- Calories remaining today: {remaining_calories} kcal
- Protein remaining today : {remaining_protein}g
- Daily calorie goal      : {daily_goal} kcal
- Daily protein goal      : {protein_goal}g

Look at this restaurant menu and recommend the TOP 3 best dishes based on the user's remaining nutrition goals.
Also identify 2-3 dishes to avoid and why.

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

If you cannot read the menu clearly, return recommendations as an empty array and explain in summary."""

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
        "temperature": 0.3,
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