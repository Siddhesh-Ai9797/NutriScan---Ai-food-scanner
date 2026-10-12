from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Literal

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


# Safety limits. Below these, an unsupervised app should not set a target.
MIN_CALORIES = {"female": 1200, "male": 1500}
MAX_DEFICIT_FRACTION = 0.20      # never cut more than 20% below maintenance
MAX_PROTEIN_G = 220              # cap for very heavy users


@router.post("/goals/calculate")
def calculate_goals(
    weight_kg     : float = Query(..., ge=25, le=300, description="Body weight in kg"),
    age           : int   = Query(..., ge=13, le=100),
    fitness_goal  : Literal["cutting", "bulking", "maintaining"] = "maintaining",
    activity_level: Literal["sedentary", "moderate", "active"]   = "moderate",
    gender        : Literal["male", "female"]                    = "male",
    height_cm     : float = Query(170, ge=120, le=230),
):
    """
    Calculate personalized calorie and protein goals using
    Mifflin-St Jeor equation + activity multiplier, with safety limits.
    """
    # Mifflin-St Jeor BMR
    if gender == "male":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

    multipliers = {"sedentary": 1.2, "moderate": 1.55, "active": 1.725}
    tdee = bmr * multipliers[activity_level]

    notes = []
    effective_goal = fitness_goal
    if age < 18 and fitness_goal == "cutting":
        effective_goal = "maintaining"
        notes.append("We don't set calorie deficits for users under 18. Talk to a doctor before dieting.")

    if effective_goal == "cutting":
        daily_goal   = max(tdee - 400, tdee * (1 - MAX_DEFICIT_FRACTION))
        protein_goal = weight_kg * 2.2
    elif effective_goal == "bulking":
        daily_goal   = tdee + 300
        protein_goal = weight_kg * 2.0
    else:
        daily_goal   = tdee
        protein_goal = weight_kg * 1.8

    floor = MIN_CALORIES[gender]
    if daily_goal < floor:
        daily_goal = floor
        notes.append(
            f"Your calculated target was below {floor} kcal, so we set it to {floor} kcal. "
            "Please check with a doctor or dietitian before eating less than this."
        )
    if protein_goal > MAX_PROTEIN_G:
        protein_goal = MAX_PROTEIN_G

    return {
        "bmr"         : round(bmr),
        "tdee"        : round(tdee),
        "daily_goal"  : round(daily_goal),
        "protein_goal": round(protein_goal),
        "fitness_goal": effective_goal,
        "notes"       : notes,
    }