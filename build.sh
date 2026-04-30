#!/bin/bash
set -e

echo "==> Installing Python dependencies..."
pip install --upgrade pip
pip install "fastapi[standard]==0.115.6" "uvicorn[standard]==0.32.1" \
    "sqlalchemy==2.0.36" "pydantic==2.10.3" "apscheduler==3.10.4" \
    "aiofiles>=23.0.0"

echo "==> Installing Node.js dependencies..."
cd frontend
npm ci

echo "==> Building React frontend..."
npm run build

cd ..
echo "==> Build complete."
