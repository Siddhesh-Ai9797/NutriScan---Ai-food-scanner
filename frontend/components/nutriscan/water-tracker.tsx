"use client"

import { Droplets } from "lucide-react"
import { useStore } from "@/lib/store"

const QUICK_ADD = [150, 250, 350, 500]

export function WaterTracker({uid}: {uid: string}) {
  const { waterMl, addWater, profile } = useStore()
  const goal  = profile.waterGoal || 2500
  const pct   = Math.min(Math.round((waterMl / goal) * 100), 100)
  const cups  = Math.floor(waterMl / 250)

  return (
    <div className="rounded-3xl border border-border bg-card p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Droplets className="size-5 text-blue-500" />
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Water intake
          </h3>
        </div>
        <span className="text-xs text-muted-foreground">{cups} cups</span>
      </div>

      {/* Big number */}
      <div className="mb-4 flex items-baseline gap-1.5">
        <span className="text-3xl font-bold tabular-nums text-foreground">
          {waterMl >= 1000 ? `${(waterMl / 1000).toFixed(1)}L` : `${waterMl}ml`}
        </span>
        <span className="text-sm text-muted-foreground">/ {goal >= 1000 ? `${goal/1000}L` : `${goal}ml`}</span>
        <span className="ml-auto text-sm font-semibold text-blue-500">{pct}%</span>
      </div>

      {/* Progress bar */}
      <div className="mb-4 h-3 w-full overflow-hidden rounded-full bg-blue-100">
        <div
          className="h-full rounded-full bg-blue-500 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Wave visualization */}
      <div className="mb-4 flex justify-center gap-1">
        {Array.from({ length: 10 }, (_, i) => (
          <div
            key={i}
            className={`h-6 w-5 rounded-sm transition-colors ${
              i < Math.floor(pct / 10) ? "bg-blue-500" : "bg-blue-100"
            }`}
          />
        ))}
      </div>

      {/* Quick add buttons */}
      <div className="flex gap-2">
        {QUICK_ADD.map((ml) => (
          <button
            key={ml}
            onClick={() => addWater(ml, uid)}
            className="flex-1 rounded-full border border-blue-200 bg-blue-50 py-2 text-xs font-semibold text-blue-600 hover:bg-blue-100 transition-colors"
          >
            +{ml}ml
          </button>
        ))}
      </div>
    </div>
  )
}