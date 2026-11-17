#!/bin/bash
# start_all.sh — Inicializa os 7 processos do sistema no Linux (dual boot / Docker opcional).
# Uso: ./scripts/start_all.sh [TEMP_INICIAL] [UMIDADE_INICIAL] [INTERVALO]

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMP="${1:-28.0}"
UMIDADE="${2:-42.0}"
INTERVALO="${3:-2.0}"

if [ -x "$ROOT/.venv/bin/python" ]; then
    PYTHON="$ROOT/.venv/bin/python"
elif command -v python3 > /dev/null 2>&1; then
    PYTHON="python3"
else
    PYTHON="python"
fi

PIDS=()
echo "Iniciando sistema da estufa agrícola distribuída (Linux)..."

if command -v docker > /dev/null 2>&1 && docker info > /dev/null 2>&1; then
    echo "[1/5] Iniciando broker MQTT via Docker Compose..."
    cd "$ROOT" && docker compose up -d
    sleep 1
else
    echo "[1/5] Docker indisponível -> iniciando broker_local em Python puro (:1883)..."
    cd "$ROOT" && "$PYTHON" -u -m estufa.broker_local &
    PIDS+=($!)
    sleep 1
fi

echo "[2/5] Iniciando controladores (1, 2 e 3)..."
cd "$ROOT" && "$PYTHON" -u -m estufa.controlador 1 &
PIDS+=($!)
sleep 0.3
cd "$ROOT" && "$PYTHON" -u -m estufa.controlador 2 &
PIDS+=($!)
sleep 0.3
cd "$ROOT" && "$PYTHON" -u -m estufa.controlador 3 &
PIDS+=($!)
sleep 1

echo "[3/5] Iniciando atuador MQTT..."
cd "$ROOT" && "$PYTHON" -u -m estufa.atuador &
PIDS+=($!)
sleep 0.4

echo "[4/5] Iniciando sensor contínuo (temp=$TEMP, umidade=$UMIDADE, intervalo=$INTERVALO)..."
cd "$ROOT" && "$PYTHON" -u -m estufa.sensor --temp "$TEMP" --umidade "$UMIDADE" --intervalo "$INTERVALO" &
PIDS+=($!)

echo ""
echo "[5/5] Sistema ativo. PIDs em background: ${PIDS[*]}"
echo "Para iniciar o cliente interativo:"
echo "    $PYTHON -m estufa.cliente"
echo ""
echo "Para encerrar todos os processos:"
echo "    kill ${PIDS[*]} 2>/dev/null || true"
echo "    docker compose down 2>/dev/null || true"
