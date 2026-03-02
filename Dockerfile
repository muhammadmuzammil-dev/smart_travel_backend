FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

# ── CRITICAL: Install CPU-only PyTorch BEFORE everything else ──────────────────
# Default pip installs CUDA PyTorch (~3 GB). CPU-only is ~300 MB.
# This single step brings image from 8.6 GB → ~2 GB.
RUN pip install --no-cache-dir \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies (sentence-transformers will reuse CPU torch)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-bake the embedding model into the image (~90 MB)
# Avoids downloading on every cold start
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy app code and data
COPY . .

EXPOSE 8000

# Use shell form so $PORT env var is expanded at runtime
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
