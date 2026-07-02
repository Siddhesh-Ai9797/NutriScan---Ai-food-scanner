"use client"

import { ChevronRight, Plus, UtensilsCrossed } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useStore } from "@/lib/store"

const MEAL_LABEL: Record<string, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snacks: "Snack",
}

export function RecentScans() {
  const { loggedMeals } = useStore()

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
              <button
                type="button"
                className="flex w-full items-center gap-3 py-3 text-left transition-colors hover:opacity-80"
              >
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
                <ChevronRight
                  className="size-4 shrink-0 text-muted-foreground"
                  aria-hidden="true"
                />
              </button>
            </li>
          ))}
        </ul>
      )}

      <Button
        variant="outline"
        className="mt-4 h-11 w-full rounded-full border-primary text-sm font-semibold text-primary hover:bg-accent hover:text-primary"
        onClick={() => alert("Manual meal entry coming soon!")}
      >
        <Plus className="size-4" aria-hidden="true" />
        Add Meal Manually
      </Button>
    </div>
  )
}