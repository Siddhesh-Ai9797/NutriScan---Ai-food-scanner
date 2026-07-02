"use client"

import { Home, ScanLine, BarChart3, User } from "lucide-react"
import { cn } from "@/lib/utils"

export type Tab = "home" | "scan" | "stats" | "profile"

const TABS = [
  { id: "home", label: "Home", icon: Home },
  { id: "scan", label: "Scan", icon: ScanLine },
  { id: "stats", label: "Stats", icon: BarChart3 },
  { id: "profile", label: "Profile", icon: User },
] as const

export function BottomNav({
  active,
  onChange,
}: {
  active: Tab
  onChange: (tab: Tab) => void
}) {
  return (
    <nav
      aria-label="Primary"
      className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-card/95 backdrop-blur"
    >
      <ul className="mx-auto flex max-w-md items-center justify-around px-3 py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))]">
        {TABS.map((tab) => {
          const Icon = tab.icon
          const isActive = tab.id === active
          return (
            <li key={tab.id}>
              <button
                type="button"
                onClick={() => onChange(tab.id)}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Icon className="size-5" aria-hidden="true" />
                <span className={cn(!isActive && "sr-only")}>{tab.label}</span>
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
