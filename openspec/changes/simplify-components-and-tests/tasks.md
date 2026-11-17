# Tasks: Simplify IoT Components, Streamline Tests & Add Pedagogical Comments

> **Change ID:** `simplify-components-and-tests`
> **Linked Proposal:** [proposal.md](./proposal.md)
> **Status:** complete
>
> All tasks must be `[x]` before this change can be archived via `sdd-spec-archive`.

---

## Implementation Tasks

- [x] Remove `DEDUP_CACHE_SIZE` from `trabalho_pratico1/estufa/config.py` and clean up section comments
- [x] Simplify `trabalho_pratico1/estufa/sensor.py`: remove `PERFIS` (`--modo`) and `subs_confirmadas`/`evento_inscrito` ceremony; implement continuous closed-loop `SimuladorAmbiente` with `--temp`, `--umidade`, and `--intervalo`
- [x] Simplify `trabalho_pratico1/estufa/atuador.py`: remove `_dedup_cache` / `_is_duplicado` and unify `_processar_bomba` and `_processar_exaustor` into a single parameterized handler
- [x] Streamline `trabalho_pratico1/estufa/broker_local.py`: remove dead `_tentar_mosquitto_portatil`, `--python-only`, unused wildcard matching, and `UNSUBSCRIBE`; exit cleanly with diagnostic message when port is in use
- [x] Add clear pedagogical inline comments at critical distributed-systems points across all `trabalho_pratico1/estufa/*.py` modules (`config.py`, `middleware.py`, `controlador.py`, `cliente.py`, `sensor.py`, `atuador.py`, `broker_local.py`)

## Security Validation Tasks

- [x] Validate CLI bounds in `sensor.py` (`--temp`, `--umidade`, `--intervalo`) and `broker_local.py` (`1 <= port <= 65535`), plus bounded varint/UTF-8 frame decoding
- [x] Confirm safe JSON payload parsing in `sensor.py` and `atuador.py` without crashing on malformed messages
- [x] Confirm loopback binding (`127.0.0.1`) and absence of hardcoded secrets across all modified files

## Shift-Left Test Suite Tasks

### Happy Path
- [x] Update `trabalho_pratico1/tests/test_sensor.py` (`TP-01`, `TP-02`): verify continuous closed-loop drift for pump/exhaust OFF and ON, plus MQTT status callback handling
- [x] Update `trabalho_pratico1/tests/test_atuador.py` (`TP-03`): verify unified actuator handler updates state and publishes QoS 1 status confirmation
- [x] Streamline `trabalho_pratico1/tests/test_broker_local.py` (`TP-04`): verify real-socket `paho-mqtt` QoS 1 publish (`wait_for_publish()`) and multi-subscriber fanout

### Edge Cases & Failure Modes
- [x] Implement `TE-01` & `TE-02` in `test_sensor.py` and `test_atuador.py`: verify invalid CLI parameter rejection and safe handling of malformed MQTT payloads / unknown actions
- [x] Implement `TE-03` & `TE-04` in `test_broker_local.py`: verify abrupt disconnect cleanup, malformed packet resilience, and clean exit when bind port is already occupied

## Documentation Tasks

- [x] Verify `specs/iot-sensor-actuator-loop.md` and `specs/lab-presentation-automation-delta.md` match the simplified module interfaces

## Review Gate

- [x] All implementation tasks complete
- [x] All security validation tasks complete
- [x] All tests passing (`.\trabalho_pratico1\.venv\Scripts\pytest.exe .\trabalho_pratico1\tests -v -p no:cacheprovider`)
- [x] Proposal acceptance criteria verified
- [x] Ready for `sdd-spec-archive`
