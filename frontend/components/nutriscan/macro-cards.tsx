import { MACRO_CALORIES, type Macros } from "@/lib/nutriscan-data"

const CARDS = [
  { key: "protein", label: "Protein", bar: "bg-protein" },
  { key: "carbs", label: "Carbs", bar: "bg-carbs" },
  { key: "fat", label: "Fat", bar: "bg-fat" },
] as const

export function MacroCards({ macros }: { macros: Macros }) {
  const cals = {
    protein: macros.protein * MACRO_CALORIES.protein,
    carbs: macros.carbs * MACRO_CALORIES.carbs,
    fat: macros.fat * MACRO_CALORIES.fat,
  }
  const total = cals.protein + cals.carbs + cals.fat || 1

  return (
    <div className="grid grid-cols-3 gap-3">
      {CARDS.map((card) => {
        const grams = macros[card.key]
        const pct = Math.round((cals[card.key] / total) * 100)
        return (
          <div
            key={card.key}
            className="flex flex-col gap-2 rounded-2xl border border-border bg-card p-3"
          >
            <span className="text-xs font-medium text-muted-foreground">
              {card.label}
            </span>
            <span className="text-lg font-bold tabular-nums text-foreground">
              {grams}
              <span className="text-sm font-medium text-muted-foreground">g</span>
            </span>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full rounded-full ${card.bar}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}
