<#
.SYNOPSIS
    Inicializa os componentes do sistema da estufa agrícola distribuída.
.DESCRIPTION
    Ordem de inicialização: Broker -> Middleware -> Controladores -> Atuador -> Sensor.
.PARAMETER modo_sensor
    Perfil de simulação do sensor: normal, seco, quente, frio (padrão: normal).
#>
param(
    [ValidateSet("normal","seco","quente","frio")]
    [string]$modo_sensor = "normal"
)

$ROOT = Split-Path -Parent $PSScriptRoot

Write-Host "Iniciando sistema da estufa agrícola distribuída..." -ForegroundColor Green

Write-Host "[1/6] Verificando Docker..." -ForegroundColor Cyan
try { docker info > $null 2>&1 } catch {
    Write-Host "[ERRO] O serviço Docker não está em execução." -ForegroundColor Red
    exit 1
}

Write-Host "[2/6] Iniciando broker MQTT..." -ForegroundColor Cyan
Push-Location $ROOT; docker compose up -d; Pop-Location
Start-Sleep -Seconds 2

Write-Host "[3/6] Iniciando servidor de Middleware (porta 9000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.middleware_server`"" -WindowStyle Normal
Start-Sleep -Seconds 1

Write-Host "[4/6] Iniciando controladores (3 réplicas)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json`"" -WindowStyle Normal
Start-Sleep -Milliseconds 500
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json`"" -WindowStyle Normal
Start-Sleep -Milliseconds 500
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json`"" -WindowStyle Normal
Start-Sleep -Seconds 1

Write-Host "[5/6] Iniciando atuador..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.atuador`"" -WindowStyle Normal
Start-Sleep -Milliseconds 500

Write-Host "[6/6] Iniciando sensor (modo: $modo_sensor)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.sensor --modo $modo_sensor`"" -WindowStyle Normal

Write-Host ""
Write-Host "Sistema inicializado." -ForegroundColor Green
Write-Host "Para iniciar o cliente:" -ForegroundColor Yellow
Write-Host "    python -m estufa.cliente" -ForegroundColor White
