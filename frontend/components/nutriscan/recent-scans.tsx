"use client"

import { useState } from "react"
import { Loader2, Plus, Trash2, UtensilsCrossed } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useStore } from "@/lib/store"
import { useAuth } from "@/lib/auth"
import { deleteMeal } from "@/lib/meals"
import { ManualMealForm } from "./manual-meal-form"

const MEAL_LABEL: Record<string, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snacks: "Snack",
}

export function RecentScans() {
  const { loggedMeals, removeMeal, loadWeekly } = useStore()
  const { user } = useAuth()
  const [adding, setAdding]         = useState(false)
  const [confirmId, setConfirmId]   = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [error, setError]           = useState<string | null>(null)

  async function handleDelete(id: string) {
    if (confirmId !== id) { setConfirmId(id); return }
    setDeletingId(id)
    setError(null)
    try {
      await deleteMeal(id)
      removeMeal(id)
      if (user) loadWeekly(user.uid)
    } catch {
      setError("Couldn't delete that meal. Please try again.")
    } finally {
      setDeletingId(null)
      setConfirmId(null)
    }
  }

  return (
    <div className="rounded-3xl border border-border bg-card p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Recent scans
        </h3>
      </div>

      {loggedMeals.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-8 text-center">
          <UtensilsCrossed className="size-8 text-muted-foreground" aria-hidden="true" />
          <p className="text-sm font-medium text-foreground">No meals logged yet</p>
          <p className="text-xs text-muted-foreground">
            Scan a food photo to start tracking
          </p>
        </div>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {loggedMeals.map((scan) => (
            <li key={scan.id}>
              <div className="flex w-full items-center gap-3 py-3 text-left">
                <span className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-accent text-2xl">
                  {scan.image && scan.image.startsWith("blob:")
                    ? "🍽️"
                    : "🍽️"}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-foreground">
                    {scan.name}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {MEAL_LABEL[scan.meal]} · {scan.time}
                  </p>
                </div>
                <span className="text-sm font-semibold tabular-nums text-foreground">
                  {scan.calories}
                  <span className="ml-0.5 text-xs font-medium text-muted-foreground">
                    kcal
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => handleDelete(scan.id)}
                  onBlur={() => setConfirmId((c) => (c === scan.id ? null : c))}
                  disabled={deletingId === scan.id}
                  aria-label={`Delete ${scan.name}`}
                  className={`flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-xs font-medium transition-colors ${
                    confirmId === scan.id
                      ? "bg-destructive/10 text-destructive"
                      : "text-muted-foreground hover:text-destructive"
                  }`}
                >
                  {deletingId === scan.id
                    ? <Loader2 className="size-4 animate-spin" />
                    : confirmId === scan.id
                      ? "Delete?"
                      : <Trash2 className="size-4" aria-hidden="true" />}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}

      {adding && user ? (
        <ManualMealForm uid={user.uid} onClose={() => setAdding(false)} />
      ) : (
        <Button
          variant="outline"
          className="mt-4 h-11 w-full rounded-full border-primary text-sm font-semibold text-primary hover:bg-accent hover:text-primary"
          onClick={() => setAdding(true)}
        >
          <Plus className="size-4" aria-hidden="true" />
          Add Meal Manually
        </Button>
      )}
    </div>
  )
}