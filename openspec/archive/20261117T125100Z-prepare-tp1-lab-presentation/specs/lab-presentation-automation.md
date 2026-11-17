---
id: "lab-presentation-automation"
title: "TP1 Lab Presentation Environment & Multi-Terminal Automation"
version: "1.0.0"
status: "draft"
owners:
  - "@anybo"
scope:
  paths:
    - "trabalho_pratico1/estufa/broker_local.py"
    - "trabalho_pratico1/scripts/**"
    - "trabalho_pratico1/tests/test_broker_local.py"
    - ".vscode/tasks.json"
    - "trabalho_pratico1/.vscode/tasks.json"
    - "prompt-tp1-lab-setup.md"
resources: []
---

# TP1 Lab Presentation Environment & Multi-Terminal Automation — Living Specification

> This is the authoritative source of truth for this module's current functional state.
> Update this file only after merging a completed change from `openspec/changes/`.

---

## Context & Objectives

Provides a self-contained, zero-admin, Docker-free execution and validation layer for `trabalho_pratico1` on Windows laboratory computers, enabling one-command multi-terminal launch inside Antigravity IDE (VS Code) and automated pre-flight E2E verification of all presentation stages.

## Functional Requirements

- **[RF-01]** `estufa.broker_local` MUST provide an MQTT v3.1.1 broker on `127.0.0.1:1883` without requiring Docker or Windows Administrator privileges, supporting `CONNECT/CONNACK`, `SUBSCRIBE/SUBACK`, `PUBLISH/PUBACK` (`QoS 0` and `QoS 1`), `PINGREQ/PINGRESP`, and `DISCONNECT`.
- **[RF-02]** `.vscode/tasks.json` and `trabalho_pratico1/.vscode/tasks.json` MUST define background tasks grouped into split terminal panes (`1_infra`, `2_replicas`, `3_io`, `4_cliente`) and a compound task `🚀 [DEMO] 1. Subir Todo o Sistema (Estufa TP1)`.
- **[RF-03]** `scripts/validate_e2e.py` MUST verify all 7 stages of `roteiro_apresentacao.md` against real subprocesses and remove temporary `data_ctrl_*.json` files upon completion.

## Non-Functional Requirements

- **[RNF-01]** E2E validation suite MUST complete in under 25 seconds on a standard Windows machine.
- **[RNF-02]** All local services MUST bind strictly to loopback (`localhost` / `127.0.0.1`).

## Out of Scope

- Modifying existing consensus, hysteresis, or LRU deduplication logic in `estufa/`.

## Revision History

| Version | Date | Author | Summary |
|---------|------|--------|---------|
| 1.0.0 | 2026-11-12 | @anybo | Initial specification for lab presentation readiness |
