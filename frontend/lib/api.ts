import type { ScanResult } from "./nutriscan-data"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export async function scanFood(file: File): Promise<ScanResult> {
  const formData = new FormData()
  formData.append("file", file)

  const response = await fetch(`${API_URL}/predict`, {
    method: "POST",
    body: formData,
  })

  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`)
  }

  const data = await response.json()

  // Map FastAPI response → ScanResult shape v0 expects
  return {
    name: data.food ?? "Unknown food",
    confidence: data.confidence ?? 0,
    calories: data.calories ?? 0,
    macros: {
      protein: data.protein ?? 0,
      carbs: data.carbs ?? 0,
      fat: data.fat ?? 0,
    },
    image: URL.createObjectURL(file),  // show the uploaded photo
    predictions: (data.top5 ?? []).map((p: { food: string; confidence: number }) => ({
      name: p.food.replace(/_/g, " "),
      confidence: Math.round(p.confidence * 100),
    })),
    // Extra fields from API
    weightGrams: data.weight_grams,
    serving: data.serving,
    source: data.source,
    isOod: data.is_ood,
    message: data.message,
  }
}