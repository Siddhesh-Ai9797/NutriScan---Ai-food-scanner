export type Macros = {
  protein: number // grams
  carbs: number // grams
  fat: number // grams
}

export type Prediction = {
  name: string
  confidence: number // 0-100
}

export type ScanResult = {
  name: string
  confidence: number
  calories: number
  macros: Macros
  image: string
  predictions: Prediction[]
  weightGrams?: number
  serving?: string
  source?: string
  isOod?: boolean
  message?: string
}
export type MealCategory = "breakfast" | "lunch" | "dinner" | "snacks"

export type RecentScan = {
  id: string
  name: string
  calories: number
  time: string
  image: string
  meal: MealCategory
}

// Grams of macro -> calories (4 / 4 / 9)
export const MACRO_CALORIES = { protein: 4, carbs: 4, fat: 9 } as const

export const MACRO_META = {
  protein: { label: "Protein", token: "protein", unit: "g" },
  carbs: { label: "Carbs", token: "carbs", unit: "g" },
  fat: { label: "Fat", token: "fat", unit: "g" },
} as const

export const SCAN_RESULT: ScanResult = {
  name: "Grilled Salmon Bowl",
  confidence: 94,
  calories: 612,
  macros: { protein: 42, carbs: 48, fat: 26 },
  image: "/foods/salmon-bowl.png",
  predictions: [
    { name: "Grilled Salmon Bowl", confidence: 94 },
    { name: "Poke Bowl", confidence: 81 },
    { name: "Teriyaki Salmon", confidence: 63 },
    { name: "Rice & Fish Bowl", confidence: 47 },
    { name: "Buddha Bowl", confidence: 29 },
  ],
}

export const DAILY_GOAL = 2200

export const MEAL_BREAKDOWN: { meal: MealCategory; label: string; calories: number }[] = [
  { meal: "breakfast", label: "Breakfast", calories: 420 },
  { meal: "lunch", label: "Lunch", calories: 680 },
  { meal: "dinner", label: "Dinner", calories: 612 },
  { meal: "snacks", label: "Snacks", calories: 235 },
]

export const RECENT_SCANS: RecentScan[] = [
  {
    id: "1",
    name: "Grilled Salmon Bowl",
    calories: 612,
    time: "Today, 7:24 PM",
    image: "/foods/salmon-bowl.png",
    meal: "dinner",
  },
  {
    id: "2",
    name: "Greek Salad",
    calories: 320,
    time: "Today, 1:05 PM",
    image: "/foods/greek-salad.png",
    meal: "lunch",
  },
  {
    id: "3",
    name: "Avocado Toast",
    calories: 285,
    time: "Today, 8:12 AM",
    image: "/foods/avocado-toast.png",
    meal: "breakfast",
  },
  {
    id: "4",
    name: "Blueberry Oatmeal",
    calories: 240,
    time: "Yesterday, 8:40 AM",
    image: "/foods/oatmeal.png",
    meal: "breakfast",
  },
]

export function totalMacroGrams(macros: Macros) {
  return macros.protein + macros.carbs + macros.fat
}
