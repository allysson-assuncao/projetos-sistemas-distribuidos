---
id: "distributed-controllers-consensus"
title: "Distributed Controllers, Embedded Middleware, Leader Election & Consensus Persistence"
version: "1.0.0"
status: "active"
owners:
  - "@anybo"
scope:
  paths:
    - "trabalho_pratico1/estufa/config.py"
    - "trabalho_pratico1/estufa/middleware.py"
    - "trabalho_pratico1/estufa/controlador.py"
    - "trabalho_pratico1/estufa/cliente.py"
resources: []
---

# Distributed Controllers, Embedded Middleware, Leader Election & Consensus Persistence — Living Specification

> This is the authoritative source of truth for this module's current functional state.
> Update this file only after merging a completed change from `openspec/changes/`.

---

## Context & Objectives

Defines the core distributed middleware architecture for `trabalho_pratico1` aligned with Figure 1 of `Trabalho Prático 1 - SD.pdf`: an embedded XML-RPC logical layer inside the 3 process controllers (`:8001`, `:8002`, `:8003`) and client CLI, eliminating any external intermediary server (`:9000`), providing dynamic Bully leader election, peer-to-peer consensus validation prior to JSON database persistence, Byzantine fault tolerance, and seamless failover/reconnection recovery.

## Functional Requirements

- **[RF-01]** No standalone middleware intermediary server process (`:9000`) SHALL exist; `estufa/middleware.py` (`ClusterMiddleware`, `ErroQuorum`, `criar_proxy_rpc`) MUST operate as an embedded logical XML-RPC coordination and failover library used directly by `estufa/cliente.py` and `estufa/controlador.py`.
- **[RF-02]** The 3 controllers (`ctrl_1` on `:8001`, `ctrl_2` on `:8002`, `ctrl_3` on `:8003`, also launchable via `python -m estufa.controlador <1|2|3> [--byzantino]`) MUST implement dynamic Bully leader election via XML-RPC methods `ping()`, `iniciar_eleicao(rank_origem: int)`, and `anunciar_lider(novo_lider_id: str)` using controller rank (`1 < 2 < 3`) and periodic leader heartbeat monitoring (`INTERVALO_HEARTBEAT_SEGUNDOS = 2.0`), automatically electing a new leader upon leader crash.
- **[RF-03]** Before persisting official state changes or emitting actuator commands, the elected leader MUST run consensus validation (`coletar_voto_estado(proposta: dict | None)`) across active peers in parallel using `ClusterMiddleware.calcular_consenso(respostas)` dynamic quorum rules:
  - With 3 active controllers: require $\ge 2$ matching votes (masking 1 `--byzantino` node).
  - With 2 active controllers: require agreement ($2/2$) to commit shared updates, raising `ErroQuorum` on irreconcilable conflict.
  - With 1 active controller: operate in degraded $1/1$ mode to preserve system availability.
- **[RF-04]** Upon consensus, the leader MUST synchronously propagate `commit_estado(estado_oficial: dict)` via XML-RPC to all active followers so that `data_ctrl_1.json`, `data_ctrl_2.json`, and `data_ctrl_3.json` store identical validated state (`temperatura`, `umidade`, `bomba_ligada`, `exaustor_ligado`, `ultima_atualizacao`, `lider_id`), and ONLY the leader SHALL publish actuation commands to MQTT (`estufa/atuadores/*`).
- **[RF-05]** When a stopped controller starts or reconnects, `_sincronizar_com_cluster()` MUST pull the official state directly from active peers/leader via XML-RPC `obter_estado()` and update its local JSON database before participating in consensus or assuming leadership.
- **[RF-06]** `estufa/cliente.py` MUST connect directly to the active controllers via `ClusterMiddleware` (`obter_estado()`, `comandar_bomba(ligar: bool)`, `comandar_exaustor(ligar: bool)`, `verificar_saude()`), routing to the active leader (followers transparently forward commands via `_executar_comando_atuador`) and failing over across `8001..8003` on `ConnectionRefusedError`, `TimeoutError`, `socket.timeout`, `OSError`, or `xmlrpc.client.ProtocolError`.

## Non-Functional Requirements

- **[RNF-01]** All peer XML-RPC calls MUST enforce a bounded socket timeout (`TIMEOUT_RPC_SEGUNDOS = 1.5s`) via `_TimeoutTransport`, while client `ClusterMiddleware` defaults to `TIMEOUT_RPC_SEGUNDOS * 2.5` (`3.75s`) so leader consensus + commit completes within the client window.
- **[RNF-02]** All XML-RPC servers (`_ThreadedXMLRPCServer` using `socketserver.ThreadingMixIn` and `allow_reuse_address = True`) MUST bind strictly to `localhost` (`127.0.0.1`) on user-space ports (`8001`, `8002`, `8003`).
- **[RNF-03]** Outbound XML-RPC network calls MUST NEVER execute while holding `self._lock` to prevent cross-controller deadlocks during simultaneous elections or commits, and local JSON writes MUST use atomic thread-scoped temp file replacement.

## Out of Scope

- Continuous sensor curve simplification (`estufa/sensor.py`), actuator/broker cleanup (`estufa/atuador.py`, `estufa/broker_local.py`), and Windows 11 demo scripts/docs (addressed in Changes 2 and 3).

## Revision History

| Version | Date | Author | Summary |
|---------|------|--------|---------|
| 1.0.0 | 2026-11-17 | @anybo | Initial specification and final RPC/quorum contract for Change 1 |
