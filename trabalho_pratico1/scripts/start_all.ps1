<#
.SYNOPSIS
    Starts all components of the Distributed Greenhouse System.
.DESCRIPTION
    Boot order: Broker → Middleware Server → Controllers → Actuator → Sensor
    Client must be started manually.
.PARAMETER modo_sensor
    Sensor profile: normal, seco, quente, frio (default: normal)
#>
param(
    [ValidateSet("normal","seco","quente","frio")]
    [string]$modo_sensor = "normal"
)

$ROOT = Split-Path -Parent $PSScriptRoot

Write-Host "🌿 Iniciando Sistema Estufa Agrícola Distribuída..." -ForegroundColor Green

# 0. Verify Docker
Write-Host "[0/7] Verificando Docker..." -ForegroundColor Cyan
try { docker info > $null 2>&1 } catch {
    Write-Host "❌ Docker não está rodando." -ForegroundColor Red
    exit 1
}

# 1. Broker MQTT
Write-Host "[1/7] Iniciando broker MQTT..." -ForegroundColor Cyan
Push-Location $ROOT; docker compose up -d; Pop-Location
Start-Sleep -Seconds 2

# 2. Middleware Server (MUST be before controllers)
Write-Host "[2/7] Iniciando Middleware Server (porta 9000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.middleware_server`"" -WindowStyle Normal
Start-Sleep -Seconds 1

# 3-5. Controllers
Write-Host "[3/7] Iniciando Controladores (3 réplicas)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json`"" -WindowStyle Normal
Start-Sleep -Milliseconds 500
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json`"" -WindowStyle Normal
Start-Sleep -Milliseconds 500
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json`"" -WindowStyle Normal
Start-Sleep -Seconds 1

# 6. Actuator
Write-Host "[4/7] Iniciando Atuador..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.atuador`"" -WindowStyle Normal
Start-Sleep -Milliseconds 500

# 7. Sensor
Write-Host "[5/7] Iniciando Sensor (modo: $modo_sensor)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.sensor --modo $modo_sensor`"" -WindowStyle Normal

Write-Host ""
Write-Host "✅ Sistema inicializado!" -ForegroundColor Green
Write-Host "Para iniciar o cliente:" -ForegroundColor Yellow
Write-Host "    python -m estufa.cliente" -ForegroundColor White
