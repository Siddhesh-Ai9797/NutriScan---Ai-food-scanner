import Image from "next/image"
import { BadgeCheck, Flame } from "lucide-react"
import type { ScanResult } from "@/lib/nutriscan-data"
import { MacroCards } from "./macro-cards"
import { MacroDonut } from "./macro-donut"
import { PredictionsList } from "./predictions-list"

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </h3>
  )
}

export function ResultCard({ result }: { result: ScanResult }) {
  return (
    <div className="flex flex-col gap-4">
      {/* Header card */}
      <div className="overflow-hidden rounded-3xl border border-border bg-card">
        <div className="relative aspect-[16/10] w-full">
          <Image
            src={result.image || "/placeholder.svg"}
            alt={result.name}
            fill
            sizes="(max-width: 768px) 100vw, 480px"
            className="object-cover"
            priority
          />
          <span className="absolute left-3 top-3 inline-flex items-center gap-1 rounded-full bg-success px-2.5 py-1 text-xs font-semibold text-primary-foreground">
            <BadgeCheck className="size-3.5" aria-hidden="true" />
            {result.confidence}% match
          </span>
        </div>

        <div className="p-5">
          <p className="text-xs font-medium text-muted-foreground">
            Identified food
          </p>
          <h2 className="mt-0.5 text-xl font-bold text-foreground text-balance">
            {result.name}
          </h2>

          <div className="mt-4 flex items-center gap-3 rounded-2xl bg-accent p-4">
            <span className="flex size-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <Flame className="size-5" aria-hidden="true" />
            </span>
            <div className="flex items-baseline gap-1.5">
              <span className="text-4xl font-bold tabular-nums leading-none text-foreground">
                {result.calories}
              </span>
              <span className="text-sm font-medium text-muted-foreground">
                kcal
              </span>
            </div>
          </div>

          <div className="mt-4">
            <MacroCards macros={result.macros} />
          </div>
        </div>
      </div>

      {/* Macro breakdown */}
      <div className="rounded-3xl border border-border bg-card p-5">
        <SectionLabel>Macro breakdown</SectionLabel>
        <MacroDonut macros={result.macros} calories={result.calories} />
      </div>

      {/* Top predictions */}
      <div className="rounded-3xl border border-border bg-card p-5">
        <SectionLabel>Top 5 predictions</SectionLabel>
        <PredictionsList predictions={result.predictions} />
      </div>
    </div>
  )
}
