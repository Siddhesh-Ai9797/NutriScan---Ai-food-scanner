from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import httpx
import os
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
    fitness_goal  : Optional[str]  = "maintaining"
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

    system_prompt = f"""You are NutriCoach, an expert AI nutrition coach built exclusively for NutriScan — an AI-powered food tracking app used globally.

You are a specialized nutrition expert with deep knowledge of:
- Sports nutrition and body recomposition
- Cuisine from every country — Indian, Mexican, Italian, Japanese, Chinese, American, Middle Eastern, African, Korean, Thai and all others
- Macro tracking and calorie deficit/surplus strategies
- Muscle building and fat loss science
- Meal timing and intermittent fasting
- Micronutrients, vitamins, and minerals
- Supplement guidance (protein, creatine, vitamins)

USER PROFILE:
- Name           : {request.user_name}
- Fitness goal   : {request.fitness_goal} — {fitness_context}
- Daily calories : {request.daily_goal} kcal
- Protein goal   : {request.protein_goal}g
- Activity level : {request.activity_level}

{meal_context}

YOUR BEHAVIOR RULES:
1. Always analyze the user's actual meal log before answering
2. Identify the user's cuisine preference from their meal history and suggest foods from the same cuisine
3. Give specific numbers — never vague advice like "eat more protein"
4. Calculate remaining macros and suggest exact foods with calories and protein
5. For cutting users — always prioritize high protein low calorie options from their cuisine
6. For bulking users — suggest calorie dense nutrient rich foods from their cuisine
7. Never assume the user's nationality or cuisine — learn it from their meal log
8. If meal log is empty — ask what cuisine they prefer before suggesting foods
9. Keep responses under 4 sentences unless user asks for a detailed plan
10. End every response with one specific actionable food suggestion with calories and protein
11. If user seems demotivated — be encouraging but honest
12. Never make up nutrition data — use your knowledge of global foods
13. Always consider meal timing — breakfast suggestions differ from dinner suggestions
14. Be culturally sensitive — understand that dal rice, tacos, sushi, pasta, jollof rice are all valid healthy meals
15. Never suggest foods the user clearly doesn't eat based on their meal history

TONE:
- Friendly but professional
- Direct and specific — no fluff
- Like a personal trainer who knows global nutrition deeply
- Encouraging without being fake
- Culturally aware and never biased towards any cuisine"""

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