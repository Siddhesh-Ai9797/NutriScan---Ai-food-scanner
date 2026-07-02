# ── Base image ────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# ── System dependencies ───────────────────────────────────────────────────
RUN apt-get update && apt-get install -y \
    gcc g++ curl unzip \
    && rm -rf /var/lib/apt/lists/*

# ── Install AWS CLI ───────────────────────────────────────────────────────
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
    && unzip awscliv2.zip \
    && ./aws/install \
    && rm -rf awscliv2.zip aws/

# ── Python dependencies ───────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# ── Copy backend code ─────────────────────────────────────────────────────
COPY . .

# ── Create checkpoints directory ──────────────────────────────────────────
RUN mkdir -p checkpoints

# ── Expose port ───────────────────────────────────────────────────────────
EXPOSE 8000

# ── Startup script — downloads model then starts server ──────────────────
CMD aws s3 cp s3://food-scanner-unknown-foods/models/best_model.pth ./checkpoints/best_model.pth \
    && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}