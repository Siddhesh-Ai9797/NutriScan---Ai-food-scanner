"use client"

import { Flame } from "lucide-react"
import { useStore } from "@/lib/store"

export function StreakBadge() {
  const { streak } = useStore()

  if (streak === 0) return null

  return (
    <div className="flex items-center gap-1.5 rounded-full bg-orange-50 border border-orange-200 px-3 py-1">
      <Flame className="size-3.5 text-orange-500" />
      <span className="text-xs font-semibold text-orange-600">{streak} day streak</span>
    </div>
  )
}