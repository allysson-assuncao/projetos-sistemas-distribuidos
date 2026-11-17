param(
    [ValidateRange(-50.0, 100.0)]
    [double]$Temp = 28.0,

    [ValidateRange(0.0, 100.0)]
    [double]$Umidade = 42.0,

    [ValidateScript({ $_ -gt 0.05 })]
    [double]$Intervalo = 2.0
)

$ROOT = Split-Path -Parent $PSScriptRoot
$VENV_PYTHON = Join-Path $ROOT ".venv\Scripts\python.exe"
$PYTHON = if (Test-Path $VENV_PYTHON) { $VENV_PYTHON } else { "python" }

function Start-EstufaWindow {
    param(
        [string]$Titulo,
        [string]$Comando,
        [string[]]$HistoricoExtra = @()
    )

    $linhasHist = @()
    foreach ($item in $HistoricoExtra) {
        $escaped = $item.Replace("'", "''")
        $linhasHist += "try { [Microsoft.PowerShell.PSConsoleReadLine]::AddToHistory('$escaped') } catch {}; Add-History -InputObject '$escaped' -ErrorAction SilentlyContinue"
    }
    $cmdEscaped = $Comando.Replace("'", "''")
    $linhasHist += "try { [Microsoft.PowerShell.PSConsoleReadLine]::AddToHistory('$cmdEscaped') } catch {}; Add-History -InputObject '$cmdEscaped' -ErrorAction SilentlyContinue"
    $blocoHist = $linhasHist -join "; "

    $scriptJanela = @"
`$Host.UI.RawUI.WindowTitle = '$Titulo'
Set-Location '$ROOT'
Write-Host '[$Titulo] Dica: pressione Ctrl+C para parar e Seta para Cima para editar/reiniciar.' -ForegroundColor DarkGray
$blocoHist
$Comando
"@

    $bytes = [System.Text.Encoding]::Unicode.GetBytes($scriptJanela)
    $encoded = [Convert]::ToBase64String($bytes)
    Start-Process powershell.exe -ArgumentList "-NoExit", "-EncodedCommand", $encoded -WindowStyle Normal
}

Write-Host "Iniciando Estufa Agrícola Distribuída..." -ForegroundColor Green
Write-Host "Python: $PYTHON" -ForegroundColor Gray

# 1. Broker MQTT local (:1883)
$porta1883Ativa = $null -ne (Get-NetTCPConnection -LocalPort 1883 -State Listen -ErrorAction SilentlyContinue)
if ($porta1883Ativa) {
    Write-Host "[1/6] Broker MQTT já ativo na porta 1883." -ForegroundColor Cyan
} else {
    Write-Host "[1/6] Abrindo janela do Broker MQTT (:1883)..." -ForegroundColor Cyan
    Start-EstufaWindow -Titulo "1. Broker MQTT (:1883)" -Comando "& '$PYTHON' -u -m estufa.broker_local"
    Start-Sleep -Seconds 1
}

# 2. Controladores distribuídos (Bully + Consenso + DB Replicado)
Write-Host "[2/6] Abrindo janelas dos 3 Controladores (8001, 8002, 8003)..." -ForegroundColor Cyan
Start-EstufaWindow `
    -Titulo "2. Controlador 1 (:8001)" `
    -Comando "& '$PYTHON' -u -m estufa.controlador 1" `
    -HistoricoExtra @("& '$PYTHON' -u -m estufa.controlador 1 --byzantino")
Start-Sleep -Milliseconds 300

Start-EstufaWindow `
    -Titulo "3. Controlador 2 (:8002)" `
    -Comando "& '$PYTHON' -u -m estufa.controlador 2" `
    -HistoricoExtra @("& '$PYTHON' -u -m estufa.controlador 2 --byzantino")
Start-Sleep -Milliseconds 300

Start-EstufaWindow `
    -Titulo "4. Controlador 3 (:8003)" `
    -Comando "& '$PYTHON' -u -m estufa.controlador 3" `
    -HistoricoExtra @("& '$PYTHON' -u -m estufa.controlador 3 --byzantino")
Start-Sleep -Seconds 1

# 3. Atuador e Sensor Contínuo
Write-Host "[3/6] Abrindo janela do Atuador MQTT..." -ForegroundColor Cyan
Start-EstufaWindow -Titulo "5. Atuador MQTT" -Comando "& '$PYTHON' -u -m estufa.atuador"
Start-Sleep -Milliseconds 400

Write-Host "[4/6] Abrindo janela do Sensor Contínuo (temp=$Temp, umidade=$Umidade, intervalo=$Intervalo)..." -ForegroundColor Cyan
$cmdSensor = "& '$PYTHON' -u -m estufa.sensor --temp $Temp --umidade $Umidade --intervalo $Intervalo"
Start-EstufaWindow `
    -Titulo "6. Sensor Continuo" `
    -Comando $cmdSensor `
    -HistoricoExtra @(
        "& '$PYTHON' -u -m estufa.sensor --temp 38 --umidade 25 --intervalo 2",
        "& '$PYTHON' -u -m estufa.sensor --temp 12 --umidade 75 --intervalo 2"
    )

Write-Host ""
Write-Host "[OK] 6 janelas abertas com histórico pronto (Ctrl+C e Seta para Cima para alterar parâmetros)." -ForegroundColor Green
Write-Host "Para iniciar o Cliente Direto (7º processo) neste terminal, execute:" -ForegroundColor Yellow
Write-Host "    & '$PYTHON' -m estufa.cliente" -ForegroundColor White
