import type { ScanResult } from "./nutriscan-data"
import type { LoggedMeal, UserProfile } from "./store"

import { auth } from "./firebase"

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

// ── Signed-in requests ────────────────────────────────────────────────────
// Every backend call carries the user's Firebase ID token; the API rejects
// requests without one.
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const user = auth.currentUser
  if (user) headers.set("Authorization", `Bearer ${await user.getIdToken()}`)
  return fetch(`${API_URL}${path}`, { ...init, headers })
}

// Turns an error response into a message a user can act on.
export async function apiErrorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json()
    if (typeof data?.detail === "string" && data.detail.trim()) return data.detail
  } catch { /* not JSON */ }
  if (response.status === 401) return "Please sign in again."
  if (response.status === 413) return "That photo is too large. Please use one under 10MB."
  if (response.status === 429) return "You've reached the limit for now. Please try again a little later."
  if (response.status >= 500) return "Our server had a problem. Please try again in a moment."
  return "Something went wrong. Please try again."
}

// ── Scan food photo ───────────────────────────────────────────────────────
export async function scanFood(file: File): Promise<ScanResult> {
  const formData = new FormData()
  formData.append("file", file)

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 120000) // 2 min timeout

  const response = await apiFetch("/predict", {
    method: "POST",
    body: formData,
    signal: controller.signal,
  })
  clearTimeout(timeout)

  if (!response.ok) throw new Error(await apiErrorMessage(response))

  const data = await response.json()

  return {
    name: data.food ?? "Unknown food",
    confidence: data.confidence ?? 0,
    calories: data.calories ?? 0,
    macros: {
      protein: data.protein ?? 0,
      carbs: data.carbs ?? 0,
      fat: data.fat ?? 0,
    },
    // The S3 copy is private; preview the photo straight from the device.
    image: URL.createObjectURL(file),
    predictions: (data.top5 ?? []).map((p: { food: string; confidence: number }) => ({
      name: p.food.replace(/_/g, " "),
      confidence: Math.round(p.confidence * 100),
    })),
    weightGrams: data.weight_grams,
    serving: data.serving,
    source: data.source,
    isOod: data.is_ood,
    message: data.message,
    imageUrl: data.image_url,
  }
}

// ── AI Nutrition Coach ────────────────────────────────────────────────────
export type ChatMessage = {
  role: "user" | "coach"
  content: string
}

export async function askCoach(
  message: string,
  meals: LoggedMeal[],
  profile: UserProfile,
  userName: string,
  history: ChatMessage[] = [],
): Promise<string> {
  const response = await apiFetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      meals: meals.map((m) => ({
        name: m.name,
        calories: m.calories,
        protein: m.protein,
        carbs: m.carbs,
        fat: m.fat,
        meal: m.meal,
        time: m.time,
      })),
      daily_goal: profile.dailyGoal,
      protein_goal: profile.proteinGoal,
      fitness_goal: profile.fitnessGoal,
      activity_level: profile.activityLevel,
      user_name: userName,
      history: history.map((m) => ({
        role: m.role === "coach" ? "assistant" : "user",
        content: m.content.slice(0, 2000),
      })),
    }),
  })

  if (!response.ok) throw new Error(await apiErrorMessage(response))
  const data = await response.json()
  return data.reply
}

// ── Restaurant menu scanner ───────────────────────────────────────────────
export type MenuDish = {
  name: string
  estimated_calories: number
  protein: number
  carbs: number
  fat: number
  reason: string
}

export type MenuScanResult = {
  recommendations: MenuDish[]
  avoid: string[]
  summary: string
  remaining_calories: number
}

export async function scanMenu(
  file: File,
  caloriesConsumed: number,
  dailyGoal: number,
  proteinConsumed: number,
  proteinGoal: number,
): Promise<MenuScanResult> {
  const formData = new FormData()
  formData.append("file", file)
  formData.append("calories_consumed", String(caloriesConsumed))
  formData.append("daily_goal", String(dailyGoal))
  formData.append("protein_consumed", String(proteinConsumed))
  formData.append("protein_goal", String(proteinGoal))

  const response = await apiFetch("/scan-menu", {
    method: "POST",
    body: formData,
  })

  if (!response.ok) throw new Error(await apiErrorMessage(response))
  return response.json()
}

// ── Calculate personalized goals ──────────────────────────────────────────
export async function calculateGoals(
  weightKg: number,
  age: number,
  fitnessGoal: string,
  activityLevel: string,
  gender: "male" | "female",
  heightCm: number,
): Promise<{ daily_goal: number; protein_goal: number; fitness_goal: string; notes: string[] }> {
  const params = new URLSearchParams({
    weight_kg: String(weightKg),
    age: String(age),
    fitness_goal: fitnessGoal,
    activity_level: activityLevel,
    gender,
    height_cm: String(heightCm),
  })

  const response = await apiFetch(`/goals/calculate?${params}`, {
    method: "POST",
  })

  if (!response.ok) throw new Error(await apiErrorMessage(response))
  return response.json()
}