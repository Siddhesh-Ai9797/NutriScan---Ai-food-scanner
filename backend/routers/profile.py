from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class UserProfile(BaseModel):
    user_id       : str
    display_name  : str
    email         : str
    daily_goal    : int   = 2000
    protein_goal  : int   = 150
    fitness_goal  : str   = "maintaining"   # cutting / bulking / maintaining
    activity_level: str   = "moderate"      # sedentary / moderate / active
    weight_kg     : Optional[float] = None
    age           : Optional[int]   = None


class ProfileResponse(BaseModel):
    status : str
    profile: UserProfile


# ── Recommended goals based on fitness goal ───────────────────────────────
GOAL_PRESETS = {
    "cutting": {
        "daily_goal"  : 1700,
        "protein_goal": 160,
        "description" : "Calorie deficit — lose fat while preserving muscle",
    },
    "bulking": {
        "daily_goal"  : 2800,
        "protein_goal": 180,
        "description" : "Calorie surplus — build muscle mass",
    },
    "maintaining": {
        "daily_goal"  : 2200,
        "protein_goal": 150,
        "description" : "Maintenance — stay at current weight",
    },
}


@router.get("/goals/presets")
def get_goal_presets():
    """Returns recommended calorie and protein targets for each fitness goal."""
    return GOAL_PRESETS


@router.post("/goals/calculate")
def calculate_goals(
    weight_kg     : float,
    age           : int,
    fitness_goal  : str   = "maintaining",
    activity_level: str   = "moderate",
    gender        : str   = "male",
):
    """
    Calculate personalized calorie and protein goals using
    Mifflin-St Jeor equation + activity multiplier.
    """
    # Mifflin-St Jeor BMR
    if gender == "male":
        bmr = 10 * weight_kg + 6.25 * 170 - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * 160 - 5 * age - 161

    # Activity multiplier
    multipliers = {
        "sedentary": 1.2,
        "moderate" : 1.55,
        "active"   : 1.725,
    }
    tdee = bmr * multipliers.get(activity_level, 1.55)

    # Adjust for fitness goal
    if fitness_goal == "cutting":
        daily_goal   = round(tdee - 400)
        protein_goal = round(weight_kg * 2.2)   # 2.2g per kg for cutting
    elif fitness_goal == "bulking":
        daily_goal   = round(tdee + 300)
        protein_goal = round(weight_kg * 2.0)   # 2g per kg for bulking
    else:
        daily_goal   = round(tdee)
        protein_goal = round(weight_kg * 1.8)   # 1.8g per kg for maintaining

    return {
        "bmr"         : round(bmr),
        "tdee"        : round(tdee),
        "daily_goal"  : daily_goal,
        "protein_goal": protein_goal,
        "fitness_goal": fitness_goal,
    }