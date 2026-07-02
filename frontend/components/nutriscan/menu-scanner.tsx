"use client"

import { useState, useRef } from "react"
import { UtensilsCrossed, Loader2, Upload, CheckCircle, XCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useStore } from "@/lib/store"
import { scanMenu, type MenuScanResult } from "@/lib/api"

export function MenuScanner() {
  const { totalCalories, totalProtein, profile } = useStore()
  const [result,  setResult]  = useState<MenuScanResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  async function handleFile(file: File) {
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const data = await scanMenu(
        file,
        totalCalories,
        profile.dailyGoal,
        totalProtein,
        profile.proteinGoal,
      )
      setResult(data)
    } catch {
      setError("Could not scan menu. Try a clearer photo with readable text.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-3xl border border-border bg-card p-5">
      <div className="mb-4 flex items-center gap-2">
        <UtensilsCrossed className="size-5 text-primary" />
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Menu scanner
        </h3>
      </div>

      <p className="mb-4 text-sm text-muted-foreground">
        Take a photo of any restaurant menu → get personalized dish recommendations based on your remaining {profile.dailyGoal - totalCalories} kcal today.
      </p>

      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) handleFile(file)
          e.target.value = ""
        }}
      />

      {!result && !loading && (
        <Button
          onClick={() => fileRef.current?.click()}
          className="h-11 w-full rounded-full text-sm font-semibold"
        >
          <Upload className="size-4" />
          Upload menu photo
        </Button>
      )}

      {loading && (
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <Loader2 className="size-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Analyzing menu…</p>
        </div>
      )}

      {error && (
        <div className="rounded-2xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {result && (
        <div className="flex flex-col gap-4">
          {/* Summary */}
          <p className="text-sm text-muted-foreground">{result.summary}</p>

          {/* Remaining */}
          <div className="rounded-2xl bg-accent px-4 py-3 text-sm">
            <span className="font-semibold text-foreground">{result.remaining_calories} kcal</span>
            <span className="text-muted-foreground"> remaining today</span>
          </div>

          {/* Recommendations */}
          {result.recommendations.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Best choices for you
              </p>
              <div className="flex flex-col gap-2">
                {result.recommendations.map((dish, i) => (
                  <div key={i} className="rounded-2xl border border-green-200 bg-green-50 p-3">
                    <div className="flex items-start gap-2">
                      <CheckCircle className="size-4 shrink-0 text-green-600 mt-0.5" />
                      <div>
                        <p className="text-sm font-semibold text-foreground">{dish.name}</p>
                        <p className="text-xs text-muted-foreground">
                          ~{dish.estimated_calories} kcal · {dish.protein}g protein
                        </p>
                        <p className="mt-1 text-xs text-green-700">{dish.reason}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Avoid */}
          {result.avoid.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Dishes to avoid
              </p>
              <div className="flex flex-col gap-2">
                {result.avoid.map((dish, i) => (
                  <div key={i} className="flex items-start gap-2 rounded-2xl border border-red-200 bg-red-50 p-3">
                    <XCircle className="size-4 shrink-0 text-red-500 mt-0.5" />
                    <p className="text-xs text-red-700">{dish}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <Button
            variant="outline"
            onClick={() => { setResult(null); setError(null) }}
            className="h-10 w-full rounded-full text-sm"
          >
            Scan another menu
          </Button>
        </div>
      )}
    </div>
  )
}