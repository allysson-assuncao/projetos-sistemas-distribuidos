#!/bin/bash
# start_all.sh — Starts all components of the Distributed Greenhouse System
# Correct boot order: Broker → Middleware → Controllers → Actuator → Sensor
# Client must be started manually after this script.

set -e  # Exit on error

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODO_SENSOR="${1:-normal}"

echo "🌿 Iniciando Sistema Estufa Agrícola Distribuída..."
echo ""

# ── Verify Docker ──────────────────────────────────────────────
echo "[0/7] Verificando Docker..."
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker daemon não está rodando. Inicie o Docker e tente novamente."
    exit 1
fi
echo "✅ Docker OK"

# ── Step 1: MQTT Broker ────────────────────────────────────────
echo "[1/7] Iniciando broker MQTT (Docker)..."
cd "$ROOT" && docker compose up -d
sleep 2
echo "✅ Broker MQTT iniciado."

# ── Step 2: Middleware Server (MUST come before controllers) ───
echo "[2/7] Iniciando Middleware Server (porta 9000)..."
cd "$ROOT" && python -m estufa.middleware_server &
PIDS=($!)
sleep 1
echo "✅ Middleware Server iniciado (PID: ${PIDS[-1]})."

# ── Steps 3-5: Controllers (will sync state from Middleware) ───
echo "[3/7] Iniciando Controladores (3 réplicas — com state sync)..."
cd "$ROOT" && python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json &
PIDS+=($!)
sleep 0.5
cd "$ROOT" && python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json &
PIDS+=($!)
sleep 0.5
cd "$ROOT" && python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json &
PIDS+=($!)
sleep 1

# ── Step 6: Actuator ───────────────────────────────────────────
echo "[4/7] Iniciando Atuador (com deduplicação LRU)..."
cd "$ROOT" && python -m estufa.atuador &
PIDS+=($!)
sleep 0.5

# ── Step 7: Sensor ─────────────────────────────────────────────
echo "[5/7] Iniciando Sensor (modo: $MODO_SENSOR)..."
cd "$ROOT" && python -m estufa.sensor --modo "$MODO_SENSOR" &
PIDS+=($!)

echo ""
echo "✅ Sistema totalmente inicializado!"
echo ""
echo "PIDs dos processos: ${PIDS[@]}"
echo ""
echo "Para iniciar o cliente:"
echo "    python -m estufa.cliente"
echo ""
echo "Para parar todos os processos:"
echo "    kill ${PIDS[@]}"
echo "    docker compose down"
