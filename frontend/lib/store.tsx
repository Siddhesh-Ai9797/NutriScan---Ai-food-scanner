"use client"

import { createContext, useContext, useState, useCallback, type ReactNode } from "react"
import type { ScanResult, MealCategory } from "./nutriscan-data"
import { fetchTodayMeals, fetchWeeklyMeals, saveUserProfile, fetchUserProfile, saveWaterIntake, fetchWaterIntake } from "./meals"

export type LoggedMeal = {
  id: string
  name: string
  calories: number
  protein: number
  carbs: number
  fat: number
  meal: MealCategory
  time: string
  image: string
}

export type UserProfile = {
  dailyGoal: number
  proteinGoal: number
  fitnessGoal: "cutting" | "bulking" | "maintaining"
  activityLevel: "sedentary" | "moderate" | "active"
  weightKg: number | null
  age: number | null
  waterGoal: number   // ml per day
}

export type DayCalories = {
  date: string   // "Mon", "Tue" etc
  calories: number
}

type StoreState = {
  // Profile
  profile: UserProfile
  updateProfile: (p: Partial<UserProfile>, uid: string) => Promise<void>
  loadProfile: (uid: string) => Promise<void>

  // Meals
  loggedMeals: LoggedMeal[]
  logMeal: (result: ScanResult, meal: MealCategory) => void
  removeMeal: (id: string) => void
  loadMeals: (uid: string) => Promise<void>

  // Weekly chart data
  weeklyData: DayCalories[]
  loadWeekly: (uid: string) => Promise<void>

  // Water
  waterMl: number
  addWater: (ml: number, uid?: string) => void
  resetWater: () => void
  loadWater: (uid: string) => Promise<void>

  // Streak
  streak: number

  // Derived
  totalCalories: number
  totalProtein: number
  mealBreakdown: { meal: MealCategory; label: string; calories: number }[]
}

const DEFAULT_PROFILE: UserProfile = {
  dailyGoal: 2200,
  proteinGoal: 150,
  fitnessGoal: "maintaining",
  activityLevel: "moderate",
  weightKg: null,
  age: null,
  waterGoal: 2500,
}

const MEAL_LABELS: Record<MealCategory, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snacks: "Snacks",
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

const StoreContext = createContext<StoreState | null>(null)

export function StoreProvider({ children }: { children: ReactNode }) {
  const [userId, setUserId] = useState<string | null>(null)
  const [loggedMeals, setLoggedMeals] = useState<LoggedMeal[]>([])
  const [profile, setProfile] = useState<UserProfile>(DEFAULT_PROFILE)
  const [weeklyData, setWeeklyData] = useState<DayCalories[]>([])
  const [waterMl, setWaterMl] = useState(0)
  const [streak, setStreak] = useState(0)

  // ── Profile ────────────────────────────────────────────────────────────
  const loadProfile = useCallback(async (uid: string) => {
    try {
      const p = await fetchUserProfile(uid)
      if (p) setProfile({ ...DEFAULT_PROFILE, ...p })
    } catch (err) {
      console.error("Failed to load profile:", err)
    }
  }, [])

  const updateProfile = useCallback(async (updates: Partial<UserProfile>, uid: string) => {
    const newProfile = { ...profile, ...updates }
    setProfile(newProfile)
    try {
      await saveUserProfile(uid, newProfile)
    } catch (err) {
      console.error("Failed to save profile:", err)
    }
  }, [profile])

  // ── Meals ──────────────────────────────────────────────────────────────
  const logMeal = useCallback((result: ScanResult, meal: MealCategory) => {
    const newMeal: LoggedMeal = {
      id: crypto.randomUUID(),
      name: result.name,
      calories: result.calories,
      protein: result.macros.protein,
      carbs: result.macros.carbs,
      fat: result.macros.fat,
      meal,
      time: `Today, ${formatTime(new Date())}`,
      image: result.image,
    }
    setLoggedMeals((prev) => [newMeal, ...prev])
  }, [])

  const loadMeals = useCallback(async (uid: string) => {
    try {
      const meals = await fetchTodayMeals(uid)
      const mapped: LoggedMeal[] = meals.map((m) => ({
        id: m.id,
        name: m.name,
        calories: m.calories,
        protein: m.protein,
        carbs: m.carbs,
        fat: m.fat,
        meal: m.meal,
        time: `Today, ${new Date(m.createdAt.toDate()).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        })}`,
        image: m.imageUrl ?? "",
      }))
      setLoggedMeals(mapped)

      // Calculate streak from meal history
      if (meals.length > 0) setStreak((prev) => Math.max(prev, 1))
    } catch (err) {
      console.error("Failed to load meals:", err)
    }
  }, [])

  const removeMeal = useCallback((id: string) => {
    setLoggedMeals((prev) => prev.filter((m) => m.id !== id))
  }, [])

  // ── Weekly data ────────────────────────────────────────────────────────
  const loadWeekly = useCallback(async (uid: string) => {
    try {
      const meals = await fetchWeeklyMeals(uid)
      const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
      const map: Record<string, number> = {}

      meals.forEach((m) => {
        const d = new Date(m.createdAt.toDate())
        const day = days[d.getDay()]
        map[day] = (map[day] || 0) + m.calories
      })

      // Build last 7 days in order
      const today = new Date()
      const week: DayCalories[] = Array.from({ length: 7 }, (_, i) => {
        const d = new Date(today)
        d.setDate(today.getDate() - (6 - i))
        const key = days[d.getDay()]
        return { date: key, calories: map[key] || 0 }
      })

      setWeeklyData(week)
    } catch (err) {
      console.error("Failed to load weekly data:", err)
    }
  }, [])

  // ── Water ──────────────────────────────────────────────────────────────
  const loadWater = useCallback(async (uid: string) => {
    try {
      const ml = await fetchWaterIntake(uid)
      setWaterMl(ml)
    } catch (err) {
      console.error("Failed to load water:", err)
    }
  }, [])
  const addWater = useCallback((ml: number, uid?: string) => {
    setWaterMl((prev) => {
      const newTotal = prev + ml
      if (uid) saveWaterIntake(uid, newTotal)
      return newTotal
    })
  }, [])
  const resetWater = useCallback(() => setWaterMl(0), [])

  // ── Derived ────────────────────────────────────────────────────────────
  const totalCalories = loggedMeals.reduce((sum, m) => sum + m.calories, 0)
  const totalProtein = loggedMeals.reduce((sum, m) => sum + m.protein, 0)

  const mealBreakdown = (["breakfast", "lunch", "dinner", "snacks"] as MealCategory[]).map(
    (meal) => ({
      meal,
      label: MEAL_LABELS[meal],
      calories: loggedMeals
        .filter((m) => m.meal === meal)
        .reduce((sum, m) => sum + m.calories, 0),
    })
  )

  return (
    <StoreContext.Provider value={{
      profile,
      updateProfile,
      loadProfile,
      loggedMeals,
      logMeal,
      removeMeal,
      loadMeals,
      weeklyData,
      loadWeekly,
      waterMl,
      addWater,
      resetWater,
      loadWater,
      streak,
      totalCalories,
      totalProtein,
      mealBreakdown,
    }}>
      {children}
    </StoreContext.Provider>
  )
}

export function useStore() {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error("useStore must be used inside StoreProvider")
  return ctx
}

export function getCurrentMeal(): MealCategory {
  const hour = new Date().getHours()
  if (hour >= 6 && hour < 11) return "breakfast"
  if (hour >= 11 && hour < 15) return "lunch"
  if (hour >= 15 && hour < 18) return "snacks"
  if (hour >= 18 && hour < 22) return "dinner"
  return "snacks"   // 10 PM — 6 AM
}