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

  const [form, setForm] = useState({
    fitnessGoal  : profile.fitnessGoal,
    activityLevel: profile.activityLevel,
    dailyGoal    : profile.dailyGoal,
    proteinGoal  : profile.proteinGoal,
    waterGoal    : profile.waterGoal,
    weightKg     : profile.weightKg ?? "",
    age          : profile.age ?? "",
  })

  async function autoCalculate() {
    if (!form.weightKg || !form.age) return
    setCalcLoading(true)
    try {
      const result = await calculateGoals(
        Number(form.weightKg),
        Number(form.age),
        form.fitnessGoal,
        form.activityLevel,
      )
      setForm((prev) => ({
        ...prev,
        dailyGoal  : result.daily_goal,
        proteinGoal: result.protein_goal,
      }))
    } catch {
      // Keep manual values
    } finally {
      setCalcLoading(false)
    }
  }

  async function handleSave() {
    setLoading(true)
    await updateProfile({
      fitnessGoal  : form.fitnessGoal,
      activityLevel: form.activityLevel,
      dailyGoal    : Number(form.dailyGoal),
      proteinGoal  : Number(form.proteinGoal),
      waterGoal    : Number(form.waterGoal),
      weightKg     : form.weightKg ? Number(form.weightKg) : null,
      age          : form.age ? Number(form.age) : null,
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

      {/* Weight and age for auto-calc */}
      <div className="flex gap-3">
        <div className="flex-1">
          <label className="mb-1.5 block text-sm font-medium text-foreground">Weight (kg)</label>
          <input
            type="number"
            value={form.weightKg}
            onChange={(e) => setForm((prev) => ({ ...prev, weightKg: e.target.value }))}
            placeholder="75"
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
            className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary"
          />
        </div>
      </div>

      <Button
        variant="outline"
        onClick={autoCalculate}
        disabled={!form.weightKg || !form.age || calcLoading}
        className="h-10 w-full rounded-full text-sm"
      >
        {calcLoading ? <Loader2 className="size-4 animate-spin" /> : "Auto-calculate my goals"}
      </Button>

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

      <Button
        onClick={handleSave}
        disabled={loading}
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