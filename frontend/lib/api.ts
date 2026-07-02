import type { ScanResult } from "./nutriscan-data"
import type { LoggedMeal, UserProfile } from "./store"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

// ── Scan food photo ───────────────────────────────────────────────────────
export async function scanFood(file: File): Promise<ScanResult> {
  const formData = new FormData()
  formData.append("file", file)

  const response = await fetch(`${API_URL}/predict`, {
    method: "POST",
    body  : formData,
  })

  if (!response.ok) throw new Error(`API error: ${response.statusText}`)

  const data = await response.json()

  return {
    name       : data.food ?? "Unknown food",
    confidence : data.confidence ?? 0,
    calories   : data.calories ?? 0,
    macros     : {
      protein: data.protein ?? 0,
      carbs  : data.carbs   ?? 0,
      fat    : data.fat     ?? 0,
    },
    image      : URL.createObjectURL(file),
    predictions: (data.top5 ?? []).map((p: { food: string; confidence: number }) => ({
      name      : p.food.replace(/_/g, " "),
      confidence: Math.round(p.confidence * 100),
    })),
    weightGrams: data.weight_grams,
    serving    : data.serving,
    source     : data.source,
    isOod      : data.is_ood,
    message    : data.message,
  }
}

// ── AI Nutrition Coach ────────────────────────────────────────────────────
export type ChatMessage = {
  role   : "user" | "coach"
  content: string
}

export async function askCoach(
  message : string,
  meals   : LoggedMeal[],
  profile : UserProfile,
  userName: string,
): Promise<string> {
  const response = await fetch(`${API_URL}/chat`, {
    method : "POST",
    headers: { "Content-Type": "application/json" },
    body   : JSON.stringify({
      message,
      meals: meals.map((m) => ({
        name    : m.name,
        calories: m.calories,
        protein : m.protein,
        carbs   : m.carbs,
        fat     : m.fat,
        meal    : m.meal,
        time    : m.time,
      })),
      daily_goal    : profile.dailyGoal,
      protein_goal  : profile.proteinGoal,
      fitness_goal  : profile.fitnessGoal,
      activity_level: profile.activityLevel,
      user_name     : userName,
    }),
  })

  if (!response.ok) throw new Error("Coach unavailable")
  const data = await response.json()
  return data.reply
}

// ── Restaurant menu scanner ───────────────────────────────────────────────
export type MenuDish = {
  name              : string
  estimated_calories: number
  protein           : number
  carbs             : number
  fat               : number
  reason            : string
}

export type MenuScanResult = {
  recommendations   : MenuDish[]
  avoid             : string[]
  summary           : string
  remaining_calories: number
}

export async function scanMenu(
  file            : File,
  caloriesConsumed: number,
  dailyGoal       : number,
  proteinConsumed : number,
  proteinGoal     : number,
): Promise<MenuScanResult> {
  const formData = new FormData()
  formData.append("file",             file)
  formData.append("calories_consumed", String(caloriesConsumed))
  formData.append("daily_goal",        String(dailyGoal))
  formData.append("protein_consumed",  String(proteinConsumed))
  formData.append("protein_goal",      String(proteinGoal))

  const response = await fetch(`${API_URL}/scan-menu`, {
    method: "POST",
    body  : formData,
  })

  if (!response.ok) throw new Error("Menu scanner unavailable")
  return response.json()
}

// ── Calculate personalized goals ──────────────────────────────────────────
export async function calculateGoals(
  weightKg     : number,
  age          : number,
  fitnessGoal  : string,
  activityLevel: string,
  gender       : string = "male",
) {
  const params = new URLSearchParams({
    weight_kg     : String(weightKg),
    age           : String(age),
    fitness_goal  : fitnessGoal,
    activity_level: activityLevel,
    gender,
  })

  const response = await fetch(`${API_URL}/goals/calculate?${params}`, {
    method: "POST",
  })

  if (!response.ok) throw new Error("Goal calculation failed")
  return response.json()
}