import {
  collection, query, where,
  getDocs, serverTimestamp, limit,
  doc, setDoc, getDoc, updateDoc, deleteDoc,
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

// ── New meal id (created locally so the UI and Firestore share one id) ────
export function newMealId(): string {
  return doc(collection(db, "meals")).id
}

// ── Save a meal ───────────────────────────────────────────────────────────
export async function saveMeal(
  userId: string,
  data  : Omit<MealRecord, "id" | "userId" | "createdAt">,
  id    : string = newMealId(),
): Promise<string> {
  await setDoc(doc(db, "meals", id), {
    ...data,
    userId,
    createdAt: serverTimestamp(),
  })
  return id
}

// ── Update a meal after the user corrects it ──────────────────────────────
export type MealCorrection = Pick<MealRecord, "name" | "calories" | "protein" | "carbs" | "fat"> & {
  source : string
  serving: string | null
}

export async function updateMeal(id: string, data: MealCorrection): Promise<void> {
  await updateDoc(doc(db, "meals", id), data)
}

// ── Delete a meal the user logged by mistake ──────────────────────────────
export async function deleteMeal(id: string): Promise<void> {
  await deleteDoc(doc(db, "meals", id))
}

// ── Fetch today's meals ───────────────────────────────────────────────────
export async function fetchTodayMeals(userId: string): Promise<MealRecord[]> {
  const q = query(
    collection(db, "meals"),
    where("userId", "==", userId),
    limit(500)
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
    limit(500)
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
  const today = new Date().toLocaleDateString("en-CA")// "2026-07-02"
  await setDoc(doc(db, "water", `${userId}_${today}`), { ml, userId, date: today }, { merge: true })
}

// ── Fetch today's water intake ────────────────────────────────────────────
export async function fetchWaterIntake(userId: string): Promise<number> {
  const today = new Date().toLocaleDateString("en-CA")
  const snap  = await getDoc(doc(db, "water", `${userId}_${today}`))
  if (!snap.exists()) return 0
  return snap.data().ml ?? 0
}