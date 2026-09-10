# Starts the Digital Wallet gRPC server with configurable parameters.
# Run from the atividade_pratica4/ directory.

param(
    [int]$port    = 50051,
    [int]$workers = 10,
    [float]$delay = 0.0
)

$rootDir = Split-Path -Parent $PSScriptRoot

Write-Host "Starting Digital Wallet Server..." -ForegroundColor Cyan
Write-Host "  Port    : $port"      -ForegroundColor Gray
Write-Host "  Workers : $workers"   -ForegroundColor Gray
Write-Host "  Delay   : ${delay}s"  -ForegroundColor Gray

python "$rootDir\carteira\server.py" --port $port --workers $workers --delay $delay
