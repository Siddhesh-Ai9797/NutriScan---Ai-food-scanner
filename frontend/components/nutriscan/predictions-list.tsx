import type { Prediction } from "@/lib/nutriscan-data"

export function PredictionsList({ predictions }: { predictions: Prediction[] }) {
  return (
    <ul className="flex flex-col gap-3">
      {predictions.map((p, i) => (
        <li key={p.name} className="flex items-center gap-3">
          <span className="w-4 text-sm font-semibold tabular-nums text-muted-foreground">
            {i + 1}
          </span>
          <div className="flex-1">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-foreground">
                {p.name}
              </span>
              <span className="text-sm font-semibold tabular-nums text-muted-foreground">
                {p.confidence}%
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${p.confidence}%` }}
              />
            </div>
          </div>
        </li>
      ))}
    </ul>
  )
}
