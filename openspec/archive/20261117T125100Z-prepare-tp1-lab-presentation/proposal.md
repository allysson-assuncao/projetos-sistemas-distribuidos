# Proposal: Prepare TP1 Lab Presentation Environment & Multi-Terminal Automation

> **Change ID:** `prepare-tp1-lab-presentation`
> **Status:** approved
> **Author:** @anybo
> **Created:** 2026-11-12
> **Last Updated:** 2026-11-12

---

## Summary

This change enables `trabalho_pratico1` (Distributed Greenhouse Control System using MQTT and XML-RPC) to be installed, validated end-to-end, and demonstrated live on a Windows laboratory machine **without Docker and without Administrator privileges** inside the **Antigravity IDE (VS Code)**. It adds a hybrid local MQTT broker (`estufa/broker_local.py` supporting portable `mosquitto.exe` with an automatic pure-Python MQTT v3.1.1 QoS 1 fallback on `localhost:1883`), an automated End-to-End smoke test suite (`scripts/validate_e2e.py`), updated PowerShell scripts (`scripts/start_all.ps1` and `scripts/reset_demo.ps1`), VS Code/Antigravity IDE split-terminal tasks (`.vscode/tasks.json` and `trabalho_pratico1/.vscode/tasks.json`), unit tests for the local MQTT broker (`tests/test_broker_local.py`), and a self-contained agent execution prompt (`prompt-tp1-lab-setup.md`).

## Motivation

- The live presentation of Practical Assignment 1 (`trabalho_pratico1/roteiro_apresentacao.md`) takes place on an institute laboratory computer running Windows without Docker and without Administrator rights.
- Currently, `docker-compose.yml` and `scripts/start_all.ps1` require Docker (`eclipse-mosquitto:2.0`) to provide the MQTT broker on `localhost:1883`, and `scripts/start_all.ps1` invokes bare `python` instead of `.venv\Scripts\python.exe`, causing `ModuleNotFoundError: No module named 'paho'` in spawned shells.
- During the live presentation, the presenter must show 8 processes interacting in real time inside Antigravity IDE (Broker, Middleware, 3 Controller Replicas, Actuator with LRU cache, Sensor, and Client) and transition across 7 demonstration stages (unit tests, normal startup, autonomous actuation + LRU deduplication, 2/3 crash tolerance, state recovery sync, 2/3 Byzantine masking, and 1/3 quorum loss).

## Scope

### In Scope
- `trabalho_pratico1/estufa/broker_local.py`: Hybrid MQTT broker launcher (uses `trabalho_pratico1/broker/bin/mosquitto.exe` if present and runnable; otherwise runs a built-in pure-Python MQTT v3.1.1 server on `127.0.0.1:1883` supporting `CONNECT/CONNACK`, `SUBSCRIBE/SUBACK`, `PUBLISH/PUBACK` with `QoS 0` and `QoS 1`, `PINGREQ/PINGRESP`, and `DISCONNECT`).
- `trabalho_pratico1/tests/test_broker_local.py`: Unit and integration tests verifying MQTT v3.1.1 `QoS 1` pub/sub and `wait_for_publish()` against the pure-Python broker.
- `trabalho_pratico1/scripts/validate_e2e.py`: Automated pre-flight End-to-End smoke test verifying all 7 stages of `roteiro_apresentacao.md` using real subprocesses and cleaning up `data_ctrl_*.json` afterward.
- `trabalho_pratico1/scripts/start_all.ps1` and `trabalho_pratico1/scripts/reset_demo.ps1`: Non-admin, Docker-free PowerShell launch and cleanup scripts using `.venv\Scripts\python.exe`.
- `.vscode/tasks.json` and `trabalho_pratico1/.vscode/tasks.json`: Antigravity IDE / VS Code compound and stage-specific tasks that open split-screen integrated terminals in parallel.
- `prompt-tp1-lab-setup.md`: Self-contained execution prompt for an independent agent on the lab machine.

### Out of Scope
- Modifying core domain logic in `estufa/sensor.py`, `estufa/controlador.py`, `estufa/atuador.py`, `estufa/middleware.py`, `estufa/middleware_server.py`, or `estufa/cliente.py`.
- Cloud deployment, external network exposure, or TLS/authentication changes to the academic prototype.

## Proposed Solution

### Approach
1. **Hybrid Local MQTT Broker (`estufa/broker_local.py`)**: Checks whether `localhost:1883` is already listening. If not, checks if `broker/bin/mosquitto.exe` exists and can run with a generated local config (`listener 1883 127.0.0.1`, `allow_anonymous true`, `persistence false`). If `mosquitto.exe` is unavailable or blocked by Windows policy, starts a multi-threaded pure-Python TCP server implementing MQTT v3.1.1 packet framing (variable-length remaining length encoding/decoding, `CONNECT/CONNACK`, `SUBSCRIBE/SUBACK`, `PUBLISH/PUBACK` with 2-byte `packet_id` acknowledgment for `QoS 1`, `PINGREQ/PINGRESP`, and `DISCONNECT`).
2. **End-to-End Smoke Test (`scripts/validate_e2e.py`)**: Programmatically spawns the real services (`broker_local`, `middleware_server`, `ctrl_1..3`, `atuador`), tests cluster health (3/3), publishes a low-humidity MQTT reading (`18.5%`) to verify autonomous pump activation and LRU deduplication (`1` execution + `2` duplicate drops), stops `ctrl_3` to verify 2/3 crash tolerance, restarts `ctrl_3` without `--skip-sync` to verify state transfer via Middleware, restarts `ctrl_2` with `--byzantino` to verify 2/3 Byzantine masking, stops `ctrl_3` to verify `ERRO_QUORUM` when 2 of 3 replicas fail, and finally terminates all child processes and deletes `data_ctrl_*.json`.
3. **Antigravity IDE Split-Terminal Automation (`.vscode/tasks.json`)**: Configures VS Code background tasks grouped into split terminal panes (`1_infra`, `2_replicas`, `3_io`, `4_cliente`) plus stage helper tasks (`Modo Seco`, `Modo Quente`, `Recuperar Ctrl 3`, `Ctrl 2 Bizantino`, `Reset Geral`, `Validar Tudo`).

### Impacted Files
| File | Change Type | Notes |
|------|-------------|-------|
| `trabalho_pratico1/estufa/broker_local.py` | Create | Hybrid portable Mosquitto + pure-Python MQTT 3.1.1 QoS 1 broker on `127.0.0.1:1883` |
| `trabalho_pratico1/tests/test_broker_local.py` | Create | Automated tests for pure-Python MQTT 3.1.1 broker with `paho-mqtt` QoS 1 |
| `trabalho_pratico1/scripts/validate_e2e.py` | Create | Pre-flight E2E smoke test covering all presentation stages + state cleanup |
| `trabalho_pratico1/scripts/reset_demo.ps1` | Create | Stops running demo processes on ports `1883, 8001..8003, 9000` and removes `data_ctrl_*.json` |
| `trabalho_pratico1/scripts/start_all.ps1` | Modify | Use `.venv\Scripts\python.exe` and fallback to `estufa.broker_local` when Docker is unavailable |
| `.vscode/tasks.json` | Create | Root workspace split-terminal tasks for Antigravity IDE |
| `trabalho_pratico1/.vscode/tasks.json` | Create | Subfolder workspace split-terminal tasks for Antigravity IDE |
| `prompt-tp1-lab-setup.md` | Create | Ready-to-run prompt for the independent agent on the laboratory machine |

### Data Model Changes (if applicable)
- None. Existing JSON persistence format (`data_ctrl_1.json`, `data_ctrl_2.json`, `data_ctrl_3.json`) and MQTT/XML-RPC payloads remain unchanged.

## Acceptance Criteria

- [ ] **Given** a Windows environment without Docker or Administrator privileges, **When** `python -m estufa.broker_local` is started and `paho-mqtt` clients connect to `localhost:1883` using `MQTTv311` and `qos=1`, **Then** `CONNECT`, `SUBSCRIBE`, `PUBLISH` (`wait_for_publish()`), and `PINGREQ` succeed and subscribed clients receive published messages.
- [ ] **Given** a clean state in `trabalho_pratico1`, **When** `pytest tests/ -v` is executed using `.venv\Scripts\pytest.exe`, **Then** all existing 51 unit tests plus the new `test_broker_local.py` tests pass without external dependencies.
- [ ] **Given** the `.venv` environment in `trabalho_pratico1`, **When** `python scripts/validate_e2e.py` is executed, **Then** all 6 end-to-end presentation scenarios (3/3 health, autonomous MQTT actuation + LRU deduplication, 2/3 crash tolerance, boot state sync recovery, 2/3 Byzantine masking, and 1/3 `ErroQuorum`) pass and `data_ctrl_*.json` files are cleaned up upon completion.
- [ ] **Given** the workspace opened in Antigravity IDE (either at root or `trabalho_pratico1`), **When** the user runs the task `🚀 [DEMO] 1. Subir Todo o Sistema (Estufa TP1)`, **Then** all 8 components launch in organized split integrated terminals using `.venv\Scripts\python.exe`.

## Defensive Security & Validation Considerations

### Input Validation
- `estufa/broker_local.py` validates MQTT packet bounds, remaining-length varint limits (maximum 4 varint bytes per MQTT v3.1.1 specification, rejecting malformed frames), UTF-8 topic decoding errors, and CLI `--host`/`--port` arguments (`1 <= port <= 65535`).
- `scripts/start_all.ps1` validates `$modo_sensor` via `[ValidateSet("normal","seco","quente","frio")]`.

### Secret Isolation
- No credentials, API keys, tokens, or secrets are used or hardcoded anywhere in the project.

### Authorization & Authentication Impact
- N/A — local academic distributed systems simulation; all services bind exclusively to `localhost` (`127.0.0.1`) for loopback inter-process communication.

### Other Security Risks
- **Loopback Binding**: `estufa/broker_local.py` binds by default to `127.0.0.1` (`localhost`) rather than `0.0.0.0`, preventing unintended exposure on shared laboratory LANs.
- **Process Cleanup Safety**: `scripts/reset_demo.ps1` targets only processes listening on the specific project ports (`1883, 8001, 8002, 8003, 9000`) owned by the current user session.

## Testing Strategy & Shift-Left Plan

### Happy Path Tests
| Test ID | Scenario | Test Type | Expected Result |
|---------|----------|-----------|-----------------|
| TP-01 | `paho-mqtt` publishes with `qos=1` and `wait_for_publish()` to `broker_local.py` | Unit / Integration | Subscriber receives exact JSON payload and publisher receives `PUBACK` |
| TP-02 | Multiple subscribers on same topic (`ctrl_1`, `ctrl_2`, `ctrl_3`) receive sensor reading | Integration | All 3 subscribers receive the message and emit identical deterministic `comando_id` |
| TP-03 | Full 7-stage E2E validation (`scripts/validate_e2e.py`) | E2E | All 6 live checks pass and state files are cleaned up |

### Edge Case & Failure Mode Tests
| Test ID | Scenario | Test Type | Expected Result |
|---------|----------|-----------|-----------------|
| TE-01 | Client disconnects abruptly or sends `DISCONNECT` (`0xE0`) to `broker_local.py` | Unit | Broker removes dead socket from topic subscriptions without crashing other clients |
| TE-02 | Payload > 127 bytes (2-byte MQTT varint remaining length) published with `qos=1` | Unit | Broker decodes and encodes multi-byte varint length accurately |
| TE-03 | Malformed MQTT packet / truncated stream sent to `broker_local.py` | Unit | Broker closes the offending client connection gracefully and continues serving |
| TE-04 | E2E quorum loss when 2 of 3 replicas fail (`ctrl_2` Byzantine + `ctrl_3` stopped) | E2E | Middleware raises XML-RPC Fault with `ERRO_QUORUM` |

### Test Commands
- **Run unit tests:** `.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests -v`
- **Run E2E validation:** `.\trabalho_pratico1\.venv\Scripts\python.exe .\trabalho_pratico1\scripts\validate_e2e.py`

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Lab Windows policy (AppLocker/Defender) blocks downloaded `mosquitto.exe` | High | High | `estufa/broker_local.py` automatically falls back to pure-Python MQTT 3.1.1 broker running inside the trusted `python.exe` interpreter |
| Stale `data_ctrl_*.json` or orphan processes between demo rehearsals | Med | Med | `scripts/reset_demo.ps1` and VS Code task `🧹 [RESET]` stop processes on ports `1883, 8001..8003, 9000` and delete `data_ctrl_*.json` |
| Workspace opened at repository root vs `trabalho_pratico1/` subfolder in Antigravity IDE | Med | Med | Provide `.vscode/tasks.json` in both root and `trabalho_pratico1/.vscode/tasks.json` with paths anchored appropriately |

## Specification Changes & Delta Stubs

### `specs/lab-presentation-automation.md`
- **Target Canonical Spec:** `New Specification` (`openspec/specs/lab-presentation-automation.md`)
- **Summary of Updates:** Defines functional and non-functional requirements for Docker-free/Admin-free execution, hybrid MQTT v3.1.1 broker behavior, E2E pre-flight validation, and Antigravity IDE multi-terminal orchestration.

## References

- `trabalho_pratico1/README.md`
- `trabalho_pratico1/roteiro_apresentacao.md`
- `trabalho_pratico1/estufa/config.py`
