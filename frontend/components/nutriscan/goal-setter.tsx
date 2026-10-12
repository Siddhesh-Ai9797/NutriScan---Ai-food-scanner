"use client"

import { useState } from "react"
import { Loader2, Check } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useStore } from "@/lib/store"
import { calculateGoals } from "@/lib/api"

type FitnessGoal = "cutting" | "bulking" | "maintaining"

const GOAL_OPTIONS: { value: FitnessGoal; label: string; emoji: string; desc: string }[] = [
  { value: "cutting",    label: "Cutting",    emoji: "🔥", desc: "Lose fat, preserve muscle" },
  { value: "maintaining",label: "Maintaining", emoji: "⚖️", desc: "Stay at current weight" },
  { value: "bulking",    label: "Bulking",    emoji: "💪", desc: "Build muscle mass" },
]

// Same limits the server uses; values outside them are not saved.
const LIMITS = {
  weightKg   : { min: 25,   max: 300,  label: "Weight",       unit: "kg" },
  age        : { min: 13,   max: 100,  label: "Age",          unit: "years" },
  heightCm   : { min: 120,  max: 230,  label: "Height",       unit: "cm" },
  dailyGoal  : { min: 1200, max: 6000, label: "Daily calories", unit: "kcal" },
  proteinGoal: { min: 0,    max: 400,  label: "Protein",      unit: "g" },
  waterGoal  : { min: 500,  max: 6000, label: "Water goal",   unit: "ml" },
} as const

type LimitKey = keyof typeof LIMITS

function rangeErrors(form: Record<LimitKey, unknown>, keys: LimitKey[], required: LimitKey[]): string[] {
  const errors: string[] = []
  for (const key of keys) {
    const raw = form[key]
    const { min, max, label, unit } = LIMITS[key]
    if (raw === "" || raw === null || raw === undefined) {
      if (required.includes(key)) errors.push(`${label} is required.`)
      continue
    }
    const n = Number(raw)
    if (!Number.isFinite(n) || n < min || n > max) {
      errors.push(`${label} must be between ${min} and ${max} ${unit}.`)
    }
  }
  return errors
}

const ACTIVITY_OPTIONS = [
  { value: "sedentary", label: "Sedentary",  desc: "Desk job, little exercise" },
  { value: "moderate",  label: "Moderate",   desc: "Exercise 3-5 days/week" },
  { value: "active",    label: "Very Active", desc: "Hard exercise 6-7 days/week" },
]

export function GoalSetter({ uid }: { uid: string }) {
  const { profile, updateProfile } = useStore()
  const [saved,    setSaved]    = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [calcLoading, setCalcLoading] = useState(false)
  const [calcNotes, setCalcNotes] = useState<string[]>([])
  const [calcError, setCalcError] = useState<string | null>(null)

  const [form, setForm] = useState({
    fitnessGoal  : profile.fitnessGoal,
    activityLevel: profile.activityLevel,
    dailyGoal    : profile.dailyGoal,
    proteinGoal  : profile.proteinGoal,
    waterGoal    : profile.waterGoal,
    weightKg     : profile.weightKg ?? "",
    age          : profile.age ?? "",
    heightCm     : profile.heightCm ?? "",
    gender       : profile.gender ?? "",
  })

  const saveErrors = rangeErrors(
    form as unknown as Record<LimitKey, unknown>,
    ["weightKg", "age", "heightCm", "dailyGoal", "proteinGoal", "waterGoal"],
    ["dailyGoal", "proteinGoal", "waterGoal"],
  )
  const calcErrors = [
    ...rangeErrors(form as unknown as Record<LimitKey, unknown>, ["weightKg", "age", "heightCm"], ["weightKg", "age", "heightCm"]),
    ...(form.gender ? [] : ["Please choose male or female for the calculation."]),
  ]

  async function autoCalculate() {
    if (calcErrors.length) return
    setCalcLoading(true)
    setCalcError(null)
    setCalcNotes([])
    try {
      const result = await calculateGoals(
        Number(form.weightKg),
        Number(form.age),
        form.fitnessGoal,
        form.activityLevel,
        form.gender as "male" | "female",
        Number(form.heightCm),
      )
      setForm((prev) => ({
        ...prev,
        dailyGoal  : result.daily_goal,
        proteinGoal: result.protein_goal,
        fitnessGoal: (result.fitness_goal as FitnessGoal) ?? prev.fitnessGoal,
      }))
      setCalcNotes(result.notes ?? [])
    } catch (err) {
      setCalcError(err instanceof Error ? err.message : "Couldn't calculate goals. Please try again.")
    } finally {
      setCalcLoading(false)
    }
  }

  async function handleSave() {
    if (saveErrors.length) return
    setLoading(true)
    await updateProfile({
      fitnessGoal  : form.fitnessGoal,
      activityLevel: form.activityLevel,
      dailyGoal    : Number(form.dailyGoal),
      proteinGoal  : Number(form.proteinGoal),
      waterGoal    : Number(form.waterGoal),
      weightKg     : form.weightKg ? Number(form.weightKg) : null,
      age          : form.age ? Number(form.age) : null,
      heightCm     : form.heightCm ? Number(form.heightCm) : null,
      gender       : form.gender === "male" || form.gender === "female" ? form.gender : null,
    }, uid)
    setLoading(false)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="flex flex-col gap-4 rounded-3xl border border-border bg-card p-5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Your goals
      </h3>

      {/* Fitness goal */}
      <div>
        <p className="mb-2 text-sm font-medium text-foreground">Fitness goal</p>
        <div className="flex gap-2">
          {GOAL_OPTIONS.map((g) => (
            <button
              key={g.value}
              onClick={() => setForm((prev) => ({ ...prev, fitnessGoal: g.value }))}
              className={`flex flex-1 flex-col items-center rounded-2xl border p-3 text-center transition-colors ${
                form.fitnessGoal === g.value
                  ? "border-primary bg-accent"
                  : "border-border bg-secondary"
              }`}
            >
              <span className="text-lg">{g.emoji}</span>
              <span className="mt-1 text-xs font-semibold text-foreground">{g.label}</span>
              <span className="text-[10px] text-muted-foreground">{g.desc}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Activity level */}
      <div>
        <p className="mb-2 text-sm font-medium text-foreground">Activity level</p>
        <div className="flex flex-col gap-2">
          {ACTIVITY_OPTIONS.map((a) => (
            <button
              key={a.value}
              onClick={() => setForm((prev) => ({ ...prev, activityLevel: a.value as any }))}
              className={`flex items-center justify-between rounded-xl border px-4 py-2.5 transition-colors ${
                form.activityLevel === a.value
                  ? "border-primary bg-accent"
                  : "border-border bg-secondary"
              }`}
            >
              <span className="text-sm font-medium text-foreground">{a.label}</span>
              <span className="text-xs text-muted-foreground">{a.desc}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Sex for the calorie formula */}
      <div>
        <label className="mb-1.5 block text-sm font-medium text-foreground">Sex (for the calorie formula)</label>
        <div className="flex gap-2">
          {(["female", "male"] as const).map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setForm((prev) => ({ ...prev, gender: g }))}
              className={`h-10 flex-1 rounded-xl border text-sm font-medium capitalize transition-colors ${
                form.gender === g ? "border-primary bg-accent text-primary" : "border-border text-muted-foreground"
              }`}
            >
              {g}
            </button>
          ))}
        </div>
      </div>

      {/* Weight, height and age for auto-calc */}
      <div className="flex gap-3">
        <div className="flex-1">
          <label className="mb-1.5 block text-sm font-medium text-foreground">Weight (kg)</label>
          <input
            type="number"
            value={form.weightKg}
            onChange={(e) => setForm((prev) => ({ ...prev, weightKg: e.target.value }))}
            placeholder="75"
            min={LIMITS.weightKg.min}
            max={LIMITS.weightKg.max}
            className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary"
          />
        </div>
        <div className="flex-1">
          <label className="mb-1.5 block text-sm font-medium text-foreground">Age</label>
          <input
            type="number"
            value={form.age}
            onChange={(e) => setForm((prev) => ({ ...prev, age: e.target.value }))}
            placeholder="24"
            min={LIMITS.age.min}
            max={LIMITS.age.max}
            className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary"
          />
        </div>
        <div className="flex-1">
          <label className="mb-1.5 block text-sm font-medium text-foreground">Height (cm)</label>
          <input
            type="number"
            value={form.heightCm}
            onChange={(e) => setForm((prev) => ({ ...prev, heightCm: e.target.value }))}
            placeholder="170"
            min={LIMITS.heightCm.min}
            max={LIMITS.heightCm.max}
            className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary"
          />
        </div>
      </div>

      <Button
        variant="outline"
        onClick={autoCalculate}
        disabled={calcErrors.length > 0 || calcLoading}
        className="h-10 w-full rounded-full text-sm"
      >
        {calcLoading ? <Loader2 className="size-4 animate-spin" /> : "Auto-calculate my goals"}
      </Button>
      {(form.weightKg !== "" || form.age !== "" || form.heightCm !== "") && calcErrors.length > 0 && (
        <p className="text-xs text-muted-foreground">{calcErrors[0]}</p>
      )}
      {calcError && <p className="text-xs text-destructive">{calcError}</p>}
      {calcNotes.map((note) => (
        <p key={note} className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
          {note}
        </p>
      ))}

      {/* Manual overrides */}
      <div className="flex gap-3">
        <div className="flex-1">
          <label className="mb-1.5 block text-sm font-medium text-foreground">Daily calories</label>
          <input
            type="number"
            value={form.dailyGoal}
            onChange={(e) => setForm((prev) => ({ ...prev, dailyGoal: e.target.value as any }))}
            className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary"
          />
        </div>
        <div className="flex-1">
          <label className="mb-1.5 block text-sm font-medium text-foreground">Protein (g)</label>
          <input
            type="number"
            value={form.proteinGoal}
            onChange={(e) => setForm((prev) => ({ ...prev, proteinGoal: e.target.value as any }))}
            className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary"
          />
        </div>
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-foreground">Daily water goal (ml)</label>
        <input
          type="number"
          value={form.waterGoal}
          onChange={(e) => setForm((prev) => ({ ...prev, waterGoal: e.target.value as any }))}
          className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary"
        />
      </div>

      {saveErrors.length > 0 && (
        <ul className="flex flex-col gap-1">
          {saveErrors.map((e) => (
            <li key={e} className="text-xs text-destructive">{e}</li>
          ))}
        </ul>
      )}

      <Button
        onClick={handleSave}
        disabled={loading || saveErrors.length > 0}
        className="h-11 w-full rounded-full text-sm font-semibold"
      >
        {loading
          ? <Loader2 className="size-4 animate-spin" />
          : saved
          ? <><Check className="size-4" /> Saved!</>
          : "Save goals"
        }
      </Button>
    </div>
  )
}