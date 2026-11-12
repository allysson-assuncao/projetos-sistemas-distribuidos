param(
    [ValidateSet("normal","seco","quente","frio")]
    [string]$modo_sensor = "normal"
)

$ROOT = Split-Path -Parent $PSScriptRoot
$VENV_PYTHON = Join-Path $ROOT ".venv\Scripts\python.exe"

if (Test-Path $VENV_PYTHON) {
    $PYTHON = $VENV_PYTHON
} else {
    $PYTHON = "python"
}

Write-Host "Iniciando sistema da estufa agrícola distribuída..." -ForegroundColor Green
Write-Host "Usando interpretador Python: $PYTHON" -ForegroundColor Gray

# Verifica se a porta 1883 já está escutando
$porta1883Ativa = $null -ne (Get-NetTCPConnection -LocalPort 1883 -State Listen -ErrorAction SilentlyContinue)

if ($porta1883Ativa) {
    Write-Host "[1/6] Broker MQTT já está ativo na porta 1883." -ForegroundColor Cyan
} else {
    Write-Host "[1/6] Verificando disponibilidade de Docker ou Broker Local (sem Admin)..." -ForegroundColor Cyan
    $dockerOk = $false
    try {
        docker info > $null 2>&1
        if ($LASTEXITCODE -eq 0) {
            $dockerOk = $true
        }
    } catch {
        $dockerOk = $false
    }

    if ($dockerOk) {
        Write-Host "[2/6] Iniciando broker MQTT via Docker Compose..." -ForegroundColor Cyan
        Push-Location $ROOT
        docker compose up -d
        Pop-Location
    } else {
        Write-Host "[2/6] Docker indisponível -> Iniciando Broker MQTT Local Híbrido (porta 1883, sem Admin)..." -ForegroundColor Cyan
        Start-Process powershell -ArgumentList "-NoExit -Command `"$Host.UI.RawUI.WindowTitle = '1. Broker MQTT (:1883)'; Set-Location '$ROOT'; & '$PYTHON' -u -m estufa.broker_local`"" -WindowStyle Normal
    }
    Start-Sleep -Seconds 1
}

Write-Host "[3/6] Iniciando servidor de Middleware (porta 9000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"$Host.UI.RawUI.WindowTitle = '2. Middleware XML-RPC (:9000)'; Set-Location '$ROOT'; & '$PYTHON' -u -m estufa.middleware_server`"" -WindowStyle Normal
Start-Sleep -Seconds 1

Write-Host "[4/6] Iniciando controladores (3 réplicas: 8001, 8002, 8003)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"$Host.UI.RawUI.WindowTitle = '3. Controlador ctrl_1 (:8001)'; Set-Location '$ROOT'; & '$PYTHON' -u -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json`"" -WindowStyle Normal
Start-Sleep -Milliseconds 300
Start-Process powershell -ArgumentList "-NoExit -Command `"$Host.UI.RawUI.WindowTitle = '4. Controlador ctrl_2 (:8002)'; Set-Location '$ROOT'; & '$PYTHON' -u -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json`"" -WindowStyle Normal
Start-Sleep -Milliseconds 300
Start-Process powershell -ArgumentList "-NoExit -Command `"$Host.UI.RawUI.WindowTitle = '5. Controlador ctrl_3 (:8003)'; Set-Location '$ROOT'; & '$PYTHON' -u -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json`"" -WindowStyle Normal
Start-Sleep -Seconds 1

Write-Host "[5/6] Iniciando atuador (Cache LRU)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"$Host.UI.RawUI.WindowTitle = '6. Atuador (Cache LRU)'; Set-Location '$ROOT'; & '$PYTHON' -u -m estufa.atuador`"" -WindowStyle Normal
Start-Sleep -Milliseconds 500

Write-Host "[6/6] Iniciando sensor (modo: $modo_sensor)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"$Host.UI.RawUI.WindowTitle = '7. Sensor ($modo_sensor)'; Set-Location '$ROOT'; & '$PYTHON' -u -m estufa.sensor --modo $modo_sensor`"" -WindowStyle Normal

Write-Host ""
Write-Host "Sistema inicializado com sucesso!" -ForegroundColor Green
Write-Host "Para iniciar o cliente interativo neste terminal, execute:" -ForegroundColor Yellow
Write-Host "    & '$PYTHON' -m estufa.cliente" -ForegroundColor White
