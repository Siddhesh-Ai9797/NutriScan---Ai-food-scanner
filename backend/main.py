import os
from dotenv import load_dotenv

# ── Load .env FIRST before anything else ─────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import predict, label

# ── FastAPI app ───────────────────────────────────────────────────────────
app = FastAPI(
    title       = "AI Food Nutrition Scanner",
    description = "Upload a food photo → get calories and macros instantly.",
    version     = "1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["http://localhost:3000", os.getenv("FRONTEND_URL", "*")],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────
app.include_router(predict.router, tags=["Prediction"])
app.include_router(label.router,   tags=["Labeling"])


@app.get("/")
def root():
    return {"status": "running", "message": "AI Food Nutrition Scanner API is live."}


@app.get("/health")
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)