#!/bin/bash
set -e

APP_NAME="TaskoBot"
COMPOSE_PROJECT="taskobot"

echo "=== $APP_NAME Deploy ==="

# Check .env
if [ ! -f .env ]; then
    echo "[!] .env not found. Creating from .env.example..."
    cp .env.example .env
    echo "[!] Fill in .env with your values and re-run this script."
    exit 1
fi

# Create data dir for SQLite
mkdir -p data

# Build and start
echo "[*] Building containers..."
docker compose -p "$COMPOSE_PROJECT" build

echo "[*] Starting $APP_NAME..."
docker compose -p "$COMPOSE_PROJECT" up -d

# Health check
echo "[*] Waiting for services..."
sleep 3

if curl -sf http://localhost:3000/api/health > /dev/null 2>&1; then
    echo "[+] $APP_NAME is running!"
    echo "    Frontend: http://localhost:3000"
    echo "    API:      http://localhost:3000/api/health"
else
    echo "[!] Health check failed. Check logs:"
    echo "    docker compose -p $COMPOSE_PROJECT logs"
fi
