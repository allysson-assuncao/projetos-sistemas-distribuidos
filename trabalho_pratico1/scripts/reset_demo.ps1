$ErrorActionPreference = "SilentlyContinue"
$ROOT = Split-Path -Parent $PSScriptRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " [RESET] Limpando processos e estados do Trabalho Prático 1" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Encerrar processos Python que estejam rodando módulos 'estufa.'
try {
    $procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'"
    foreach ($p in $procs) {
        if ($p.CommandLine -match "estufa\.") {
            Write-Host " -> Encerrando Python (PID $($p.ProcessId)): $($p.CommandLine)" -ForegroundColor Yellow
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
} catch {}

# 2. Garantir liberação das portas do projeto (1883, 8001, 8002, 8003)
$portas = @(1883, 8001, 8002, 8003)
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

# 3. Remover bancos locais JSON replicados (data_ctrl_*.json e temporários)
Get-ChildItem -Path $ROOT -Filter "data_ctrl_*.json*" -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item $_.FullName -Force -ErrorAction Stop
    Write-Host " -> Estado removido: $($_.Name)" -ForegroundColor Green
}

Write-Host ""
Write-Host "[OK] Ambiente limpo e portas (1883, 8001, 8002, 8003) liberadas!" -ForegroundColor Green
