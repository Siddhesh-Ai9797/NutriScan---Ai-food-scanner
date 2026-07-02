"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Loader2 } from "lucide-react"
import { useAuth } from "@/lib/auth"
import { Button } from "@/components/ui/button"
import { Logo } from "@/components/nutriscan/logo"

type Mode = "login" | "signup"

export default function AuthPage() {
  const router = useRouter()
  const { user, login, signup } = useAuth()  // one call, destructure everything
  const [mode, setMode]       = useState<Mode>("login")
  const [name, setName]       = useState("")
  const [email, setEmail]     = useState("")
  const [password, setPass]   = useState("")
  const [error, setError]     = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (user) router.push("/")
  }, [user, router])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      if (mode === "signup") {
        if (!name.trim()) throw new Error("Please enter your name.")
        await signup(name.trim(), email, password)
      } else {
        await login(email, password)
      }
    } catch (err: unknown) {
      console.error("Auth error:", err)
      const msg = err instanceof Error ? err.message : "Something went wrong."
      // Clean up Firebase error messages
      setError(
        msg.includes("email-already-in-use")
          ? "An account with this email already exists."
          : msg.includes("wrong-password") || msg.includes("invalid-credential")
          ? "Incorrect email or password."
          : msg.includes("weak-password")
          ? "Password must be at least 6 characters."
          : msg.includes("invalid-email")
          ? "Please enter a valid email address."
          : msg
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center px-5">
      <div className="mb-8 flex flex-col items-center gap-2">
        <Logo />
        <p className="text-sm text-muted-foreground">
          {mode === "login" ? "Welcome back" : "Create your account"}
        </p>
      </div>

      <div className="w-full rounded-3xl border border-border bg-card p-6">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">

          {mode === "signup" && (
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-foreground">Name</label>
              <input
                type="text"
                placeholder="Your name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="h-11 w-full rounded-xl border border-border bg-background px-4 text-sm outline-none focus:border-primary"
              />
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-foreground">Email</label>
            <input
              type="email"
              placeholder="you@email.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="h-11 w-full rounded-xl border border-border bg-background px-4 text-sm outline-none focus:border-primary"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-foreground">Password</label>
            <input
              type="password"
              placeholder="Min. 6 characters"
              value={password}
              onChange={(e) => setPass(e.target.value)}
              required
              minLength={6}
              className="h-11 w-full rounded-xl border border-border bg-background px-4 text-sm outline-none focus:border-primary"
            />
          </div>

          {error && (
            <p className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </p>
          )}

          <Button
            type="submit"
            disabled={loading}
            className="h-11 w-full rounded-full text-sm font-semibold"
          >
            {loading
              ? <Loader2 className="size-4 animate-spin" />
              : mode === "login" ? "Sign in" : "Create account"
            }
          </Button>
        </form>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          {mode === "login" ? "Don't have an account? " : "Already have an account? "}
          <button
            type="button"
            onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(null) }}
            className="font-semibold text-primary hover:underline"
          >
            {mode === "login" ? "Sign up" : "Sign in"}
          </button>
        </p>
      </div>
    </div>
  )
}