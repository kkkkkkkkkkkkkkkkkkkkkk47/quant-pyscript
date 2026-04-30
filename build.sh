#!/bin/bash
# Build script — runs during deployment to compile the React frontend.
# Called automatically by Railway/Render/Heroku before starting the server.

set -e

echo "==> Installing Python dependencies..."
pip install -e .

echo "==> Installing Node.js dependencies..."
cd frontend
npm ci

echo "==> Building React frontend..."
npm run build

cd ..
echo "==> Build complete. frontend/dist/ is ready."
