---
id: "lab-presentation-automation"
title: "TP1 Lab Presentation Environment & Multi-Terminal Automation"
version: "1.3.0"
status: "active"
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
    - "trabalho_pratico1/revisao_defesa_tp1.md"
    - "trabalho_pratico1/roteiro_apresentacao.md"
resources: []
---

# TP1 Lab Presentation Environment & Multi-Terminal Automation — Living Specification

> This is the authoritative source of truth for this module's current functional state.
> Update this file only after merging a completed change from `openspec/changes/`.

---

## Context & Objectives

Provides a self-contained, zero-admin, Docker-free execution and validation layer for `trabalho_pratico1` on Windows 11 laboratory computers (with Linux dual-boot compatibility), enabling independent interactive terminals with command history (`Ctrl+C` + `↑`), clean VS Code tasks, automated pre-flight E2E verification of all 7 processes, and synchronized oral-defense reference documentation.

## Functional Requirements

- **[RF-01]** `estufa.broker_local` MUST provide a pure-Python MQTT v3.1.1 broker on `127.0.0.1:1883` without requiring Docker, Windows Administrator privileges, or external `mosquitto.exe` binaries, supporting `CONNECT/CONNACK`, `SUBSCRIBE/SUBACK`, `PUBLISH/PUBACK` (`QoS 0` and `QoS 1`), `PINGREQ/PINGRESP`, and `DISCONNECT`, and exiting cleanly with a diagnostic message if the target port is already in use.
- **[RF-02]** `scripts/start_all.ps1`, `.vscode/tasks.json`, and `trabalho_pratico1/.vscode/tasks.json` MUST launch and manage the 7-process distributed architecture (`broker_local`, `ctrl_1..3` on `8001..8003`, `atuador`, `sensor`, and `cliente`) without `middleware_server` (`:9000`) or `--modo`, providing independent interactive terminals with command history for live parameter adjustments and individual service restarts on Windows 11.
- **[RF-03]** `scripts/validate_e2e.py` MUST verify the 7-process architecture end-to-end against real subprocesses (Bully election, closed-loop MQTT actuation + identical `data_ctrl_1..3.json` persistence, sequential `ctrl_3 -> ctrl_2 -> ctrl_1` failover, reconnection DB sync, 2/3 Byzantine masking, and 2-node conflict `ErroQuorum`) and remove temporary `data_ctrl_*.json` files upon completion.
- **[RF-04]** Defense reference guides (`revisao_defesa_tp1.md`, `roteiro_apresentacao.md`, `relatorio/relatorio.md`, and `trabalho_pratico1_codigo_completo.txt`) MUST maintain exact line-number mappings (`Lxx–Lyy`), including a Defense Survival Guide (Leader vs. Follower comparison, 8 XML-RPC methods, 6 MQTT topics, critical oral-defense Q&As, 3-flow code study guide, and live drill checklist).

## Non-Functional Requirements

- **[RNF-01]** E2E validation suite MUST complete in under 45 seconds on a standard Windows machine.
- **[RNF-02]** All local services MUST bind strictly to loopback (`127.0.0.1`).

## Out of Scope

- Cloud deployment or external LAN exposure outside loopback (`127.0.0.1`).

## Revision History

| Version | Date | Author | Summary |
|---------|------|--------|---------|
| 1.0.0 | 2026-11-12 | @anybo | Initial specification for lab presentation readiness |
| 1.1.0 | 2026-11-17 | @anybo | Streamlined pure-Python broker_local (`simplify-components-and-tests`) |
| 1.2.0 | 2026-11-17 | @anybo | Updated for 7-process interactive Windows 11 demo, E2E suite, and documentation (`prepare-interactive-windows-demo-and-docs`) |
| 1.3.0 | 2026-11-21 | @anybo | Synchronized line-number mappings and added Defense Survival Guide in `revisao_defesa_tp1.md` (`simplify-tp1-for-defense`) |
