# Delta Spec: `iot-sensor-actuator-loop`

> **Change ID:** `simplify-tp1-for-defense`
> **Target Canonical Spec:** `openspec/specs/iot-sensor-actuator-loop.md`
> **Change Type:** Modify

## Architectural Updates

- **Deterministic Closed-Loop Simulation (`estufa/sensor.py`):**
  - Replace `random.uniform()` drift and internal `threading.Lock` in `SimuladorAmbiente` with deterministic fixed-step updates:
    - Temperature: `+2.0°C` per cycle when `exaustor_ligado` is `False`; `-2.5°C` per cycle when `exaustor_ligado` is `True` (clamped to `[0.0, 55.0]`).
    - Soil moisture: `-3.0%` per cycle when `bomba_ligada` is `False`; `+6.0%` per cycle when `bomba_ligada` is `True` (clamped to `[0.0, 100.0]`).
  - Preserve `__init__` range validation, MQTT QoS 1 subscription to `estufa/status/bomba` and `estufa/status/exaustor`, and CLI arguments `--temp`, `--umidade`, `--intervalo`.
