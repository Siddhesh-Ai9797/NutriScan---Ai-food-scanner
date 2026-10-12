"use client"

import { useState } from "react"
import { Loader2, Search, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { apiFetch, apiErrorMessage } from "@/lib/api"
import { newMealId, saveMeal } from "@/lib/meals"
import { getCurrentMeal, useStore } from "@/lib/store"
import type { MealCategory, ScanResult } from "@/lib/nutriscan-data"

const MEALS: { value: MealCategory; label: string }[] = [
  { value: "breakfast", label: "Breakfast" },
  { value: "lunch",     label: "Lunch" },
  { value: "dinner",    label: "Dinner" },
  { value: "snacks",    label: "Snack" },
]

type Found = { name: string; calories: number; protein: number; carbs: number; fat: number; serving: string }

export function ManualMealForm({ uid, onClose }: { uid: string; onClose: () => void }) {
  const { logMeal, loadWeekly } = useStore()
  const [name, setName]       = useState("")
  const [grams, setGrams]     = useState("250")
  const [meal, setMeal]       = useState<MealCategory>(getCurrentMeal())
  const [found, setFound]     = useState<Found | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving]   = useState(false)
  const [error, setError]     = useState<string | null>(null)

  const gramsNum   = Number(grams)
  const gramsValid = Number.isFinite(gramsNum) && gramsNum >= 1 && gramsNum <= 3000

  async function lookUp() {
    if (!name.trim() || !gramsValid) return
    setLoading(true)
    setError(null)
    setFound(null)
    try {
      const params = new URLSearchParams({ food: name.trim(), grams: String(gramsNum) })
      const res = await apiFetch(`/nutrition?${params}`)
      if (!res.ok) throw new Error(await apiErrorMessage(res))
      const data = await res.json()
      setFound({
        name    : name.trim(),
        calories: data.calories,
        protein : data.protein,
        carbs   : data.carbs,
        fat     : data.fat,
        serving : data.serving ?? `${gramsNum}g`,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't look up that food.")
    } finally {
      setLoading(false)
    }
  }

  async function addToLog() {
    if (!found) return
    setSaving(true)
    setError(null)
    const id = newMealId()
    const result: ScanResult = {
      name       : found.name,
      confidence : 0,
      calories   : found.calories,
      macros     : { protein: found.protein, carbs: found.carbs, fat: found.fat },
      image      : "",
      predictions: [],
      weightGrams: gramsNum,
      serving    : found.serving,
      source     : "manual",
    }
    try {
      await saveMeal(uid, {
        name       : found.name,
        calories   : found.calories,
        protein    : found.protein,
        carbs      : found.carbs,
        fat        : found.fat,
        meal,
        weightGrams: gramsNum,
        serving    : found.serving,
        source     : "manual",
        imageUrl   : null,
      }, id)
      logMeal(result, meal, id)
      loadWeekly(uid)
      onClose()
    } catch {
      setError("Couldn't save this meal. Please try again.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mt-4 flex flex-col gap-3 rounded-2xl border border-border bg-accent p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-foreground">Add a meal</p>
        <button onClick={onClose} aria-label="Close" className="text-muted-foreground hover:text-foreground">
          <X className="size-4" />
        </button>
      </div>

      <input
        type="text"
        value={name}
        onChange={(e) => { setName(e.target.value); setFound(null) }}
        onKeyDown={(e) => e.key === "Enter" && lookUp()}
        placeholder="e.g. 2 rotis with dal, chicken salad"
        maxLength={120}
        autoFocus
        className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary"
      />

      <div className="flex gap-2">
        <div className="flex-1">
          <label className="mb-1 block text-xs text-muted-foreground">Portion (grams)</label>
          <input
            type="number"
            min={1}
            max={3000}
            value={grams}
            onChange={(e) => { setGrams(e.target.value); setFound(null) }}
            className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary"
          />
        </div>
        <div className="flex-1">
          <label className="mb-1 block text-xs text-muted-foreground">Meal</label>
          <select
            value={meal}
            onChange={(e) => setMeal(e.target.value as MealCategory)}
            className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary"
          >
            {MEALS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </div>
      </div>
      {!gramsValid && <p className="text-xs text-destructive">Portion must be between 1 and 3000 grams.</p>}

      {!found ? (
        <Button
          onClick={lookUp}
          disabled={!name.trim() || !gramsValid || loading}
          className="h-10 w-full rounded-full text-sm font-semibold"
        >
          {loading ? <Loader2 className="size-4 animate-spin" /> : <><Search className="size-4" /> Look up nutrition</>}
        </Button>
      ) : (
        <>
          <div className="rounded-xl border border-border bg-background px-4 py-3 text-sm">
            <p className="font-semibold capitalize text-foreground">{found.name}</p>
            <p className="text-muted-foreground">
              {found.calories} kcal · P {found.protein}g · C {found.carbs}g · F {found.fat}g · {found.serving}
            </p>
          </div>
          <Button onClick={addToLog} disabled={saving} className="h-10 w-full rounded-full text-sm font-semibold">
            {saving ? <Loader2 className="size-4 animate-spin" /> : "Add to log"}
          </Button>
        </>
      )}

      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}
