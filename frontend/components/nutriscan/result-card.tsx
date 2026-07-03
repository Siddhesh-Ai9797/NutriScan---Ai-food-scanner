"use client"

import { useState } from "react"
import Image from "next/image"
import { Flame, Check, Pencil, Loader2, ChevronDown, ChevronUp } from "lucide-react"
import type { ScanResult } from "@/lib/nutriscan-data"
import { MacroCards } from "./macro-cards"
import { MacroDonut } from "./macro-donut"
import { PredictionsList } from "./predictions-list"
import { Button } from "@/components/ui/button"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

type ConfirmState = "confirming" | "editing" | "loading" | "confirmed"

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </h3>
  )
}

export function ResultCard({ result }: { result: ScanResult }) {
  const [confirmState, setConfirmState]   = useState<ConfirmState>("confirming")
  const [editedName, setEditedName]       = useState("")
  const [currentResult, setCurrentResult] = useState<ScanResult>(result)
  const [error, setError]                 = useState<string | null>(null)
  const [showItems, setShowItems]         = useState(false)

  const items     = (result as any).items ?? []
  const multiItem = (result as any).multi_item ?? false

  // ── User confirms food name ───────────────────────────────────────────
  async function handleConfirm() {
    setConfirmState("confirmed")
    try {
      await fetch(`${API_URL}/label`, {
        method : "POST",
        headers: { "Content-Type": "application/json" },
        body   : JSON.stringify({
          food_name : currentResult.name,
          image_url : (result as any).imageUrl ?? null,
          source    : result.source ?? "efficientnet",
          calories  : currentResult.calories,
          protein   : currentResult.macros.protein,
          carbs     : currentResult.macros.carbs,
          fat       : currentResult.macros.fat,
          confirmed : true,
        }),
      })
    } catch { /* silent */ }
  }

  // ── User edits food name ──────────────────────────────────────────────
  async function handleEdit() {
    if (!editedName.trim()) return
    setConfirmState("loading")
    setError(null)

    try {
      const res = await fetch(
        `${API_URL}/nutrition?food=${encodeURIComponent(editedName.trim())}`
      )
      if (!res.ok) throw new Error("Not found")
      const data = await res.json()

      const updated: ScanResult = {
        ...currentResult,
        name    : editedName.trim(),
        calories: data.calories ?? currentResult.calories,
        macros  : {
          protein: data.protein ?? currentResult.macros.protein,
          carbs  : data.carbs   ?? currentResult.macros.carbs,
          fat    : data.fat     ?? currentResult.macros.fat,
        },
      }
      setCurrentResult(updated)
      setConfirmState("confirmed")

      try {
        await fetch(`${API_URL}/label`, {
          method : "POST",
          headers: { "Content-Type": "application/json" },
          body   : JSON.stringify({
            food_name : editedName.trim(),
            image_url : (result as any).imageUrl ?? null,
            source    : "user_correction",
            calories  : data.calories,
            protein   : data.protein,
            carbs     : data.carbs,
            fat       : data.fat,
            confirmed : true,
          }),
        })
      } catch { /* silent */ }

    } catch {
      setError("Couldn't find nutrition for this food. Try a different name.")
      setConfirmState("editing")
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-hidden rounded-3xl border border-border bg-card">
        <div className="relative aspect-[16/10] w-full">
          <Image
            src={currentResult.image || "/placeholder.svg"}
            alt={currentResult.name}
            fill
            sizes="(max-width: 768px) 100vw, 480px"
            className="object-cover"
            priority
          />
          {currentResult.confidence && (
            <span className="absolute left-3 top-3 inline-flex items-center gap-1 rounded-full bg-success px-2.5 py-1 text-xs font-semibold text-primary-foreground">
              <Check className="size-3.5" />
              {currentResult.confidence}% match
            </span>
          )}
          {multiItem && (
            <span className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-primary px-2.5 py-1 text-xs font-semibold text-primary-foreground">
              {items.length} items detected
            </span>
          )}
        </div>

        <div className="p-5">
          <p className="text-xs font-medium text-muted-foreground">Identified food</p>

          {/* Food name + edit */}
          {confirmState === "editing" || confirmState === "loading" ? (
            <div className="mt-1 flex flex-col gap-2">
              <input
                type="text"
                value={editedName}
                onChange={(e) => setEditedName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleEdit()}
                placeholder="e.g. Pomplet Fry, Biryani, Tacos..."
                autoFocus
                className="h-10 w-full rounded-xl border border-primary bg-background px-3 text-sm outline-none"
              />
              {error && <p className="text-xs text-destructive">{error}</p>}
              <div className="flex gap-2">
                <Button
                  onClick={handleEdit}
                  disabled={!editedName.trim() || confirmState === "loading"}
                  className="h-9 flex-1 rounded-full text-xs font-semibold"
                >
                  {confirmState === "loading"
                    ? <Loader2 className="size-3.5 animate-spin" />
                    : <><Check className="size-3.5" /> Get nutrition</>
                  }
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setConfirmState("confirming")}
                  disabled={confirmState === "loading"}
                  className="h-9 rounded-full px-3"
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className="mt-0.5 flex items-center justify-between">
              <h2 className="text-xl font-bold text-foreground">
                {currentResult.name}
                {multiItem && (
                  <span className="ml-2 text-sm font-normal text-muted-foreground">
                    + {items.length - 1} more
                  </span>
                )}
              </h2>
              {confirmState !== "confirmed" && (
                <button
                  onClick={() => { setEditedName(currentResult.name); setConfirmState("editing") }}
                  className="flex items-center gap-1 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent"
                >
                  <Pencil className="size-3" /> Edit
                </button>
              )}
            </div>
          )}

          {/* Confirmation buttons */}
          {confirmState === "confirming" && (
            <div className="mt-4 rounded-2xl border border-border bg-accent p-4">
              <p className="mb-3 text-sm font-medium text-foreground">
                Is this correct?
              </p>
              <div className="flex gap-2">
                <Button onClick={handleConfirm} className="h-10 flex-1 rounded-full text-sm font-semibold">
                  <Check className="size-4" /> Correct
                </Button>
                <Button
                  variant="outline"
                  onClick={() => { setEditedName(currentResult.name); setConfirmState("editing") }}
                  className="h-10 flex-1 rounded-full text-sm font-semibold"
                >
                  <Pencil className="size-4" /> Edit
                </Button>
              </div>
            </div>
          )}

          {/* Multiple items breakdown */}
          {multiItem && items.length > 0 && (
            <div className="mt-4">
              <button
                onClick={() => setShowItems(!showItems)}
                className="flex w-full items-center justify-between rounded-xl border border-border px-4 py-2.5 text-sm font-medium text-foreground"
              >
                <span>View all {items.length} detected items</span>
                {showItems ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
              </button>

              {showItems && (
                <div className="mt-2 flex flex-col gap-2">
                  {items.map((item: any, i: number) => (
                    <div key={i} className="flex items-center justify-between rounded-xl border border-border bg-secondary px-4 py-2.5">
                      <div>
                        <p className="text-sm font-medium text-foreground capitalize">{item.food}</p>
                        <p className="text-xs text-muted-foreground">
                          P:{item.protein}g · C:{item.carbs}g · F:{item.fat}g
                          {item.weight_grams ? ` · ${item.weight_grams}g` : ""}
                        </p>
                      </div>
                      <span className="text-sm font-semibold text-foreground">
                        {item.calories} kcal
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Total calories */}
          <div className="mt-4 flex items-center gap-3 rounded-2xl bg-accent p-4">
            <span className="flex size-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <Flame className="size-5" aria-hidden="true" />
            </span>
            <div>
              <div className="flex items-baseline gap-1.5">
                <span className="text-4xl font-bold tabular-nums leading-none text-foreground">
                  {currentResult.calories}
                </span>
                <span className="text-sm font-medium text-muted-foreground">kcal</span>
              </div>
              {multiItem && (
                <p className="text-xs text-muted-foreground">total for all items</p>
              )}
            </div>
            {confirmState === "confirmed" && (
              <span className="ml-auto flex items-center gap-1 text-xs font-medium text-green-600">
                <Check className="size-3.5" /> Saved
              </span>
            )}
          </div>

          <div className="mt-4">
            <MacroCards macros={currentResult.macros} />
          </div>
        </div>
      </div>

      {/* Macro breakdown */}
      <div className="rounded-3xl border border-border bg-card p-5">
        <SectionLabel>Macro breakdown</SectionLabel>
        <MacroDonut macros={currentResult.macros} calories={currentResult.calories} />
      </div>

      {/* Top predictions */}
      <div className="rounded-3xl border border-border bg-card p-5">
        <SectionLabel>Top 5 predictions</SectionLabel>
        <PredictionsList predictions={currentResult.predictions} />
      </div>
    </div>
  )
}