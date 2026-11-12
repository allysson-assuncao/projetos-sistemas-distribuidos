$ErrorActionPreference = "SilentlyContinue"
$ROOT = Split-Path -Parent $PSScriptRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " [RESET] Limpando processos e estados do Trabalho Prático 1" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Encerrar processos Python que estejam rodando módulos 'estufa.'
try {
    $procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'mosquitto.exe'"
    foreach ($p in $procs) {
        if ($p.CommandLine -match "estufa\." -or $p.Name -eq "mosquitto.exe") {
            Write-Host " -> Encerrando processo $($p.Name) (PID $($p.ProcessId)): $($p.CommandLine)" -ForegroundColor Yellow
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
} catch {}

# 2. Garantir liberação das portas 1883, 8001, 8002, 8003, 9000
$portas = @(1883, 8001, 8002, 8003, 9000)
foreach ($porta in $portas) {
    $conns = Get-NetTCPConnection -LocalPort $porta -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        if ($c.OwningProcess -gt 4) {
            Write-Host " -> Liberando porta $porta (PID $($c.OwningProcess))..." -ForegroundColor Yellow
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}

Start-Sleep -Milliseconds 400

# 3. Remover arquivos de persistência de estado (data_ctrl_*.json)
$arquivosEstado = @(
    (Join-Path $ROOT "data_ctrl_1.json"),
    (Join-Path $ROOT "data_ctrl_2.json"),
    (Join-Path $ROOT "data_ctrl_3.json")
)
foreach ($arq in $arquivosEstado) {
    if (Test-Path $arq) {
        Remove-Item $arq -Force -ErrorAction SilentlyContinue
        Write-Host " -> Estado removido: $(Split-Path -Leaf $arq)" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "[OK] Ambiente limpo e portas (1883, 8001, 8002, 8003, 9000) liberadas!" -ForegroundColor Green
