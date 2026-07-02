"use client"

import { useState, useRef, useEffect } from "react"
import { Send, Loader2, Bot, User } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useStore } from "@/lib/store"
import { askCoach } from "@/lib/api"

type Message = {
  role   : "user" | "coach"
  content: string
}

const QUICK_QUESTIONS = [
  "What should I eat for dinner?",
  "Am I hitting my protein goal?",
  "How many calories do I have left?",
  "Should I eat more today?",
]

export function CoachChat({ userName }: { userName: string }) {
  const { loggedMeals, profile } = useStore()
  const [messages, setMessages]  = useState<Message[]>([
    {
      role   : "coach",
      content: `Hi ${userName}! 👋 I'm NutriCoach, your personal nutrition assistant. Ask me anything about your diet today!`,
    },
  ])
  const [input, setInput]     = useState("")
  const [loading, setLoading] = useState(false)
  const bottomRef             = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  async function send(text: string) {
    if (!text.trim() || loading) return

    const userMsg: Message = { role: "user", content: text }
    setMessages((prev) => [...prev, userMsg])
    setInput("")
    setLoading(true)

    try {
      const reply = await askCoach(text, loggedMeals, profile, userName)
      setMessages((prev) => [...prev, { role: "coach", content: reply }])
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "coach", content: "Sorry, I'm having trouble connecting. Try again in a moment." },
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col rounded-3xl border border-border bg-card overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-border px-5 py-4">
        <div className="flex size-9 items-center justify-center rounded-full bg-primary">
          <Bot className="size-5 text-primary-foreground" />
        </div>
        <div>
          <p className="text-sm font-semibold text-foreground">NutriCoach</p>
          <p className="text-xs text-muted-foreground">Powered by your meal data</p>
        </div>
        <div className="ml-auto flex size-2 rounded-full bg-green-500" />
      </div>

      {/* Messages */}
      <div className="flex flex-col gap-3 overflow-y-auto px-4 py-4" style={{ maxHeight: 320 }}>
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex gap-2 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}
          >
            <div className={`flex size-7 shrink-0 items-center justify-center rounded-full ${
              msg.role === "coach" ? "bg-primary" : "bg-secondary"
            }`}>
              {msg.role === "coach"
                ? <Bot  className="size-4 text-primary-foreground" />
                : <User className="size-4 text-secondary-foreground" />
              }
            </div>
            <div className={`max-w-[78%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
              msg.role === "coach"
                ? "bg-accent text-foreground rounded-tl-sm"
                : "bg-primary text-primary-foreground rounded-tr-sm"
            }`}>
              {msg.content}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex gap-2">
            <div className="flex size-7 items-center justify-center rounded-full bg-primary">
              <Bot className="size-4 text-primary-foreground" />
            </div>
            <div className="flex items-center gap-1.5 rounded-2xl bg-accent px-4 py-3">
              <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Thinking…</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Quick questions */}
      {messages.length <= 1 && (
        <div className="flex flex-wrap gap-2 px-4 pb-3">
          {QUICK_QUESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => send(q)}
              className="rounded-full border border-border bg-secondary px-3 py-1.5 text-xs font-medium text-secondary-foreground hover:bg-accent"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="flex gap-2 border-t border-border px-4 py-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(input)}
          placeholder="Ask about your nutrition…"
          className="flex-1 rounded-full border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary"
        />
        <Button
          size="icon"
          onClick={() => send(input)}
          disabled={!input.trim() || loading}
          className="size-9 rounded-full shrink-0"
        >
          <Send className="size-4" />
        </Button>
      </div>
    </div>
  )
}