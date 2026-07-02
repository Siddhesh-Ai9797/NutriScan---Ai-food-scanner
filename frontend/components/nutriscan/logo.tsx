import { ScanLine } from "lucide-react"
import { cn } from "@/lib/utils"

export function Logo({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <span className="flex size-9 items-center justify-center rounded-xl bg-primary text-primary-foreground">
        <ScanLine className="size-5" aria-hidden="true" />
      </span>
      <span className="text-xl font-semibold tracking-tight text-foreground">
        Nutri<span className="text-primary">Scan</span>
      </span>
    </div>
  )
}
