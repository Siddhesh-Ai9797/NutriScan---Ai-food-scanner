"use client"
import { saveMeal } from "@/lib/meals"
import { useState, useRef, useEffect } from "react"
import { Loader2, RotateCcw, AlertCircle, LogOut } from "lucide-react"
import { useRouter } from "next/navigation"
import { Logo } from "@/components/nutriscan/logo"
import { UploadZone } from "@/components/nutriscan/upload-zone"
import { ResultCard } from "@/components/nutriscan/result-card"
import { CalorieTracker } from "@/components/nutriscan/calorie-tracker"
import { RecentScans } from "@/components/nutriscan/recent-scans"
import { BottomNav, type Tab } from "@/components/nutriscan/bottom-nav"
import { MacroDonut } from "@/components/nutriscan/macro-donut"
import { Button } from "@/components/ui/button"
import { scanFood } from "@/lib/api"
import { useStore, getCurrentMeal } from "@/lib/store"
import { useAuth } from "@/lib/auth"
import type { ScanResult } from "@/lib/nutriscan-data"

type ScanState = "idle" | "scanning" | "done" | "error" | "unknown"

export default function Page() {
  const { user, loading, logout } = useAuth()
  const router = useRouter()

  // Redirect to auth if not logged in
  useEffect(() => {
    if (!loading && !user) router.push("/auth")
  }, [user, loading, router])

  if (loading) return (
    <div className="flex min-h-dvh items-center justify-center">
      <Loader2 className="size-8 animate-spin text-primary" />
    </div>
  )

  if (!user) return null

  return <AppShell user={user} onLogout={logout} />
}

function AppShell({
  user,
  onLogout,
}: {
  user: { displayName?: string | null; email?: string | null; uid: string }
  onLogout: () => Promise<void>
}) {
  const [tab, setTab] = useState<Tab>("home")
  const [scanState, setScanState] = useState<ScanState>("idle")
  const [result, setResult] = useState<ScanResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { logMeal, totalCalories, dailyGoal, loadMeals } = useStore()
  useEffect(() => {
    loadMeals(user.uid)
  }, [user.uid])


  // Display name — use Firebase displayName or fallback to email prefix
  const displayName = user.displayName ?? user.email?.split("@")[0] ?? "User"
  const initials = displayName.slice(0, 2).toUpperCase()

  async function handleFile(file: File) {
    setScanState("scanning")
    setError(null)

    try {
      const data = await scanFood(file)

      if (data.isOod && data.source === "unknown") {
        setScanState("unknown")
        return
      }

      setResult(data)
      setScanState("done")
      logMeal(data, getCurrentMeal())

      // Save to Firestore
      if (user) {
        saveMeal(user.uid, {
          name: data.name,
          calories: data.calories,
          protein: data.macros.protein,
          carbs: data.macros.carbs,
          fat: data.macros.fat,
          meal: getCurrentMeal(),
          weightGrams: data.weightGrams ?? null,
          serving: data.serving ?? null,
          source: data.source ?? "efficientnet",
          imageUrl: null,
        })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.")
      setScanState("error")
    }
  }

  function reset() {
    setScanState("idle")
    setResult(null)
    setError(null)
  }

  function changeTab(next: Tab) {
    setTab(next)
    if (next === "scan" && scanState === "done") reset()
  }

  const greeting =
    new Date().getHours() < 12
      ? "Good morning"
      : new Date().getHours() < 17
        ? "Good afternoon"
        : "Good evening"

  return (
    <div className="mx-auto min-h-dvh max-w-md bg-background pb-24">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/90 px-5 py-4 backdrop-blur">
        <Logo />
        <div className="flex items-center gap-2">
          <button
            onClick={onLogout}
            className="flex size-9 items-center justify-center rounded-full text-muted-foreground hover:text-foreground"
            title="Sign out"
          >
            <LogOut className="size-4" />
          </button>
          <span className="flex size-9 items-center justify-center rounded-full bg-secondary text-sm font-semibold text-secondary-foreground">
            {initials}
          </span>
        </div>
      </header>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) handleFile(file)
          e.target.value = ""
        }}
      />

      <main className="flex flex-col gap-5 px-5 py-5">
        {tab === "home" && (
          <>
            <div>
              <p className="text-sm text-muted-foreground">{greeting}, {displayName}</p>
              <h1 className="text-2xl font-bold text-foreground">What did you eat?</h1>
            </div>
            <ScanFlow
              scanState={scanState}
              result={result}
              error={error}
              onFileSelect={() => fileInputRef.current?.click()}
              onReset={reset}
            />
            <CalorieTracker />
            <RecentScans />
          </>
        )}

        {tab === "scan" && (
          <>
            <h1 className="text-2xl font-bold text-foreground">Scan a meal</h1>
            <ScanFlow
              scanState={scanState}
              result={result}
              error={error}
              onFileSelect={() => fileInputRef.current?.click()}
              onReset={reset}
            />
          </>
        )}

        {tab === "stats" && (
          <>
            <h1 className="text-2xl font-bold text-foreground">Your stats</h1>
            <CalorieTracker />
            {result && (
              <div className="rounded-3xl border border-border bg-card p-5">
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Last scan macros
                </h3>
                <MacroDonut macros={result.macros} calories={result.calories} />
              </div>
            )}
            <RecentScans />
          </>
        )}

        {tab === "profile" && (
          <>
            <h1 className="text-2xl font-bold text-foreground">Profile</h1>
            <div className="flex flex-col items-center gap-3 rounded-3xl border border-border bg-card p-8 text-center">
              <span className="flex size-16 items-center justify-center rounded-full bg-primary text-xl font-bold text-primary-foreground">
                {initials}
              </span>
              <div>
                <p className="text-lg font-semibold text-foreground">{displayName}</p>
                <p className="text-sm text-muted-foreground">{user.email}</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Goal: {dailyGoal} kcal / day
                </p>
                <p className="text-sm text-muted-foreground">
                  Today: {totalCalories} kcal consumed
                </p>
              </div>
              <Button
                variant="outline"
                onClick={onLogout}
                className="mt-2 h-10 rounded-full px-6 text-sm font-semibold text-destructive border-destructive/30 hover:bg-destructive/10"
              >
                <LogOut className="size-4" />
                Sign out
              </Button>
            </div>
            <CalorieTracker />
            <RecentScans />
          </>
        )}
      </main>

      <BottomNav active={tab} onChange={changeTab} />
    </div>
  )
}

function ScanFlow({
  scanState,
  result,
  error,
  onFileSelect,
  onReset,
}: {
  scanState: ScanState
  result: ScanResult | null
  error: string | null
  onFileSelect: () => void
  onReset: () => void
}) {
  if (scanState === "scanning") {
    return (
      <div className="flex flex-col items-center gap-3 rounded-3xl border border-border bg-card px-6 py-16 text-center">
        <Loader2 className="size-8 animate-spin text-primary" />
        <p className="text-sm font-medium text-foreground">Analyzing your meal…</p>
        <p className="text-xs text-muted-foreground">Estimating calories and macros</p>
      </div>
    )
  }

  if (scanState === "done" && result) {
    return (
      <div className="flex flex-col gap-4">
        {result.source === "gpt4o" && (
          <div className="flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-700">
            <AlertCircle className="size-4 shrink-0" />
            {result.message ?? "Identified by AI — please confirm below."}
          </div>
        )}
        <ResultCard result={result} />
        <Button
          variant="outline"
          onClick={onReset}
          className="h-11 w-full rounded-full text-sm font-semibold"
        >
          <RotateCcw className="size-4" />
          Scan Another
        </Button>
      </div>
    )
  }

  if (scanState === "unknown") {
    return (
      <div className="flex flex-col items-center gap-4 rounded-3xl border border-border bg-card px-6 py-12 text-center">
        <AlertCircle className="size-10 text-muted-foreground" />
        <div>
          <p className="text-sm font-medium text-foreground">Could not identify this food</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Please try a clearer photo or better lighting.
          </p>
        </div>
        <Button variant="outline" onClick={onReset} className="h-11 rounded-full px-6 text-sm font-semibold">
          <RotateCcw className="size-4" /> Try Again
        </Button>
      </div>
    )
  }

  if (scanState === "error") {
    return (
      <div className="flex flex-col items-center gap-4 rounded-3xl border border-destructive/30 bg-card px-6 py-12 text-center">
        <AlertCircle className="size-10 text-destructive" />
        <div>
          <p className="text-sm font-medium text-foreground">Something went wrong</p>
          <p className="mt-1 text-xs text-muted-foreground">{error}</p>
        </div>
        <Button variant="outline" onClick={onReset} className="h-11 rounded-full px-6 text-sm font-semibold">
          Try Again
        </Button>
      </div>
    )
  }

  return <UploadZone onScan={onFileSelect} />
}