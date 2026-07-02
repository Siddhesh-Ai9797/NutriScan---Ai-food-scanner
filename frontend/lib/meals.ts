import {
  collection, addDoc, query, where,
  getDocs, serverTimestamp, limit,
  doc, setDoc, getDoc,
  type Timestamp,
} from "firebase/firestore"
import { db } from "./firebase"
import type { MealCategory } from "./nutriscan-data"
import type { UserProfile } from "./store"

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

// ── Save a meal ───────────────────────────────────────────────────────────
export async function saveMeal(
  userId: string,
  data  : Omit<MealRecord, "id" | "userId" | "createdAt">
): Promise<string> {
  const ref = await addDoc(collection(db, "meals"), {
    ...data,
    userId,
    createdAt: serverTimestamp(),
  })
  return ref.id
}

// ── Fetch today's meals ───────────────────────────────────────────────────
export async function fetchTodayMeals(userId: string): Promise<MealRecord[]> {
  const q = query(
    collection(db, "meals"),
    where("userId", "==", userId),
    limit(20)
  )
  const snapshot = await getDocs(q)
  const today    = new Date()
  today.setHours(0, 0, 0, 0)

  return snapshot.docs
    .map((doc) => ({ id: doc.id, ...doc.data() } as MealRecord))
    .filter((m) => m.createdAt?.toDate() >= today)
    .sort((a, b) => b.createdAt.toDate().getTime() - a.createdAt.toDate().getTime())
}

// ── Fetch last 7 days meals (for weekly chart) ────────────────────────────
export async function fetchWeeklyMeals(userId: string): Promise<MealRecord[]> {
  const q = query(
    collection(db, "meals"),
    where("userId", "==", userId),
    limit(100)
  )
  const snapshot = await getDocs(q)
  const weekAgo  = new Date()
  weekAgo.setDate(weekAgo.getDate() - 7)

  return snapshot.docs
    .map((doc) => ({ id: doc.id, ...doc.data() } as MealRecord))
    .filter((m) => m.createdAt?.toDate() >= weekAgo)
    .sort((a, b) => a.createdAt.toDate().getTime() - b.createdAt.toDate().getTime())
}

// ── Fetch all meals for a user (history) ─────────────────────────────────
export async function fetchAllMeals(userId: string): Promise<MealRecord[]> {
  const q = query(
    collection(db, "meals"),
    where("userId", "==", userId),
    limit(50)
  )
  const snapshot = await getDocs(q)
  return snapshot.docs
    .map((doc) => ({ id: doc.id, ...doc.data() } as MealRecord))
    .sort((a, b) => b.createdAt.toDate().getTime() - a.createdAt.toDate().getTime())
}

// ── Save user profile ─────────────────────────────────────────────────────
export async function saveUserProfile(uid: string, profile: UserProfile): Promise<void> {
  await setDoc(doc(db, "users", uid), profile, { merge: true })
}

// ── Fetch user profile ────────────────────────────────────────────────────
export async function fetchUserProfile(uid: string): Promise<Partial<UserProfile> | null> {
  const snap = await getDoc(doc(db, "users", uid))
  if (!snap.exists()) return null
  return snap.data() as Partial<UserProfile>
}

// ── Save water intake ─────────────────────────────────────────────────────
export async function saveWaterIntake(userId: string, ml: number): Promise<void> {
  const today = new Date().toISOString().split("T")[0] // "2026-07-02"
  await setDoc(doc(db, "water", `${userId}_${today}`), { ml, userId, date: today }, { merge: true })
}

// ── Fetch today's water intake ────────────────────────────────────────────
export async function fetchWaterIntake(userId: string): Promise<number> {
  const today = new Date().toISOString().split("T")[0]
  const snap  = await getDoc(doc(db, "water", `${userId}_${today}`))
  if (!snap.exists()) return 0
  return snap.data().ml ?? 0
}