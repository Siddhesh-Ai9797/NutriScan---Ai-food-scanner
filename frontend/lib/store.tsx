"use client"

import { createContext, useContext, useState, useCallback, type ReactNode } from "react"
import type { ScanResult, MealCategory } from "./nutriscan-data"
import { DAILY_GOAL } from "./nutriscan-data"
import { fetchTodayMeals } from "./meals"

export type LoggedMeal = {
  id      : string
  name    : string
  calories: number
  protein : number
  carbs   : number
  fat     : number
  meal    : MealCategory
  time    : string
  image   : string
}

type StoreState = {
  userName      : string
  dailyGoal     : number
  loggedMeals   : LoggedMeal[]
  logMeal       : (result: ScanResult, meal: MealCategory) => void
  removeMeal    : (id: string) => void
  loadMeals     : (uid: string) => Promise<void>
  totalCalories : number
  mealBreakdown : { meal: MealCategory; label: string; calories: number }[]
}

const StoreContext = createContext<StoreState | null>(null)

const MEAL_LABELS: Record<MealCategory, string> = {
  breakfast: "Breakfast",
  lunch    : "Lunch",
  dinner   : "Dinner",
  snacks   : "Snacks",
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [loggedMeals, setLoggedMeals] = useState<LoggedMeal[]>([])

  const logMeal = useCallback((result: ScanResult, meal: MealCategory) => {
    const newMeal: LoggedMeal = {
      id      : crypto.randomUUID(),
      name    : result.name,
      calories: result.calories,
      protein : result.macros.protein,
      carbs   : result.macros.carbs,
      fat     : result.macros.fat,
      meal,
      time    : `Today, ${formatTime(new Date())}`,
      image   : result.image,
    }
    setLoggedMeals((prev) => [newMeal, ...prev])
  }, [])

  const loadMeals = useCallback(async (uid: string) => {
    try {
      const meals = await fetchTodayMeals(uid)
      const mapped: LoggedMeal[] = meals.map((m) => ({
        id      : m.id,
        name    : m.name,
        calories: m.calories,
        protein : m.protein,
        carbs   : m.carbs,
        fat     : m.fat,
        meal    : m.meal,
        time    : `Today, ${new Date(m.createdAt.toDate()).toLocaleTimeString([], {
          hour  : "2-digit",
          minute: "2-digit",
        })}`,
        image   : m.imageUrl ?? "",
      }))
      setLoggedMeals(mapped)
    } catch (err) {
      console.error("Failed to load meals:", err)
    }
  }, [])

  const removeMeal = useCallback((id: string) => {
    setLoggedMeals((prev) => prev.filter((m) => m.id !== id))
  }, [])

  const totalCalories = loggedMeals.reduce((sum, m) => sum + m.calories, 0)

  const mealBreakdown = (["breakfast", "lunch", "dinner", "snacks"] as MealCategory[]).map(
    (meal) => ({
      meal,
      label   : MEAL_LABELS[meal],
      calories: loggedMeals
        .filter((m) => m.meal === meal)
        .reduce((sum, m) => sum + m.calories, 0),
    })
  )

  return (
    <StoreContext.Provider
      value={{
        userName: "Alex",
        dailyGoal: DAILY_GOAL,
        loggedMeals,
        logMeal,
        removeMeal,
        loadMeals,
        totalCalories,
        mealBreakdown,
      }}
    >
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
  if (hour < 10) return "breakfast"
  if (hour < 14) return "lunch"
  if (hour < 19) return "dinner"
  return "snacks"
}