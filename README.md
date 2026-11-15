# NutriScan AI

[![CI](https://github.com/Siddhesh-Ai9797/NutriScan---Ai-food-scanner/actions/workflows/ci.yml/badge.svg)](https://github.com/Siddhesh-Ai9797/NutriScan---Ai-food-scanner/actions/workflows/ci.yml)

A food nutrition scanner that is live with real users. Take a photo of a meal and get every item on the plate with calories, protein, carbs and fat. The model keeps learning new foods from user feedback through an automated retraining pipeline.

**Live app:** https://nutri-scan-ai-food-scanner.vercel.app

## Results

| Metric | Value |
|---|---|
| Top 1 accuracy, Food-101 test set | 88.46% on 25,250 photos |
| Users | 50+ |
| Photos scanned | about 800 |
| Retraining runs | 8+ in the first 2 months |

## How it works

```mermaid
flowchart LR
    U[User photo] --> C{Seen this photo?}
    C -- yes --> R[Nutrition result]
    C -- no --> F{CLIP: is it food?}
    F -- no --> B[Ask for a food photo]
    F -- yes --> M[EfficientNet-B3 classifier]
    M -- confident --> MINI[gpt-4o-mini, small image]
    M -- unsure --> G[GPT-4o Vision]
    MINI -- disputes or fails --> G
    MINI --> V[Number checks]
    G --> V
    V --> R
    R --> S3[(S3 private bucket)]
    R --> L[User confirms or corrects]
    L --> D[(DynamoDB labels)]
    D --> A[Airflow retraining DAG]
    A --> E{Accuracy checks on new and old foods}
    E -- pass --> P[Deploy new model with S3 backup]
    E -- fail --> K[Keep current model]
```

1. **Cache.** The same photo uploaded again, or retried after a slow network, is answered from memory with no new AI call. Typed food names are cached too.
2. **Guard the input.** A zero shot CLIP model checks that the photo shows food before any paid call. Selfies, screens and rooms are turned away.
3. **Classify.** An EfficientNet-B3 model fine tuned on Food-101 makes the first guess.
4. **Route.** A confident guess goes to gpt-4o-mini with a small image, which costs a small fraction of a full GPT-4o call. An unsure guess, or one the cheap model disagrees with, goes to GPT-4o, which finds every item on the plate and overrules the classifier when it is wrong.
5. **Guard the output.** Every nutrition reply is checked before the user sees it. Negative numbers, foods denser than pure fat, calories lower than their own macros, and plates over 6000 kcal are fixed or rejected, and totals are rebuilt from the items.
6. **Monitor.** Every scan records its route, the time spent in each step, tokens used, dollar cost, cache hits and guardrail hits. These show on the admin page and in the server logs, and are saved to DynamoDB when `METRICS_TABLE` is set.
7. **Learn.** A food label is saved only after 3 users agree on it. Once 50 labels collect, an Airflow pipeline retrains the model on the new foods, such as biryani, without forgetting the old ones.
8. **Release safely.** A new model ships only if it passes accuracy checks on both new and old foods. The old model is backed up to S3 and the live app updates automatically.

### Settings

| Variable | Default | What it does |
|---|---|---|
| `ROUTER` | `on` | Send confident scans to the cheap model first |
| `ROUTER_CONFIDENCE` | `0.95` | Classifier confidence needed for the cheap path |
| `FAST_VISION_MODEL` | `gpt-4o-mini` | Cheap model |
| `FULL_VISION_MODEL` | `gpt-4o` | Full model |
| `FOOD_GATE` | `on` | CLIP food check before paid calls |
| `FOOD_GATE_THRESHOLD` | `0.30` | How sure CLIP must be that a photo is food. Kept low so real meals are never blocked |
| `CACHE` | `on` | Photo and food name caches |
| `PHOTO_CACHE_TTL_HOURS` | `24` | How long a photo answer is kept |
| `METRICS_TABLE` | not set | DynamoDB table for monitoring records, kept for 400 days |

## Tech stack

| Area | Tools |
|---|---|
| Model | PyTorch, EfficientNet-B3, GPT-4o Vision |
| Backend | FastAPI, Docker, Railway |
| Frontend | Next.js, TypeScript, Tailwind, Vercel |
| MLOps | Airflow, MLflow, AWS S3, AWS Lambda, DynamoDB |
| Reliability | CLIP food check, output validation, caching, model routing, cost and latency monitoring |
| Auth | Firebase, verified on the server for every request |

## Project structure

```
backend/     FastAPI app, routers, services and tests
frontend/    Next.js app
model/       Training scripts for the base model
pipeline/    Airflow DAG, retraining, evaluation, deployment, Lambda alert
```

## Running locally

```bash
# Backend
cd backend
pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend
npm ci
npm run dev
```

The backend reads its settings from a `.env` file in the project root: OpenAI key, AWS region and keys, S3 bucket name, DynamoDB table name, Firebase project id and admin email. The model checkpoint goes in `checkpoints/best_model.pth`.

Or run both with Docker:

```bash
docker compose up --build
```

## Tests

```bash
cd backend
pip install -r requirements-test.txt
python -m pytest -q
```

The tests stub the model, Firebase, OpenAI and AWS, so they run in seconds without any keys. They cover sign in checks, rate limits, admin access, portion scaling, the router, both caches, every guardrail rule, cost tracking, and the logic that decides when GPT-4o overrules the model. GitHub Actions runs them on every push, along with the frontend build and the Docker build.

## Security

* Every API route requires a Firebase sign in, and paid routes have per user limits.
* The S3 bucket is private. Photos are shown through short lived signed links.
* User supplied food names are cleaned before they are stored or used for training.
* Monitoring records hold no user ids, photos or food names, only counts, timings and costs.

## Author

Siddhesh Patil, MS in Artificial Intelligence, DePaul University
