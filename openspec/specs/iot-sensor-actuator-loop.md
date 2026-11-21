---
id: "iot-sensor-actuator-loop"
title: "Simplified Closed-Loop IoT Sensor & Actuator"
version: "1.1.0"
status: "active"
owners:
  - "@anybo"
scope:
  paths:
    - "trabalho_pratico1/estufa/sensor.py"
    - "trabalho_pratico1/estufa/atuador.py"
resources: []
---

# Simplified Closed-Loop IoT Sensor & Actuator — Living Specification

> This is the authoritative source of truth for this module's current functional state.
> Update this file only after merging a completed change from `openspec/changes/`.

---

## Context & Objectives

Defines the simplified MQTT IoT layer of `trabalho_pratico1`: a single continuous deterministic closed-loop environment simulator (`estufa/sensor.py`) that reacts dynamically to actuator state feedback without rigid static profiles, paired with a deduplication-free actuator (`estufa/atuador.py`) receiving single-source commands from the elected cluster Leader.

## Functional Requirements

- **[RF-01]** `estufa/sensor.py` MUST publish temperature (`estufa/sensores/temperatura`) and soil humidity (`estufa/sensores/umidade_solo`) continuously with QoS 1, drifting deterministically (`+2.0°C` / `-2.5°C` for temperature, `-3.0%` / `+6.0%` for soil moisture, clamped to `[0.0, 55.0]`°C and `[0.0, 100.0]`%) based on `estufa/status/bomba` and `estufa/status/exaustor` feedback so thresholds (`15°C..35°C`, `30%..70%`) are naturally traversed without switching profiles.
- **[RF-02]** `estufa/sensor.py` MUST accept optional CLI overrides `--temp` (`-50..100`), `--umidade` (`0..100`), and `--intervalo` (`> 0.05`s) for live demonstration scenarios.
- **[RF-03]** `estufa/atuador.py` MUST subscribe to `estufa/atuadores/bomba` and `estufa/atuadores/exaustor` with QoS 1, execute `"ligar"` / `"desligar"` commands via a unified handler without LRU deduplication caches, and publish confirmation payloads (`{atuador, ligado, timestamp}`) to `estufa/status/bomba` and `estufa/status/exaustor`.

## Non-Functional Requirements

- **[RNF-01]** Malformed MQTT JSON payloads or out-of-range CLI inputs MUST be rejected or logged safely without terminating the simulation loops unexpectedly.
- **[RNF-02]** Critical MQTT subscription, QoS, and feedback loop sections MUST carry clear pedagogical inline comments for live code inspection.

## Out of Scope

- Controller leader election, consensus validation, and replicated database persistence (governed by `distributed-controllers-consensus.md`).

## Revision History

| Version | Date | Author | Summary |
|---------|------|--------|---------|
| 1.0.0 | 2026-11-17 | @anybo | Initial specification for simplified closed-loop sensor and actuator |
| 1.1.0 | 2026-11-21 | @anybo | Replaced random drift and internal lock in `SimuladorAmbiente` with deterministic fixed steps (`simplify-tp1-for-defense`) |
