#!/bin/bash
# start_all.sh — Inicializa os componentes do sistema da estufa agrícola.
# Ordem de boot: Broker -> Middleware -> Controladores -> Atuador -> Sensor

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODO_SENSOR="${1:-normal}"

if [ -x "$ROOT/.venv/bin/python" ]; then
    PYTHON="$ROOT/.venv/bin/python"
elif command -v python3 > /dev/null 2>&1; then
    PYTHON="python3"
else
    PYTHON="python"
fi

echo "Iniciando sistema da estufa agrícola distribuída..."
echo ""

echo "[1/6] Verificando Docker..."
if ! docker info > /dev/null 2>&1; then
    echo "[ERRO] O serviço Docker não está em execução."
    exit 1
fi

echo "[2/6] Iniciando broker MQTT (Docker)..."
cd "$ROOT" && docker compose up -d
sleep 2

echo "[3/6] Iniciando servidor de Middleware (porta 9000)..."
cd "$ROOT" && "$PYTHON" -m estufa.middleware_server &
PIDS=($!)
sleep 1

echo "[4/6] Iniciando controladores (3 réplicas)..."
cd "$ROOT" && "$PYTHON" -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json &
PIDS+=($!)
sleep 0.5
cd "$ROOT" && "$PYTHON" -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json &
PIDS+=($!)
sleep 0.5
cd "$ROOT" && "$PYTHON" -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json &
PIDS+=($!)
sleep 1

echo "[5/6] Iniciando atuador..."
cd "$ROOT" && "$PYTHON" -m estufa.atuador &
PIDS+=($!)
sleep 0.5

echo "[6/6] Iniciando sensor (modo: $MODO_SENSOR)..."
cd "$ROOT" && "$PYTHON" -m estufa.sensor --modo "$MODO_SENSOR" &
PIDS+=($!)

echo ""
echo "Sistema inicializado. PIDs: ${PIDS[*]}"
echo ""
echo "Para iniciar o cliente:"
echo "    $PYTHON -m estufa.cliente"
echo ""
echo "Para encerrar todos os processos:"
echo "    kill ${PIDS[*]}"
echo "    docker compose down"
