"use client"

import { useStore } from "@/lib/store"

export function WeeklyChart() {
  const { weeklyData, profile } = useStore()
  const goal = profile.dailyGoal || 2200
  const max  = Math.max(...weeklyData.map((d) => d.calories), goal)

  if (weeklyData.length === 0) {
    return (
      <div className="rounded-3xl border border-border bg-card p-5">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Weekly calories
        </h3>
        <p className="text-center text-sm text-muted-foreground py-6">
          No data yet — start scanning meals to see your weekly chart
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-3xl border border-border bg-card p-5">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Weekly calories
        </h3>
        <span className="text-xs text-muted-foreground">Goal: {goal} kcal</span>
      </div>

      {/* Bar chart */}
      <div className="flex items-end gap-1.5 h-32">
        {weeklyData.map((day, i) => {
          const height  = day.calories > 0 ? Math.max((day.calories / max) * 100, 4) : 0
          const overGoal = day.calories > goal
          const isToday  = i === weeklyData.length - 1

          return (
            <div key={day.date} className="flex flex-1 flex-col items-center gap-1.5">
              {/* Calorie label */}
              {day.calories > 0 && (
                <span className="text-[9px] text-muted-foreground tabular-nums">
                  {day.calories > 999 ? `${(day.calories/1000).toFixed(1)}k` : day.calories}
                </span>
              )}
              {/* Bar */}
              <div className="flex w-full flex-1 items-end">
                <div
                  className={`w-full rounded-t-lg transition-all ${
                    isToday
                      ? "bg-primary"
                      : overGoal
                      ? "bg-red-400"
                      : "bg-primary/30"
                  }`}
                  style={{ height: `${height}%` }}
                />
              </div>
              {/* Day label */}
              <span className={`text-[10px] font-medium ${
                isToday ? "text-primary" : "text-muted-foreground"
              }`}>
                {isToday ? "Today" : day.date}
              </span>
            </div>
          )
        })}
      </div>

      {/* Goal line label */}
      <div className="mt-3 flex items-center gap-2">
        <div className="h-0.5 w-4 bg-primary/40 rounded" />
        <span className="text-xs text-muted-foreground">Daily goal</span>
        <div className="h-0.5 w-4 bg-red-400 rounded ml-2" />
        <span className="text-xs text-muted-foreground">Over goal</span>
      </div>
    </div>
  )
}