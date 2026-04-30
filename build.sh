#!/bin/bash
set -e

echo "==> Upgrading pip, setuptools, wheel..."
python -m pip install --upgrade pip setuptools wheel

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Installing Node.js dependencies..."
cd frontend
npm ci

echo "==> Building React frontend..."
npm run build

cd ..
echo "==> Build complete."
