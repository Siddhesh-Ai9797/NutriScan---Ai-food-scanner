"use client"

import { useState } from "react"
import Image from "next/image"
import { Flame, Check, Pencil, Loader2 } from "lucide-react"
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
  const [confirmState, setConfirmState] = useState<ConfirmState>("confirming")
  const [editedName, setEditedName]     = useState("")
  const [currentResult, setCurrentResult] = useState<ScanResult>(result)
  const [error, setError]               = useState<string | null>(null)

  // ── User confirms the food name is correct ────────────────────────────
  async function handleConfirm() {
    setConfirmState("confirmed")

    // Save to training data silently in background
    try {
      await fetch(`${API_URL}/label`, {
        method : "POST",
        headers: { "Content-Type": "application/json" },
        body   : JSON.stringify({
          food_name : currentResult.name,
          image_url : result.imageUrl ?? null,
          source    : result.source ?? "efficientnet",
          calories  : currentResult.calories,
          protein   : currentResult.macros.protein,
          carbs     : currentResult.macros.carbs,
          fat       : currentResult.macros.fat,
          confirmed : true,
        }),
      })
    } catch {
      // Silent fail — don't bother the user
    }
  }

  // ── User edits the food name ──────────────────────────────────────────
  async function handleEdit() {
    if (!editedName.trim()) return
    setConfirmState("loading")
    setError(null)

    try {
      // Fetch nutrition for corrected name
      const res = await fetch(
        `${API_URL}/nutrition?food=${encodeURIComponent(editedName.trim())}`
      )

      if (!res.ok) throw new Error("Could not fetch nutrition")

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

      // Save corrected name + image to training data silently
      try {
        await fetch(`${API_URL}/label`, {
          method : "POST",
          headers: { "Content-Type": "application/json" },
          body   : JSON.stringify({
            food_name : editedName.trim(),
            image_url : result.imageUrl ?? null,
            source    : "user_correction",
            calories  : data.calories,
            protein   : data.protein,
            carbs     : data.carbs,
            fat       : data.fat,
            confirmed : true,
          }),
        })
      } catch {
        // Silent fail
      }

    } catch {
      setError("Couldn't find nutrition for this food. Try a different name.")
      setConfirmState("editing")
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Header card */}
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
        </div>

        <div className="p-5">
          <p className="text-xs font-medium text-muted-foreground">
            Identified food
          </p>
          <h2 className="mt-0.5 text-xl font-bold text-foreground">
            {currentResult.name}
          </h2>

          {/* ── Confirmation UI ── */}
          {confirmState === "confirming" && (
            <div className="mt-4 rounded-2xl border border-border bg-accent p-4">
              <p className="mb-3 text-sm font-medium text-foreground">
                Is this <span className="font-bold">{currentResult.name}</span>?
              </p>
              <div className="flex gap-2">
                <Button
                  onClick={handleConfirm}
                  className="h-10 flex-1 rounded-full text-sm font-semibold"
                >
                  <Check className="size-4" />
                  Correct
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setEditedName(currentResult.name)
                    setConfirmState("editing")
                  }}
                  className="h-10 flex-1 rounded-full text-sm font-semibold"
                >
                  <Pencil className="size-4" />
                  Edit
                </Button>
              </div>
            </div>
          )}

          {/* ── Edit UI ── */}
          {(confirmState === "editing" || confirmState === "loading") && (
            <div className="mt-4 rounded-2xl border border-border bg-accent p-4">
              <p className="mb-2 text-sm font-medium text-foreground">
                What is this food?
              </p>
              <input
                type="text"
                value={editedName}
                onChange={(e) => setEditedName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleEdit()}
                placeholder="e.g. Pomplet Fry, Biryani, Tacos..."
                autoFocus
                className="mb-3 h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary"
              />
              {error && (
                <p className="mb-2 text-xs text-destructive">{error}</p>
              )}
              <div className="flex gap-2">
                <Button
                  onClick={handleEdit}
                  disabled={!editedName.trim() || confirmState === "loading"}
                  className="h-10 flex-1 rounded-full text-sm font-semibold"
                >
                  {confirmState === "loading"
                    ? <Loader2 className="size-4 animate-spin" />
                    : <><Check className="size-4" /> Get nutrition</>
                  }
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setConfirmState("confirming")}
                  disabled={confirmState === "loading"}
                  className="h-10 rounded-full px-4 text-sm"
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}

          {/* ── Calories — always visible ── */}
          <div className="mt-4 flex items-center gap-3 rounded-2xl bg-accent p-4">
            <span className="flex size-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <Flame className="size-5" aria-hidden="true" />
            </span>
            <div className="flex items-baseline gap-1.5">
              <span className="text-4xl font-bold tabular-nums leading-none text-foreground">
                {currentResult.calories}
              </span>
              <span className="text-sm font-medium text-muted-foreground">kcal</span>
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