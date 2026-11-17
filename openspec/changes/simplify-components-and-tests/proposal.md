# Proposal: Simplify IoT Components, Streamline Tests & Add Pedagogical Comments

> **Change ID:** `simplify-components-and-tests`
> **Status:** approved
> **Author:** @anybo
> **Created:** 2026-11-17
> **Last Updated:** 2026-11-17

---

## Summary

Simplifies `estufa/sensor.py`, `estufa/atuador.py`, `estufa/broker_local.py`, and `estufa/config.py` by removing over-engineered simulation profiles, obsolete deduplication plumbing, and dead Mosquitto binary wrappers, adds clear human-written pedagogical comments at every critical distributed-systems point across all `estufa/*.py` modules for the live code walkthrough, and streamlines the unit/integration test suite in `trabalho_pratico1/tests/`.

## Motivation

- With the standalone `:9000` intermediary removed and leader-only MQTT publishing implemented in Change 1 (`refactor-core-distributed-controllers`), multiple legacy constructs in the codebase became unnecessary complexity:
  1. `estufa/sensor.py` still carries 4 static simulation profiles (`PERFIS`: `normal`, `seco`, `quente`, `frio`) and a convoluted `subs_confirmadas` callback ceremony that forced presenters to kill and relaunch the sensor with different `--modo` flags instead of letting closed-loop feedback naturally cycle through thresholds.
  2. `estufa/atuador.py` still maintains an `_dedup_cache` LRU `OrderedDict`, `_is_duplicado()`, and duplicated `_processar_bomba`/`_processar_exaustor` functions even though only the elected Leader publishes actuation commands after consensus.
  3. `estufa/broker_local.py` still contains dead `_tentar_mosquitto_portatil` launcher logic (`mosquitto.exe` is absent), `--python-only` CLI clutter, unused MQTT wildcard/`UNSUBSCRIBE` code, and an infinite `threading.Event().wait()` hang when port `1883` is already bound.
  4. Item 4 of `prompt.md` requires cleaning up AI verbosity/over-engineering and adding clear pedagogical inline comments highlighting MQTT topic subscriptions/QoS, XML-RPC calls/timeouts, connection failure handling, leader election, consensus voting, and replicated DB management for the professor's live defense.

## Scope

### In Scope
- **`trabalho_pratico1/estufa/sensor.py`:** Remove `PERFIS` (`--modo`) and the `subs_confirmadas`/`evento_inscrito` ceremony; replace with a single continuous closed-loop `SimuladorAmbiente` that naturally drifts across temperature (`15°C..35°C`) and humidity (`30%..70%`) bounds according to pump/exhaust status feedback, supporting optional `--temp`, `--umidade`, and `--intervalo` CLI arguments.
- **`trabalho_pratico1/estufa/atuador.py` & `trabalho_pratico1/estufa/config.py`:** Remove `_dedup_cache`, `_is_duplicado`, and `DEDUP_CACHE_SIZE`; unify `_processar_bomba` and `_processar_exaustor` into a single parameterized handler (`_processar_atuador`) inside a clean `Atuador` structure/module.
- **`trabalho_pratico1/estufa/broker_local.py`:** Remove dead `_tentar_mosquitto_portatil`, `--python-only`, unused wildcard matching (`_topico_casa_filtro`), and `UNSUBSCRIBE` handling; replace the silent infinite wait on port `1883` conflict with an explicit diagnostic log and clean exit (`SystemExit` / return).
- **`trabalho_pratico1/estufa/*.py` (`config.py`, `middleware.py`, `controlador.py`, `cliente.py`, `sensor.py`, `atuador.py`, `broker_local.py`):** Remove unnecessary verbosity and insert clear, direct inline comments at critical presentation points (MQTT pub/sub + QoS 1, XML-RPC calls + timeouts, failover/connection error handling, Bully leader election, consensus voting, and replicated persistence).
- **`trabalho_pratico1/tests/` (`test_sensor.py`, `test_atuador.py`, `test_broker_local.py`):** Refactor and streamline tests to match the simplified continuous sensor, deduplication-free actuator, and pure-Python local broker without socket-stream test bloat.

### Out of Scope
- Modifying Bully leader election, dynamic quorum rules, or `commit_estado` consensus behavior implemented in Change 1 (`refactor-core-distributed-controllers`).
- Updating Windows 11 / Linux launch scripts (`scripts/start_all.ps1`, `scripts/start_all.sh`, `scripts/reset_demo.ps1`, `scripts/validate_e2e.py`), `.vscode/tasks.json`, or academic documentation (`README.md`, `relatorio.md`, `roteiro_apresentacao.md`) — scheduled for Change 3 (`prepare-interactive-windows-demo-and-docs`).

## Proposed Solution

### Approach
1. **Continuous Closed-Loop Sensor (`estufa/sensor.py`):**
   - Replace the 4 `PERFIS` dictionaries with a clean `SimuladorAmbiente(temp_inicial=28.0, umidade_inicial=45.0)` driven solely by actuator feedback and natural greenhouse drift:
     - When `exaustor_ligado` is `False`, temperature rises smoothly (`+1.5` to `+2.5°C/tick`) until exceeding `35°C`; when `True`, it drops (`-2.5` to `-3.5°C/tick`) until below `15°C`.
     - When `bomba_ligada` is `False`, soil humidity drops smoothly (`-2.5` to `-4.0%/tick`) until below `30%`; when `True`, it rises (`+5.0` to `+7.0%/tick`) until exceeding `70%`.
   - Register `on_connect` (subscribing to `TOPIC_STATUS_BOMBA` and `TOPIC_STATUS_EXAUSTOR` with QoS 1) and `on_message` **before** calling `client.connect()`, removing `subs_confirmadas`, `evento_inscrito`, and `espera_subscricao`.
   - Expose simple optional CLI arguments `--temp` (float, `-50..100`), `--umidade` (float, `0..100`), and `--intervalo` (float, `> 0`, default `2.0`).

2. **Simplified Actuator (`estufa/atuador.py` & `estufa/config.py`):**
   - Remove `DEDUP_CACHE_SIZE` from `config.py`, and remove `_dedup_cache` / `_is_duplicado` from `atuador.py` since leader-only MQTT publishing guarantees single command emission per consensus decision.
   - Replace the duplicated `_processar_bomba` and `_processar_exaustor` functions with a single `_processar_atuador(client, tipo, payload)` handler that validates `acao` (`"ligar"` / `"desligar"`), updates local state, logs the source controller, and publishes feedback to `TOPIC_STATUS_BOMBA` / `TOPIC_STATUS_EXAUSTOR`.

3. **Streamlined Pure-Python Lab Broker (`estufa/broker_local.py`):**
   - Keep `BrokerMQTTLocal` lean and focused on the exact MQTT v3.1.1 packets used by the greenhouse (`CONNECT/CONNACK`, `SUBSCRIBE/SUBACK`, `PUBLISH/PUBACK` for QoS 0 and QoS 1, `PINGREQ/PINGRESP`, `DISCONNECT`).
   - Remove dead `_tentar_mosquitto_portatil`, `--python-only`, `_topico_casa_filtro` wildcards, and `UNSUBSCRIBE` logic.
   - When port `1883` is already in use on `127.0.0.1`, print a clear informative error and exit cleanly instead of hanging silently forever.

4. **Pedagogical Comments & Test Streamlining:**
   - Review every file in `estufa/` to trim verbose AI boilerplate and add clear Portuguese comments explaining each key mechanism (e.g., `# Inscrição MQTT com QoS 1`, `# Timeout explícito XML-RPC`, `# Eleição Bully e tratamento de falha de conexão`, `# Consenso e commit nas réplicas`).
   - Rewrite `test_sensor.py`, `test_atuador.py`, and streamline `test_broker_local.py` (testing real loopback `BrokerMQTTLocal` pub/sub QoS 1 rather than reimplementing raw binary socket streams).

### Impacted Files
| File | Change Type | Notes |
|------|-------------|-------|
| `trabalho_pratico1/estufa/config.py` | Modify | Remove `DEDUP_CACHE_SIZE` and add clear section comments |
| `trabalho_pratico1/estufa/sensor.py` | Modify | Remove `PERFIS`/`--modo` and callback ceremony; implement continuous closed-loop `--temp`/`--umidade`/`--intervalo` |
| `trabalho_pratico1/estufa/atuador.py` | Modify | Remove LRU cache/dedup globals; unify `_processar_bomba` & `_processar_exaustor` |
| `trabalho_pratico1/estufa/broker_local.py` | Modify | Remove dead `mosquitto.exe` wrapper, wildcards, `UNSUBSCRIBE`, and infinite port-busy hang |
| `trabalho_pratico1/estufa/controlador.py` | Modify | Add concise pedagogical defense comments; remove `uuid` import if unused or comment clearly |
| `trabalho_pratico1/estufa/middleware.py` | Modify | Add concise pedagogical defense comments on failover, timeout, and consensus |
| `trabalho_pratico1/estufa/cliente.py` | Modify | Add concise pedagogical defense comments on direct RPC and resilience |
| `trabalho_pratico1/tests/test_sensor.py` | Modify | Update tests for continuous closed-loop simulation and CLI/payload validation |
| `trabalho_pratico1/tests/test_atuador.py` | Modify | Replace LRU tests with simplified actuator state & MQTT status feedback tests |
| `trabalho_pratico1/tests/test_broker_local.py` | Modify | Streamline to concise real-socket MQTT v3.1.1 QoS 1 & malformed-frame tests |

### Data Model Changes (if applicable)
- None. MQTT payloads (`{"valor": float, "unidade": str, "timestamp": float}`, `{"acao": str, "origem": str, "timestamp": float}`, `{"atuador": str, "ligado": bool, "timestamp": float}`) and replicated JSON state (`data_ctrl_*.json`) keep their existing schemas.

## Acceptance Criteria

- [ ] **Given** `estufa/sensor.py` is started without `--modo` (using optional `--temp`, `--umidade`, `--intervalo`), **When** actuators are OFF, **Then** temperature rises above `TEMP_MAX_CELSIUS` (`35°C`) and humidity falls below `UMIDADE_MIN_PERCENT` (`30%`); **When** `estufa/status/bomba` or `estufa/status/exaustor` reports `ligado=true`, **Then** humidity rises and temperature falls naturally within clamped bounds (`0..55°C`, `0..100%`).
- [ ] **Given** `estufa/atuador.py` receives an MQTT JSON command (`"ligar"` or `"desligar"`) on `estufa/atuadores/bomba` or `estufa/atuadores/exaustor`, **When** `_on_message` processes the payload without LRU deduplication, **Then** the actuator updates its state and publishes `{atuador, ligado, timestamp}` to the corresponding `estufa/status/*` topic.
- [ ] **Given** `estufa/broker_local.py` is started on `127.0.0.1:1883`, **When** multiple `paho-mqtt` QoS 1 clients connect, subscribe, publish, and disconnect (or send malformed frames), **Then** messages are delivered cleanly; **When** port `1883` is already bound, **Then** `broker_local.py` prints a clear message and exits without hanging.
- [ ] **Given** all Python modules in `trabalho_pratico1/estufa/`, **When** inspected for presentation defense readiness, **Then** each module contains clear, concise comments explaining MQTT subscriptions/QoS, XML-RPC calls/timeouts, connection failure handling, leader election, consensus voting, and replicated DB management.
- [ ] **Given** the streamlined test suite in `trabalho_pratico1/tests/`, **When** `.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests -v -p no:cacheprovider` is executed, **Then** all tests pass without skipped or relaxed assertions.

## Defensive Security & Validation Considerations

### Input Validation
- Validate `--temp` (`-50.0 <= temp <= 100.0`), `--umidade` (`0.0 <= umidade <= 100.0`), `--intervalo` (`> 0.05` seconds), and `--port` (`1 <= port <= 65535`) on CLI startup, raising `ValueError` or `ArgumentTypeError` on invalid bounds.
- Safely parse incoming MQTT payloads (`json.loads`, `decode("utf-8", errors="strict")`) in `sensor.py` and `atuador.py`, ignoring malformed JSON or non-dict payloads without crashing the MQTT loop.
- Enforce MQTT v3.1.1 varint length bounds (max 4 bytes) and UTF-8 validation in `broker_local.py`, disconnecting malformed clients cleanly.

### Secret Isolation
- N/A — no credentials, tokens, passwords, or API keys exist in any module or configuration file.

### Authorization & Authentication Impact
- N/A — local loopback (`127.0.0.1`) academic simulation; no authentication layer modified.

### Other Security Risks
- **Loopback Binding:** `broker_local.py` binds exclusively to `127.0.0.1` by default, preventing LAN exposure on shared university networks.
- **Resource Protection:** `broker_local.py` closes dead/erroneous client sockets promptly and `sensor.py` / `atuador.py` clamp simulated values to safe numeric intervals.

## Testing Strategy & Shift-Left Plan

### Happy Path Tests
| Test ID | Scenario | Test Type | Expected Result |
|---------|----------|-----------|-----------------|
| TP-01 | `SimuladorAmbiente` closed-loop drift with pump/exhaust OFF and ON | Unit | Temp rises when exhaust OFF and drops when ON; humidity drops when pump OFF and rises when ON |
| TP-02 | `sensor.py` receives `estufa/status/bomba` / `estufa/status/exaustor` via MQTT | Unit / Integration | Actuator state updates inside `SimuladorAmbiente` and reverses drift direction |
| TP-03 | `atuador.py` processes `ligar` and `desligar` on pump and exhaust topics | Unit | Internal state updates and `estufa/status/*` confirmation is published with QoS 1 |
| TP-04 | `broker_local.py` delivers QoS 1 publish (`wait_for_publish()`) to multiple subscribers | Integration | All subscribers receive exact payload and publisher receives `PUBACK` |

### Edge Case & Failure Mode Tests
| Test ID | Scenario | Test Type | Expected Result |
|---------|----------|-----------|-----------------|
| TE-01 | Invalid CLI params (`--temp 999`, `--umidade -5`, `--intervalo 0`, `--port 70000`) | Unit | Rejected cleanly with `ValueError` / `SystemExit` |
| TE-02 | Malformed JSON or unknown action received by `sensor.py` / `atuador.py` | Unit | Logged and safely ignored without crashing the MQTT loop |
| TE-03 | Client abrupt disconnect or malformed MQTT packet sent to `broker_local.py` | Integration | Offending socket removed cleanly while remaining clients stay operational |
| TE-04 | `broker_local.py` launched when port `1883` is already in use | Integration | Prints diagnostic message and exits cleanly without infinite hang |

### Test Commands
- **Run full suite:** `.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests -v -p no:cacheprovider`
- **Run targeted component tests:** `.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests\test_sensor.py .\trabalho_pratico1\tests\test_atuador.py .\trabalho_pratico1\tests\test_broker_local.py -v -p no:cacheprovider`

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Downstream scripts (`start_all.ps1`, `start_all.sh`, `validate_e2e.py`) still pass `--modo` to `sensor.py` until Change 3 | High | Low | Explicitly document in Change 2 output and update all launch/E2E scripts in Change 3 (`prepare-interactive-windows-demo-and-docs`) |
| Removing `_dedup_cache` in `atuador.py` if two controllers ever emitted simultaneously during a split-brain | Low | Low | Change 1 already enforces leader-only MQTT emission via Bully rank; actuator state updates are idempotent (`ligar`/`desligar`) |
| Trimming `broker_local.py` breaks QoS 1 `PUBACK` with `paho-mqtt` 2.1.0 | Low | Med | Keep `test_broker_local.py` testing real `paho-mqtt` `QoS 1` `wait_for_publish()` end-to-end |

## Specification Changes & Delta Stubs

### `specs/iot-sensor-actuator-loop.md`
- **Target Canonical Spec:** `New Specification` (`openspec/specs/iot-sensor-actuator-loop.md`)
- **Summary of Updates:** Defines the simplified continuous closed-loop sensor simulation (`--temp`, `--umidade`, `--intervalo`) and deduplication-free MQTT actuator behavior.

### `specs/lab-presentation-automation-delta.md`
- **Target Canonical Spec:** `openspec/specs/lab-presentation-automation.md`
- **Summary of Updates:** Updates `RF-01` to reflect the streamlined pure-Python `estufa.broker_local` (removing portable `mosquitto.exe` detection, unused wildcards, and silent infinite wait on port conflict).

## References

- `trabalho_pratico1/prompt.md` (Item 4: code simplification, removal of extra complexity, and pedagogical comments)
- `openspec/specs/distributed-controllers-consensus.md`
- `openspec/specs/lab-presentation-automation.md`
- `openspec/specs/sdd-stack-contract.md`
