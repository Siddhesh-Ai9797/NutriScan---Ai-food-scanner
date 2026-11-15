"use client"

import { Activity } from "lucide-react"
import type { AdminMetrics, MetricsWindow } from "@/lib/admin"

const pct = (v: number | null) => (v === null ? "–" : `${v}%`)
const ms  = (v: number | null) => (v === null ? "–" : v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${Math.round(v)}ms`)
const usd = (v: number | null) => (v === null ? "–" : `$${v < 0.01 ? v.toFixed(4) : v.toFixed(2)}`)

const RULE_NAMES: Record<string, string> = {
  clip_not_food           : "Not food (CLIP)",
  llm_not_food            : "Not food (GPT-4o)",
  fast_disputed_classifier: "Mini model disputed EfficientNet",
  fast_said_not_food      : "Mini model unsure, escalated",
  totals_recomputed       : "Totals fixed",
  calories_below_macros   : "Calories fixed to match macros",
  impossible_density      : "Impossible item dropped",
  negative_value          : "Negative number fixed",
  plate_too_large         : "Plate over 6000 kcal rejected",
  llm_failed              : "Model call failed",
}

export function SystemHealth({ metrics }: { metrics: AdminMetrics }) {
  const day = metrics.window
  const all = metrics.all_time
  const rules = Object.entries(all.guardrails).sort((a, b) => b[1] - a[1])

  return (
    <div className="mb-6 rounded-3xl border border-border bg-card p-5">
      <div className="mb-3 flex items-center gap-2">
        <Activity className="size-5 text-primary" />
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          System health, last 24 hours
        </h2>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Tile label="Scans" value={day.scans} />
        <Tile label="p50 latency" value={ms(day.latency_ms.p50)} />
        <Tile label="p95 latency" value={ms(day.latency_ms.p95)} />
        <Tile label="Cache hits" value={pct(day.cache_hit_pct)} />
        <Tile label="Cheap model" value={pct(day.fast_path_pct)} />
        <Tile label="Blocked" value={pct(day.blocked_pct)} />
        <Tile label="Cost per scan" value={usd(day.avg_cost_per_scan)} />
        <Tile label="All AI cost" value={usd(day.total_llm_cost_usd)} />
        <Tile label="Errors" value={pct(day.error_pct)} />
      </div>

      <RouteBar window={day} />

      {rules.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-xs font-semibold text-muted-foreground">Guardrails since last deploy</p>
          <div className="flex flex-col gap-1">
            {rules.map(([rule, count]) => (
              <div key={rule} className="flex justify-between text-sm">
                <span>{RULE_NAMES[rule] ?? rule}</span>
                <span className="text-muted-foreground">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="mt-4 text-xs text-muted-foreground">
        Food check: {metrics.food_gate.ready ? "CLIP ready" : metrics.food_gate.failed ? "CLIP failed to load, GPT-4o check only" : "CLIP loading"}
        {" · "}Name cache hits: {pct(metrics.caches.name.hit_pct)}
        {" · "}{all.scans} scans since last deploy
      </p>
    </div>
  )
}

function Tile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl bg-muted/50 p-3 text-center">
      <p className="text-lg font-bold text-foreground">{value}</p>
      <p className="text-[11px] text-muted-foreground">{label}</p>
    </div>
  )
}

const ROUTE_COLOURS: Record<string, string> = {
  cache    : "bg-sky-400",
  fast     : "bg-green-500",
  full     : "bg-amber-500",
  escalated: "bg-orange-600",
  blocked  : "bg-red-500",
  failed   : "bg-zinc-400",
  rejected : "bg-zinc-300",
}

function RouteBar({ window }: { window: MetricsWindow }) {
  const total = Object.values(window.routes).reduce((a, b) => a + b, 0)
  if (!total) return null
  const entries = Object.entries(window.routes).sort((a, b) => b[1] - a[1])
  return (
    <div className="mt-4">
      <div className="flex h-2 w-full overflow-hidden rounded-full">
        {entries.map(([route, n]) => (
          <div key={route} className={ROUTE_COLOURS[route] ?? "bg-zinc-500"} style={{ width: `${(n / total) * 100}%` }} />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
        {entries.map(([route, n]) => (
          <span key={route} className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <span className={`inline-block size-2 rounded-full ${ROUTE_COLOURS[route] ?? "bg-zinc-500"}`} />
            {route} {n}
          </span>
        ))}
      </div>
    </div>
  )
}
