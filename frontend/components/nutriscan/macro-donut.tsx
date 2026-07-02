import { MACRO_CALORIES, type Macros } from "@/lib/nutriscan-data"

const SEGMENTS = [
  { key: "protein", label: "Protein", color: "var(--protein)" },
  { key: "carbs",   label: "Carbs",   color: "var(--carbs)"   },
  { key: "fat",     label: "Fat",     color: "var(--fat)"     },
] as const

export function MacroDonut({
  macros,
  calories,
}: {
  macros: Macros
  calories?: number   // actual calories from API — use this if provided
}) {
  const cals = {
    protein: macros.protein * MACRO_CALORIES.protein,
    carbs:   macros.carbs   * MACRO_CALORIES.carbs,
    fat:     macros.fat     * MACRO_CALORIES.fat,
  }

  // Use macro-derived total only for percentage splits
  const macroTotal = cals.protein + cals.carbs + cals.fat || 1

  // Display the actual API calorie value if provided
  const displayTotal = calories ?? Math.round(macroTotal)

  const radius       = 60
  const stroke       = 20
  const circumference = 2 * Math.PI * radius
  const gap          = 6

  let offset = 0
  const arcs = SEGMENTS.map((seg) => {
    const value    = cals[seg.key]
    const fraction = value / macroTotal
    const length   = Math.max(fraction * circumference - gap, 0)
    const arc = {
      color:      seg.color,
      dasharray:  `${length} ${circumference - length}`,
      dashoffset: -offset,
    }
    offset += fraction * circumference
    return arc
  })

  return (
    <div className="flex items-center gap-6">
      <div className="relative shrink-0">
        <svg
          width="160"
          height="160"
          viewBox="0 0 160 160"
          className="-rotate-90"
          role="img"
          aria-label="Macro breakdown donut chart"
        >
          <circle
            cx="80" cy="80" r={radius}
            fill="none" stroke="var(--muted)" strokeWidth={stroke}
          />
          {arcs.map((arc, i) => (
            <circle
              key={i}
              cx="80" cy="80" r={radius}
              fill="none"
              stroke={arc.color}
              strokeWidth={stroke}
              strokeDasharray={arc.dasharray}
              strokeDashoffset={arc.dashoffset}
              strokeLinecap="round"
            />
          ))}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold tabular-nums text-foreground">
            {displayTotal}
          </span>
          <span className="text-xs font-medium text-muted-foreground">kcal</span>
        </div>
      </div>

      <ul className="flex flex-col gap-3">
        {SEGMENTS.map((seg) => {
          const pct = Math.round((cals[seg.key] / macroTotal) * 100)
          return (
            <li key={seg.key} className="flex items-center gap-2.5">
              <span
                className="size-3 shrink-0 rounded-full"
                style={{ backgroundColor: seg.color }}
                aria-hidden="true"
              />
              <span className="text-sm font-medium text-foreground">
                {seg.label}
              </span>
              <span className="text-sm font-semibold tabular-nums text-muted-foreground">
                {pct}%
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}