"use client"

import { useStore } from "@/lib/store"

export function CalorieTracker() {
  const { totalCalories, totalProtein, profile, mealBreakdown } = useStore()
  const { dailyGoal, proteinGoal } = profile

  const remaining    = Math.max(dailyGoal - totalCalories, 0)
  const calPct       = Math.min(Math.round((totalCalories / dailyGoal) * 100), 100)
  const proteinPct   = Math.min(Math.round((totalProtein / proteinGoal) * 100), 100)

  return (
    <div className="rounded-3xl border border-border bg-card p-5">
      <div className="flex items-end justify-between">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Daily calories
          </h3>
          <p className="mt-1 flex items-baseline gap-1.5">
            <span className="text-3xl font-bold tabular-nums text-foreground">
              {totalCalories}
            </span>
            <span className="text-sm font-medium text-muted-foreground">
              / {dailyGoal} kcal
            </span>
          </p>
        </div>
        <div className="text-right">
          <span className="text-sm font-semibold tabular-nums text-primary">{remaining}</span>
          <p className="text-xs font-medium text-muted-foreground">left</p>
        </div>
      </div>

      {/* Calorie bar */}
      <div className="mt-4 h-2.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${calPct}%` }}
        />
      </div>

      {/* Protein bar */}
      <div className="mt-3">
        <div className="mb-1 flex justify-between text-xs text-muted-foreground">
          <span>Protein</span>
          <span>{Math.round(totalProtein)}g / {proteinGoal}g</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-blue-500 transition-all"
            style={{ width: `${proteinPct}%` }}
          />
        </div>
      </div>

      {/* Meal breakdown */}
      <div className="mt-4 grid grid-cols-2 gap-2.5">
        {mealBreakdown.map((m) => (
          <div
            key={m.meal}
            className="flex items-center justify-between rounded-full border border-border bg-secondary px-3.5 py-2"
          >
            <span className="text-sm font-medium text-secondary-foreground">{m.label}</span>
            <span className="text-sm font-semibold tabular-nums text-muted-foreground">
              {m.calories || "—"}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}