# Proposal: Interactive Windows 11 Lab Scripts, E2E Validator & Updated Documentation

> **Change ID:** `prepare-interactive-windows-demo-and-docs`
> **Status:** approved
> **Author:** @anybo
> **Created:** 2026-11-17
> **Last Updated:** 2026-11-17

---

## Summary

Updates all execution scripts (`scripts/start_all.ps1`, `scripts/reset_demo.ps1`, `scripts/start_all.sh`), End-to-End validation (`scripts/validate_e2e.py`), VS Code task definitions (`.vscode/tasks.json`, `trabalho_pratico1/.vscode/tasks.json`), and project documentation (`README.md`, `revisao_defesa_tp1.md`, `roteiro_apresentacao.md`, `relatorio/relatorio.md`, `prompt-tp1-lab-setup.md`) to reflect the refactored 7-process distributed architecture (Bully leader election, dynamic consensus persistence, direct client RPC, and simplified continuous sensor/actuator) and provide smooth interactive terminal control on Windows 11 laboratory machines.

## Motivation

- Addresses Item 5 of `prompt.md` and aligns documentation with Changes 1 and 2:
  1. Legacy `start_all.ps1`, `start_all.sh`, `reset_demo.ps1`, `validate_e2e.py`, and `.vscode/tasks.json` still reference the removed `estufa.middleware_server` (`:9000`), `--skip-sync`, `--modo`, and rigid 8-terminal `ETAPA 3..6` killer tasks.
  2. During the live Windows 11 lab presentation (no Docker, no Admin), the professor will terminate and restart individual services one by one and ask to adjust CLI parameters (`--byzantino`, `--temp`, `--umidade`, `--intervalo`), requiring independent terminals with pre-seeded command history (`Ctrl+C` + `↑`).
  3. `README.md` must present an architecture diagram closely matching Figure 1 of `Trabalho Prático 1 - SD.pdf` with clear labels on every layer, arrow, and protocol.
  4. `revisao_defesa_tp1.md` must serve as the comprehensive deep-dive code guide with exact line references to the refactored `estufa/*.py` files, while `roteiro_apresentacao.md` must be concise and step-driven for live demonstrations.

## Scope

### In Scope
- **`trabalho_pratico1/scripts/start_all.ps1`:** Launch 6 independent PowerShell windows (`broker_local`, `ctrl_1`, `ctrl_2`, `ctrl_3`, `atuador`, `sensor`) using `.venv\Scripts\python.exe`, pre-seeding each shell's PSReadLine / session history (`Add-History` + `PSReadLine` history append or wrapper) so `Ctrl+C` + `↑` immediately recalls the exact launch command for live parameter editing (`--byzantino`, `--temp`, `--umidade`), and print instructions to run `python -m estufa.cliente`.
- **`trabalho_pratico1/scripts/reset_demo.ps1`:** Stop project listeners on ports `1883, 8001, 8002, 8003` (removing legacy `:9000` / `mosquitto.exe` targets) and delete stale `data_ctrl_*.json` files in `trabalho_pratico1/`.
- **`trabalho_pratico1/scripts/start_all.sh`:** Update Linux dual-boot script to launch the 7-process architecture (`controlador 1..3`, `sensor` without `--modo`, no `middleware_server`) while keeping `docker-compose.yml` compatibility noted.
- **`trabalho_pratico1/scripts/validate_e2e.py`:** Rewrite automated E2E subprocess validation for the 7-process architecture:
  1. Start `broker_local`, `ctrl_1..3`, and `atuador`.
  2. Verify Bully leader election (`ctrl_3` elected) and cluster health (`3/3`).
  3. Verify closed-loop MQTT sensor reading triggers leader-only actuation and produces identical `data_ctrl_1.json`..`data_ctrl_3.json`.
  4. Stop `ctrl_3` -> verify automatic Bully failover to `ctrl_2` (`2/2`) and direct `ClusterMiddleware` client operation.
  5. Stop `ctrl_2` -> verify `ctrl_1` operates in degraded `1/1` mode.
  6. Restart `ctrl_2` & `ctrl_3` -> verify automatic reconnection DB sync and Bully re-election of `ctrl_3`.
  7. Restart `ctrl_2` with `--byzantino` -> verify $2/3$ Byzantine fault masking keeps honest `data_ctrl_1.json` and `data_ctrl_3.json` clean, and verify `ErroQuorum` when `ctrl_1` is also stopped leaving conflicting `ctrl_2` (`--byzantino`) + `ctrl_3` (`2` divergent active nodes).
  8. Terminate subprocesses and clean up `data_ctrl_*.json`.
- **`.vscode/tasks.json` & `trabalho_pratico1/.vscode/tasks.json`:** Replace obsolete 8-terminal `middleware_server` and `ETAPA 3..6` killer tasks with clean, modular tasks for individual services, `pytest`, `validate_e2e.py`, and `reset_demo.ps1`.
- **`trabalho_pratico1/README.md`:** Rewrite architecture overview with a Mermaid diagram modeled directly after Figure 1 of `Trabalho Prático 1 - SD.pdf` (`Camada Cliente`, `MIDDLEWARE` enclosing `ctrl_1..3` and their P2P sync/election/consensus + replicated `data_ctrl_*.json` DBs, and `Camada IoT` via `Broker MQTT`), explicitly labeling every arrow, layer, and protocol, plus updated CLI usage.
- **`trabalho_pratico1/revisao_defesa_tp1.md`:** Comprehensive deep-dive defense document explaining every refactored module (`config.py`, `middleware.py`, `controlador.py`, `cliente.py`, `sensor.py`, `atuador.py`, `broker_local.py`) with exact updated line numbers (`Lxx–Lyy`) and live Q&A.
- **`trabalho_pratico1/roteiro_apresentacao.md`:** Concise, actionable presentation guide containing terminal launch commands and a step-by-step demonstration sequence (actions, parameter edits, service shutdowns/restarts) explicitly stating what distributed mechanism each step proves.
- **`trabalho_pratico1/relatorio/relatorio.md` & `prompt-tp1-lab-setup.md`:** Update technical report and lab setup guide to reflect the refactored architecture (no `:9000`, Bully leadership, dynamic quorum, replicated commit, and `34` unit/integration tests + E2E).

### Out of Scope
- Modifying Python logic inside `trabalho_pratico1/estufa/*.py` or `trabalho_pratico1/tests/*.py` (already completed in Changes 1 and 2).
- Deleting `docker-compose.yml` or `mosquitto/mosquitto.conf` (kept per user request for Linux dual-boot testing, with compatibility notes updated).

## Proposed Solution

### Approach
1. **Interactive Windows 11 & Linux Scripts:**
   - `scripts/start_all.ps1` validates optional `-Temp`, `-Umidade`, `-Intervalo` parameters, checks `.venv\Scripts\python.exe`, verifies `1883` availability, and opens 6 independent `powershell.exe -NoExit` windows where each command is added to PSReadLine history (via `[Microsoft.PowerShell.PSConsoleReadLine]::AddToHistory(...)` if available or `Set-Content` to a per-window startup script) before launching `python -u -m estufa.<mod>`, so pressing `Ctrl+C` and `Up Arrow` recalls the command immediately for live tweaks.
   - `scripts/reset_demo.ps1` cleans up processes listening on `1883, 8001, 8002, 8003` and removes `data_ctrl_*.json` (plus any `.tmp` files).
   - `scripts/start_all.sh` mirrors the 7-process commands (`controlador 1..3`, `sensor`, `atuador`, `cliente`) for Linux with Docker/local broker support and documents any Docker dependency.
2. **Real-Subprocess E2E Validator (`scripts/validate_e2e.py`):**
   - Spawns real Python subprocesses on production ports (`1883`, `8001..8003`), drives real MQTT & XML-RPC traffic (`ClusterMiddleware` + `paho-mqtt`), verifies JSON database equality on disk, kills/restarts individual controller subprocesses, verifies `--byzantino` masking and 2-node conflict `ErroQuorum`, and guarantees cleanup in `finally`.
3. **Streamlined IDE Tasks & Documentation Suite:**
   - Simplify `.vscode/tasks.json` and `trabalho_pratico1/.vscode/tasks.json` into lightweight individual/utility tasks (`Broker`, `Ctrl 1..3`, `Atuador`, `Sensor`, `Cliente`, `Reset`, `Testes`).
   - Author `README.md` (Figure 1 architecture mirror with explicit arrow/layer legends), `revisao_defesa_tp1.md` (exhaustive code walkthrough with verified line ranges from the current files), `roteiro_apresentacao.md` (concise terminal & fault-injection steps), `relatorio/relatorio.md`, and `prompt-tp1-lab-setup.md`.

### Impacted Files
| File | Change Type | Notes |
|------|-------------|-------|
| `trabalho_pratico1/scripts/start_all.ps1` | Modify | Interactive 6-window Windows 11 launcher with command history & CLI params |
| `trabalho_pratico1/scripts/reset_demo.ps1` | Modify | Stop `1883, 8001..8003` listeners and remove `data_ctrl_*.json` |
| `trabalho_pratico1/scripts/start_all.sh` | Modify | Update Linux dual-boot script for 7-process CLI (remove `:9000` / `--modo`) |
| `trabalho_pratico1/scripts/validate_e2e.py` | Modify | Rewrite real-subprocess E2E suite for Bully election, consensus commit, failover, sync & Byzantine tests |
| `.vscode/tasks.json` | Modify | Remove `:9000` / `ETAPA 3..6` bloat; keep clean modular tasks |
| `trabalho_pratico1/.vscode/tasks.json` | Modify | Mirror clean modular tasks for subfolder workspace |
| `trabalho_pratico1/README.md` | Modify | Figure-1-aligned architecture diagram with explicit arrow/layer/protocol labels & updated commands |
| `trabalho_pratico1/revisao_defesa_tp1.md` | Modify | Detailed code walkthrough with verified line numbers for refactored modules + defense Q&A |
| `trabalho_pratico1/roteiro_apresentacao.md` | Modify | Concise terminal launch instructions & live fault-injection script explaining proved mechanisms |
| `trabalho_pratico1/relatorio/relatorio.md` | Modify | Update academic report to document embedded middleware, Bully election, consensus DB & 7-process topology |
| `prompt-tp1-lab-setup.md` | Modify | Update lab setup prompt to remove `:9000` and reflect current test/E2E suite |

### Data Model Changes (if applicable)
- None (documents and exercises the canonical JSON and MQTT schemas established in Changes 1 and 2).

## Acceptance Criteria

- [ ] **Given** a clean Windows 11 workspace with `.venv`, **When** `.\trabalho_pratico1\.venv\Scripts\python.exe .\trabalho_pratico1\scripts\validate_e2e.py` is run, **Then** all E2E checks (Bully election, MQTT closed-loop actuation, identical `data_ctrl_1..3.json`, `ctrl_3 -> ctrl_2 -> ctrl_1` failover, reconnection sync, 2/3 Byzantine masking, and 2-node conflict `ErroQuorum`) pass and `data_ctrl_*.json` files are removed afterward.
- [ ] **Given** `scripts/start_all.ps1`, `scripts/reset_demo.ps1`, and `scripts/start_all.sh`, **When** inspected or parsed (`powershell`/`bash -n`), **Then** none reference `middleware_server`, port `9000`, `--skip-sync`, or `--modo`, and `start_all.ps1` validates `-Temp`, `-Umidade`, `-Intervalo` and pre-populates command history in spawned shells.
- [ ] **Given** `.vscode/tasks.json` and `trabalho_pratico1/.vscode/tasks.json`, **When** parsed as JSON, **Then** both are valid JSON without references to `middleware_server`, `:9000`, `--modo`, or rigid `ETAPA 3..6` killer tasks.
- [ ] **Given** `trabalho_pratico1/README.md`, **When** reviewed against Figure 1 of `Trabalho Prático 1 - SD.pdf`, **Then** the architecture diagram clearly encloses controllers inside `MIDDLEWARE`, shows direct Client<->Controller RPC, Controller<->Controller P2P sync/election/consensus, Controller<->DB replication, and Controller<->MQTT pub/sub with explicit legends on every arrow and layer.
- [ ] **Given** `trabalho_pratico1/revisao_defesa_tp1.md` and `trabalho_pratico1/roteiro_apresentacao.md`, **When** cross-checked against `trabalho_pratico1/estufa/*.py`, **Then** `revisao_defesa_tp1.md` provides thorough module explanations with verified line numbers matching current source files, and `roteiro_apresentacao.md` provides concise terminal instructions plus live fault-injection steps explaining each mechanism demonstrated.
- [ ] **Given** the complete test suite, **When** `.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests -v -p no:cacheprovider` and `validate_e2e.py` are executed, **Then** all unit, integration, and E2E checks pass cleanly.

## Defensive Security & Validation Considerations

### Input Validation
- `scripts/start_all.ps1` validates `-Temp` (`-50..100`), `-Umidade` (`0..100`), and `-Intervalo` (`> 0.05`) using PowerShell `[ValidateRange(...)]` attributes.
- `scripts/validate_e2e.py` validates subprocess exit/startup readiness with bounded timeouts and cleans up all child processes in `try/finally`.

### Secret Isolation
- N/A — no credentials, tokens, or API keys exist in scripts, VS Code tasks, or documentation.

### Authorization & Authentication Impact
- N/A — local loopback (`127.0.0.1` / `localhost`) demonstration scripts without auth changes.

### Other Security Risks
- **Safe Process Cleanup (`reset_demo.ps1`):** Only terminates processes bound to the specific project ports (`1883, 8001, 8002, 8003`) or Python processes running `estufa.` in their command line.
- **No Unattended State Artifacts:** `validate_e2e.py` and `reset_demo.ps1` remove temporary `data_ctrl_*.json` files so dirty state never persists across demos.

## Testing Strategy & Shift-Left Plan

### Happy Path Tests
| Test ID | Scenario | Test Type | Expected Result |
|---------|----------|-----------|-----------------|
| TP-01 | `scripts/validate_e2e.py` runs full 7-process happy path (Bully election, closed-loop MQTT, identical `data_ctrl_1..3.json`) | E2E | All 3 JSON files match and client reads/commands succeed without `:9000` |
| TP-02 | `scripts/validate_e2e.py` tests sequential leader failover (`ctrl_3 -> ctrl_2 -> ctrl_1`) and reconnection state sync | E2E | Surviving leader maintains availability; restarted replicas resync JSON and restore Bully order |
| TP-03 | `pytest` full suite after script/doc updates | Unit / Integration | All 34 unit/integration tests pass |
| TP-04 | Syntax validation of PowerShell scripts (`PSParser`), bash script (`bash -n` if available), and JSON task files (`json.load`) | Static | Zero syntax or schema errors |

### Edge Case & Failure Mode Tests
| Test ID | Scenario | Test Type | Expected Result |
|---------|----------|-----------|-----------------|
| TE-01 | `scripts/validate_e2e.py` starts `ctrl_2 --byzantino` with 3 active nodes | E2E | $2/3$ majority isolates corrupted data; honest `data_ctrl_1.json` & `data_ctrl_3.json` remain intact |
| TE-02 | `scripts/validate_e2e.py` stops `ctrl_1` leaving `ctrl_2 --byzantino` + `ctrl_3` honest | E2E | $2$-node tie raises `ErroQuorum` cleanly without corrupting state |
| TE-03 | `scripts/reset_demo.ps1` executed on clean or dirty workspace | Integration | Cleans `data_ctrl_*.json` and port listeners without throwing unhandled errors |

### Test Commands
- **Unit & Integration:** `.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests -v -p no:cacheprovider`
- **E2E Suite:** `.\trabalho_pratico1\.venv\Scripts\python.exe .\trabalho_pratico1\scripts\validate_e2e.py`

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Line numbers cited in `revisao_defesa_tp1.md` drift from actual files | Med | Med | Directly read every file in `trabalho_pratico1/estufa/*.py` with `read_file` before writing `revisao_defesa_tp1.md` to cite exact verified line ranges |
| `validate_e2e.py` hits port conflict if local services are left running | Med | Low | Check/warn cleanly or execute `reset_demo.ps1` before running E2E, and always terminate spawned child processes in `finally` |
| PowerShell execution policy on lab machines blocks unsigned `.ps1` if not invoked properly | Med | Low | Document `powershell -ExecutionPolicy Bypass -File .\scripts\start_all.ps1` alongside standard invocation in `README.md` and `roteiro_apresentacao.md` |

## Specification Changes & Delta Stubs

### `specs/lab-presentation-automation-delta.md`
- **Target Canonical Spec:** `openspec/specs/lab-presentation-automation.md`
- **Summary of Updates:** Updates `RF-02`, `RF-03`, and `RNF-01` to reflect the 7-process modular VS Code tasks, interactive Windows 11 terminal launchers (`start_all.ps1`), and the rewritten E2E validation suite (`validate_e2e.py`) without `:9000` or `--modo`.

## References

- `trabalho_pratico1/Trabalho Prático 1 - SD.pdf` (Figure 1 architectural diagram)
- `trabalho_pratico1/prompt.md` (Item 5: Windows 11 lab presentation requirements)
- `openspec/specs/distributed-controllers-consensus.md`
- `openspec/specs/iot-sensor-actuator-loop.md`
- `openspec/specs/lab-presentation-automation.md`
