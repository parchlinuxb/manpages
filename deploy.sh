#!/usr/bin/env bash
# ==============================================================================
# Parch Linux Man Pages - Host Deployment Script
# Requirements on Host: bash, docker, docker compose (No Python needed on host)
# ==============================================================================
set -euo pipefail

echo "========================================================"
echo "🚀 Deploying Parch Linux Man Pages Services"
echo "========================================================"

# Step 1: Check Docker installation
if ! command -v docker &>/dev/null; then
    echo "❌ Error: Docker is not installed on this host." >&2
    exit 1
fi

# Step 2: Build and launch containers
echo "[1/2] Building and launching containers in detached mode..."
docker compose up -d --build

# Step 3: Show status
echo "[2/2] Checking running containers..."
docker compose ps

echo "========================================================"
echo "✅ Deployment Successful!"
echo "🌐 Parch Man Pages is live at: http://127.0.0.1:8008"
echo "========================================================"
