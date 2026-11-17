# Tasks: Interactive Windows 11 Lab Scripts, E2E Validator & Updated Documentation

> **Change ID:** `prepare-interactive-windows-demo-and-docs`
> **Linked Proposal:** [proposal.md](./proposal.md)
> **Status:** complete
>
> All tasks must be `[x]` before this change can be archived via `sdd-spec-archive`.

---

## Implementation Tasks

- [x] Update `trabalho_pratico1/scripts/start_all.ps1` to launch 6 independent PowerShell windows (`broker_local`, `ctrl_1..3`, `atuador`, `sensor`) using `.venv\Scripts\python.exe`, pre-seeding command history for live `Ctrl+C` + `↑` parameter edits (`-Temp`, `-Umidade`, `-Intervalo`) and removing `middleware_server` / `--modo`
- [x] Update `trabalho_pratico1/scripts/reset_demo.ps1` to stop listeners on `1883, 8001, 8002, 8003` (removing `:9000` / `mosquitto.exe`) and delete `data_ctrl_*.json`
- [x] Update `trabalho_pratico1/scripts/start_all.sh` for Linux dual-boot compatibility (`controlador 1..3`, `sensor` without `--modo`, no `middleware_server`) while noting `docker-compose.yml` status
- [x] Rewrite `trabalho_pratico1/scripts/validate_e2e.py` to validate the 7-process architecture end-to-end (Bully election, closed-loop MQTT + identical JSON commit, sequential failover `ctrl_3 -> ctrl_2 -> ctrl_1`, reconnection sync, 2/3 Byzantine masking, 2-node conflict `ErroQuorum`, and cleanup)
- [x] Simplify `.vscode/tasks.json` and `trabalho_pratico1/.vscode/tasks.json` removing `:9000`, `--modo`, and rigid `ETAPA 3..6` killer tasks

## Security Validation Tasks

- [x] Validate `-Temp` (`-50..100`), `-Umidade` (`0..100`), and `-Intervalo` (`> 0.05`) bounds in `scripts/start_all.ps1`
- [x] Confirm `scripts/reset_demo.ps1` only targets project ports (`1883, 8001..8003`) / `estufa.` Python processes and no secrets exist in scripts or task configs
- [x] Verify `scripts/validate_e2e.py` uses bounded timeouts and cleans up all subprocesses and temporary `data_ctrl_*.json` files in `finally`

## Shift-Left Test Suite Tasks

### Happy Path
- [x] `TP-01` & `TP-02`: Run `.\trabalho_pratico1\.venv\Scripts\python.exe .\trabalho_pratico1\scripts\validate_e2e.py` and confirm Bully election, identical JSON persistence, sequential `ctrl_3 -> ctrl_2 -> ctrl_1` failover, and reconnection sync pass (`39.22s < 45s`)
- [x] `TP-03`: Run `.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests -v -p no:cacheprovider` and verify all 34 tests pass
- [x] `TP-04`: Validate syntax of `start_all.ps1`, `reset_demo.ps1`, `start_all.sh`, `.vscode/tasks.json`, and `trabalho_pratico1/.vscode/tasks.json`

### Edge Cases & Failure Modes
- [x] `TE-01` & `TE-02`: Verify inside `validate_e2e.py` that `--byzantino` on 1 of 3 active nodes is masked by 2/3 majority, and 1 honest + 1 `--byzantino` raises `ErroQuorum`
- [x] `TE-03`: Verify `reset_demo.ps1` executes cleanly with zero unhandled errors when no processes or JSON files exist

## Documentation Tasks

- [x] Update `trabalho_pratico1/README.md` with Figure-1-aligned architecture diagram (explicit arrow, layer, and protocol indicators) and updated 7-process CLI instructions
- [x] Update `trabalho_pratico1/revisao_defesa_tp1.md` as the comprehensive code guide with verified line-number references (`Lxx–Lyy`) across all refactored `estufa/*.py` files and Q&A
- [x] Update `trabalho_pratico1/roteiro_apresentacao.md` as a concise step-by-step live terminal & fault-injection script explaining the distributed mechanism proved at each action
- [x] Update `trabalho_pratico1/relatorio/relatorio.md` and `prompt-tp1-lab-setup.md` to reflect the final architecture and execution commands

## Review Gate

- [x] All implementation tasks complete
- [x] All security validation tasks complete
- [x] All documentation tasks complete with verified line numbers
- [x] All tests and E2E checks passing (`pytest` + `validate_e2e.py`)
- [x] Proposal acceptance criteria verified
- [x] Ready for `sdd-spec-archive`
