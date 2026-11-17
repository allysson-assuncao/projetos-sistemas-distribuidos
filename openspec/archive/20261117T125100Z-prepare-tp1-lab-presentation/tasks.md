# Tasks: Prepare TP1 Lab Presentation Environment & Multi-Terminal Automation

> **Change ID:** `prepare-tp1-lab-presentation`
> **Linked Proposal:** [proposal.md](./proposal.md)
> **Status:** complete
>
> All tasks must be `[x]` before this change can be archived via `sdd-spec-archive`.

---

## Implementation Tasks

- [x] Create `trabalho_pratico1/estufa/broker_local.py` implementing the hybrid MQTT v3.1.1 broker (portable `mosquitto.exe` detection + pure-Python `QoS 0/1` server on `127.0.0.1:1883`)
- [x] Fix Windows socket timeout and `as_completed` `TimeoutError` handling in `trabalho_pratico1/estufa/middleware.py` (`_TimeoutTransport` + `TimeoutError` catch in `_votar`)
- [x] Create `trabalho_pratico1/scripts/reset_demo.ps1` to terminate processes on ports `1883, 8001, 8002, 8003, 9000` and remove `data_ctrl_*.json`
- [x] Update `trabalho_pratico1/scripts/start_all.ps1` to use `.venv\Scripts\python.exe` and fallback to `python -u -m estufa.broker_local` when Docker is unavailable
- [x] Create `.vscode/tasks.json` and `trabalho_pratico1/.vscode/tasks.json` with split-screen integrated terminal tasks for Antigravity IDE (`1_infra`, `2_replicas`, `3_io`, `4_cliente`) and stage helper tasks
- [x] Create `trabalho_pratico1/scripts/validate_e2e.py` to execute automated end-to-end verification of all 7 presentation stages and clean up state files

## Security Validation Tasks

- [x] Verify input validation and varint frame bounds in `trabalho_pratico1/estufa/broker_local.py` (`1 <= port <= 65535`, max 4 varint bytes, safe UTF-8 decoding)
- [x] Confirm no secrets or credentials are hardcoded in any created or modified files
- [x] Verify `broker_local.py` binds to `localhost` (`127.0.0.1`) by default

## Shift-Left Test Suite Tasks

### Happy Path
- [x] Write unit/integration test `TP-01` & `TP-02` in `trabalho_pratico1/tests/test_broker_local.py`: verify `paho-mqtt` `QoS 1` publish (`wait_for_publish()`) and multi-subscriber fanout
- [x] Execute E2E test `TP-03` via `trabalho_pratico1/scripts/validate_e2e.py`: verify 3/3 health, MQTT autonomous actuation + LRU deduplication, 2/3 crash tolerance, state sync recovery, and 2/3 Byzantine masking

### Edge Cases & Failure Modes
- [x] Write unit test `TE-01`, `TE-02`, `TE-03` in `trabalho_pratico1/tests/test_broker_local.py` and `test_quorum_2_de_3_um_travado_timeout` in `trabalho_pratico1/tests/test_middleware.py`: verify client disconnect cleanup, payloads > 127 bytes (multi-byte varint), malformed packet resilience, and Windows socket timeout resilience
- [x] Verify E2E test `TE-04` in `trabalho_pratico1/scripts/validate_e2e.py`: confirm `ERRO_QUORUM` when 2 of 3 replicas fail

## Documentation Tasks

- [x] Create `prompt-tp1-lab-setup.md` in repository root with the complete self-contained prompt for the lab machine agent

## Review Gate

- [x] All implementation tasks complete
- [x] All security validation tasks complete
- [x] All tests passing (`.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests -v` and `.\trabalho_pratico1\.venv\Scripts\python.exe .\trabalho_pratico1\scripts\validate_e2e.py`)
- [x] Proposal acceptance criteria verified (run `sdd-spec-validate`)
- [x] Ready for `sdd-spec-archive`
