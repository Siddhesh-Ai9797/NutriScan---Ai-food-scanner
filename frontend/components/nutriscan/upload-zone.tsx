"use client"

import { useState, useCallback } from "react"
import { Camera, ImageUp, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function UploadZone({ onScan }: { onScan: () => void }) {
  const [dragging, setDragging] = useState(false)

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      onScan()
    },
    [onScan],
  )

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={cn(
        "flex flex-col items-center rounded-3xl border-2 border-dashed border-border bg-card px-6 py-10 text-center transition-colors",
        dragging && "border-primary bg-accent",
      )}
    >
      <span className="flex size-14 items-center justify-center rounded-2xl bg-accent text-primary">
        <ImageUp className="size-7" aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-base font-semibold text-foreground text-balance">
        Drop a food photo to scan
      </h2>
      <p className="mt-1 text-sm leading-relaxed text-muted-foreground text-pretty">
        Drag &amp; drop an image here, or choose how to add your meal.
      </p>
      <div className="mt-5 flex w-full flex-col gap-2 sm:flex-row sm:justify-center">
        <Button
          onClick={() => onScan()}
          className="h-11 rounded-full px-6 text-sm font-semibold"
        >
          <Camera className="size-4" aria-hidden="true" />
          Take Photo
        </Button>
        <Button
          variant="outline"
          onClick={() => onScan()}
          className="h-11 rounded-full px-6 text-sm font-semibold"
        >
          <ImageUp className="size-4" aria-hidden="true" />
          Upload Image
        </Button>
      </div>
      <p className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Sparkles className="size-3.5 text-primary" aria-hidden="true" />
        Powered by on-device food recognition
      </p>
    </div>
  )
}