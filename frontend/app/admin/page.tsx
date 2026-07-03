"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Loader2, Users, UtensilsCrossed, TrendingUp, Camera, Brain } from "lucide-react"
import { useAuth } from "@/lib/auth"
import { fetchAdminStats, type AdminStats } from "@/lib/admin"

// ── Your admin email — only you can access this page ─────────────────────
const ADMIN_EMAIL = process.env.NEXT_PUBLIC_ADMIN_EMAIL ?? ""

export default function AdminPage() {
  const { user, loading } = useAuth()
  const router            = useRouter()
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [fetching, setFetching] = useState(true)

  useEffect(() => {
    if (!loading) {
      if (!user) { router.push("/auth"); return }
      if (user.email !== ADMIN_EMAIL) { router.push("/"); return }
    }
  }, [user, loading, router])

  useEffect(() => {
    if (user?.email === ADMIN_EMAIL) {
      fetchAdminStats()
        .then(setStats)
        .finally(() => setFetching(false))
    }
  }, [user])

  if (loading || fetching) return (
    <div className="flex min-h-dvh items-center justify-center">
      <Loader2 className="size-8 animate-spin text-primary" />
    </div>
  )

  if (!stats) return null

  return (
    <div className="mx-auto max-w-2xl px-5 py-8">
      <h1 className="mb-6 text-2xl font-bold text-foreground">NutriScan Admin</h1>

      {/* Stats grid */}
      <div className="mb-6 grid grid-cols-2 gap-3">
        <StatCard icon={<UtensilsCrossed className="size-5" />} label="Total meals" value={stats.totalMeals} />
        <StatCard icon={<TrendingUp className="size-5" />} label="Meals today" value={stats.mealsToday} />
        <StatCard icon={<Users className="size-5" />} label="Unique users" value={stats.totalUsers} />
        <StatCard icon={<Camera className="size-5" />} label="Avg calories" value={`${stats.avgCalories} kcal`} />
      </div>

      {/* Model source breakdown */}
      <div className="mb-6 rounded-3xl border border-border bg-card p-5">
        <div className="mb-3 flex items-center gap-2">
          <Brain className="size-5 text-primary" />
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Model performance
          </h2>
        </div>
        <div className="flex gap-4">
          <div className="flex-1 rounded-2xl bg-green-50 border border-green-200 p-3 text-center">
            <p className="text-2xl font-bold text-green-700">{stats.sourceBreakdown.efficientnet}</p>
            <p className="text-xs text-green-600">EfficientNet classified</p>
          </div>
          <div className="flex-1 rounded-2xl bg-amber-50 border border-amber-200 p-3 text-center">
            <p className="text-2xl font-bold text-amber-700">{stats.sourceBreakdown.gpt4o}</p>
            <p className="text-xs text-amber-600">GPT-4o fallback</p>
          </div>
          <div className="flex-1 rounded-2xl bg-red-50 border border-red-200 p-3 text-center">
            <p className="text-2xl font-bold text-red-700">{stats.sourceBreakdown.unknown}</p>
            <p className="text-xs text-red-600">Unidentified</p>
          </div>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Model accuracy: {stats.totalMeals > 0
            ? Math.round((stats.sourceBreakdown.efficientnet / stats.totalMeals) * 100)
            : 0}% classified directly
        </p>
      </div>

      {/* Top foods */}
      <div className="mb-6 rounded-3xl border border-border bg-card p-5">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Most scanned foods
        </h2>
        <div className="flex flex-col gap-2">
          {stats.topFoods.map((food, i) => (
            <div key={food.name} className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground w-4">{i + 1}</span>
              <div className="flex-1">
                <div className="flex justify-between mb-1">
                  <span className="text-sm font-medium capitalize">{food.name}</span>
                  <span className="text-xs text-muted-foreground">{food.count}x</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-primary"
                    style={{ width: `${(food.count / stats.topFoods[0].count) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Recent uploads with photos */}
      {stats.recentUploads.length > 0 && (
        <div className="rounded-3xl border border-border bg-card p-5">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Recent photo uploads
          </h2>
          <div className="grid grid-cols-3 gap-2">
            {stats.recentUploads.map((meal) => (
              <div key={meal.id} className="relative rounded-xl overflow-hidden">
                <img
                  src={meal.imageUrl!}
                  alt={meal.name}
                  className="w-full h-24 object-cover"
                />
                <div className="absolute bottom-0 left-0 right-0 bg-black/60 px-2 py-1">
                  <p className="text-[10px] text-white truncate capitalize">{meal.name}</p>
                  <p className="text-[10px] text-white/70">{meal.calories} kcal</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="rounded-3xl border border-border bg-card p-4">
      <div className="flex items-center gap-2 text-muted-foreground mb-2">{icon}
        <span className="text-xs font-semibold uppercase tracking-wide">{label}</span>
      </div>
      <p className="text-2xl font-bold text-foreground">{value}</p>
    </div>
  )
}