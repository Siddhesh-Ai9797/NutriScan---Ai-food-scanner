import {
  collection,
  addDoc,
  query,
  where,
  orderBy,
  getDocs,
  serverTimestamp,
  limit,
  type Timestamp,
} from "firebase/firestore"
import { db } from "./firebase"
import type { MealCategory } from "./nutriscan-data"

export type MealRecord = {
  id          : string
  userId      : string
  name        : string
  calories    : number
  protein     : number
  carbs       : number
  fat         : number
  meal        : MealCategory
  weightGrams : number | null
  serving     : string | null
  source      : string
  imageUrl    : string | null
  createdAt   : Timestamp
}

// ── Save a meal to Firestore ──────────────────────────────────────────────
export async function saveMeal(
  userId  : string,
  data    : Omit<MealRecord, "id" | "userId" | "createdAt">
): Promise<string> {
  const ref = await addDoc(collection(db, "meals"), {
    ...data,
    userId,
    createdAt: serverTimestamp(),
  })
  return ref.id
}

// ── Fetch today's meals for a user ────────────────────────────────────────
export async function fetchTodayMeals(userId: string): Promise<MealRecord[]> {
  const q = query(
    collection(db, "meals"),
    where("userId", "==", userId),
    limit(20)
  )

  const snapshot = await getDocs(q)
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  return snapshot.docs
    .map((doc) => ({ id: doc.id, ...doc.data() } as MealRecord))
    .filter((m) => m.createdAt?.toDate() >= today)
    .sort((a, b) => b.createdAt.toDate().getTime() - a.createdAt.toDate().getTime())
}

// ── Fetch all meals for a user (history) ─────────────────────────────────
export async function fetchAllMeals(userId: string): Promise<MealRecord[]> {
  const q = query(
    collection(db, "meals"),
    where("userId", "==", userId),
    orderBy("createdAt", "desc")
  )

  const snapshot = await getDocs(q)
  return snapshot.docs.map((doc) => ({
    id: doc.id,
    ...doc.data(),
  })) as MealRecord[]
}