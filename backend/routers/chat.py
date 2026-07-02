from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import httpx
import os
import json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

router = APIRouter()

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GPT_MODEL  = "gpt-4o"


class MealContext(BaseModel):
    name    : str
    calories: int
    protein : float
    carbs   : float
    fat     : float
    meal    : str
    time    : str


class ChatRequest(BaseModel):
    message       : str
    meals         : List[MealContext]
    daily_goal    : int            = 2000
    protein_goal  : int            = 150
    user_name     : Optional[str]  = "User"
    fitness_goal  : Optional[str]  = "maintaining"  # cutting / bulking / maintaining
    weight_kg     : Optional[float]= None
    activity_level: Optional[str]  = "moderate"


class ChatResponse(BaseModel):
    reply      : str
    suggestions: List[str] = []


def build_meal_context(meals: List[MealContext], daily_goal: int, protein_goal: int) -> str:
    if not meals:
        return "The user has not logged any meals today."

    total_calories = sum(m.calories for m in meals)
    total_protein  = sum(m.protein  for m in meals)
    total_carbs    = sum(m.carbs    for m in meals)
    total_fat      = sum(m.fat      for m in meals)

    remaining_calories = max(daily_goal - total_calories, 0)
    remaining_protein  = max(protein_goal - total_protein, 0)

    meal_lines = "\n".join([
        f"- {m.time} ({m.meal}): {m.name} | {m.calories} kcal | P:{m.protein}g C:{m.carbs}g F:{m.fat}g"
        for m in meals
    ])

    return f"""
USER'S MEAL LOG TODAY:
{meal_lines}

DAILY SUMMARY:
- Calories consumed : {total_calories} / {daily_goal} kcal ({remaining_calories} remaining)
- Protein consumed  : {total_protein}g / {protein_goal}g ({remaining_protein}g remaining)
- Carbs consumed    : {total_carbs}g
- Fat consumed      : {total_fat}g
""".strip()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured.")

    meal_context = build_meal_context(
        request.meals,
        request.daily_goal,
        request.protein_goal
    )

    fitness_context = {
        "cutting"    : "The user is in a calorie deficit trying to lose fat. Prioritize high protein, low calorie foods.",
        "bulking"    : "The user is in a calorie surplus trying to build muscle. Encourage hitting calorie and protein goals.",
        "maintaining": "The user wants to maintain their current weight. Balance is key.",
    }.get(request.fitness_goal or "maintaining", "The user wants to maintain their weight.")

    system_prompt = f"""You are NutriCoach, a friendly and knowledgeable AI nutrition coach inside the NutriScan app.

USER PROFILE:
- Name          : {request.user_name}
- Fitness goal  : {request.fitness_goal} ({fitness_context})
- Daily calories: {request.daily_goal} kcal
- Protein goal  : {request.protein_goal}g
- Activity level: {request.activity_level}

{meal_context}

RULES:
- Always be friendly, encouraging and specific
- Reference their actual meals by name when relevant
- Give concrete numbers (e.g. "you need 96g more protein today")
- Suggest real foods based on their FITNESS GOAL
- If cutting → suggest high protein low calorie options
- If bulking → encourage hitting calorie surplus with nutrient dense foods
- If maintaining → suggest balanced meals
- Keep responses concise — 2-4 sentences max unless they ask for detail
- Never make up meal data — only reference what is in their log
- Suggest Indian foods, Asian foods and international cuisines when relevant
- When they ask what to eat for a meal → calculate remaining macros and suggest 2-3 specific dishes
- End with one actionable suggestion"""

    payload = {
        "model"      : GPT_MODEL,
        "messages"   : [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": request.message},
        ],
        "max_tokens" : 300,
        "temperature": 0.7,
    }

    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "Content-Type" : "application/json",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(OPENAI_URL, headers=headers, json=payload)

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="AI coach unavailable. Try again.")

    reply = response.json()["choices"][0]["message"]["content"].strip()

    suggestions = []
    if "•" in reply or "-" in reply:
        lines = reply.split("\n")
        suggestions = [
            l.lstrip("•- ").strip()
            for l in lines
            if l.strip().startswith(("•", "-")) and len(l.strip()) > 3
        ][:3]

    return ChatResponse(reply=reply, suggestions=suggestions)