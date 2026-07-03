import { collection, getDocs, query, orderBy, limit, where } from "firebase/firestore"
import { db } from "./firebase"

export type AdminMeal = {
  id        : string
  userId    : string
  name      : string
  calories  : number
  protein   : number
  carbs     : number
  fat       : number
  meal      : string
  source    : string
  imageUrl  : string | null
  createdAt : any
}

export type AdminStats = {
  totalMeals      : number
  mealsToday      : number
  totalUsers      : number
  avgCalories     : number
  topFoods        : { name: string; count: number }[]
  recentUploads   : AdminMeal[]
  sourceBreakdown : { efficientnet: number; gpt4o: number; unknown: number }
}

// ── Fetch all meals for admin ─────────────────────────────────────────────
export async function fetchAdminStats(): Promise<AdminStats> {
  // Fetch last 200 meals
  const q        = query(collection(db, "meals"), orderBy("createdAt", "desc"), limit(200))
  const snapshot = await getDocs(q)
  const meals    = snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() } as AdminMeal))

  // Today's meals
  const today    = new Date()
  today.setHours(0, 0, 0, 0)
  const mealsToday = meals.filter((m) => m.createdAt?.toDate() >= today)

  // Total unique users
  const uniqueUsers = new Set(meals.map((m) => m.userId)).size

  // Average calories
  const avgCalories = meals.length > 0
    ? Math.round(meals.reduce((sum, m) => sum + m.calories, 0) / meals.length)
    : 0

  // Top foods
  const foodCount: Record<string, number> = {}
  meals.forEach((m) => {
    if (m.name) foodCount[m.name] = (foodCount[m.name] || 0) + 1
  })
  const topFoods = Object.entries(foodCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([name, count]) => ({ name, count }))

  // Source breakdown
  const sourceBreakdown = {
    efficientnet: meals.filter((m) => m.source === "efficientnet").length,
    gpt4o       : meals.filter((m) => m.source === "gpt4o").length,
    unknown     : meals.filter((m) => m.source === "unknown").length,
  }

  // Recent uploads with photos
  const recentUploads = meals.filter((m) => m.imageUrl).slice(0, 20)

  return {
    totalMeals  : meals.length,
    mealsToday  : mealsToday.length,
    totalUsers  : uniqueUsers,
    avgCalories,
    topFoods,
    recentUploads,
    sourceBreakdown,
  }
}